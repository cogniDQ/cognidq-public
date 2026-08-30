"""
BusinessValueService — KQI-064 to KQI-066.

Estimates the business value delivered by data quality flows:
  KQI-064: Issues caught (with trend)
  KQI-065: Estimated incidents avoided (issues of major+ severity resolved before escalation)
  KQI-066: Cost saved estimate (severity × cost model)
Also provides a ranked list of top flows by value contributed.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.flow import DQFlow, FlowExecution
from app.models.incident import IncidentIssue
from app.models.issue import Issue
from app.models.kqi import CostModel
from app.schemas.kqi import (
    BusinessValueSummaryResponse,
    IssuesTrendDataPoint,
    TopFlowEntry,
    TopFlowsResponse,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5
MAJOR_SEVERITIES = {"critical", "major"}


class BusinessValueService:
    """Service for estimating business value delivered by DQ flows."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Cache helpers (same pattern as MetricsService)
    # ------------------------------------------------------------------

    def _get_cached(self, workspace_id: UUID, metric_type: str):
        return (
            self.db.query(MetricsCache)
            .filter(
                and_(
                    MetricsCache.workspace_id == workspace_id,
                    MetricsCache.metric_type == metric_type,
                    MetricsCache.calculated_at
                    > datetime.utcnow() - timedelta(minutes=CACHE_TTL_MINUTES),
                )
            )
            .first()
        )

    def _set_cache(self, workspace_id: UUID, metric_type: str, value: dict):
        import uuid as _uuid

        entry = MetricsCache(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            metric_type=metric_type,
            metric_value=value,
            calculated_at=datetime.utcnow(),
        )
        self.db.add(entry)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to cache metric %s", metric_type)

    # ------------------------------------------------------------------
    # Cost lookup
    # ------------------------------------------------------------------

    def _get_cost_map(self, workspace_id: UUID) -> dict:
        """Return severity→cost mapping, falling back to CostModel.DEFAULT_COSTS."""
        try:
            rows = (
                self.db.query(CostModel.severity, CostModel.estimated_cost_usd)
                .filter(CostModel.workspace_id == workspace_id)
                .all()
            )
            cost_map = {r.severity: float(r.estimated_cost_usd) for r in rows}
        except Exception:
            self.db.rollback()
            cost_map = {}
        # Merge defaults for missing severities
        for sev, default_cost in CostModel.DEFAULT_COSTS.items():
            cost_map.setdefault(sev, default_cost)
        return cost_map

    # ------------------------------------------------------------------
    # KQI-064 to KQI-066: Business Value Summary
    # ------------------------------------------------------------------

    def get_summary(
        self, workspace_id: UUID, period: str = "30d", use_cache: bool = True
    ) -> BusinessValueSummaryResponse:
        """Return business-value KPIs for the given period."""

        cache_key = f"kqi_business_value_{period}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return BusinessValueSummaryResponse(**cached.metric_value)

        days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
        start = datetime.utcnow() - timedelta(days=days)

        # Base: issues linked to a flow execution inside this org
        org_flows = self.db.query(DQFlow.id).filter(DQFlow.workspace_id == workspace_id).subquery()

        base_q = (
            self.db.query(Issue)
            .join(FlowExecution, Issue.flow_execution_id == FlowExecution.id)
            .filter(
                and_(
                    FlowExecution.flow_id.in_(self.db.query(org_flows.c.id)),
                    Issue.created_at >= start,
                )
            )
        )

        issues: list[Issue] = base_q.all()

        # KQI-064: issues caught
        issues_caught = len(issues)

        # KQI-065: incidents avoided = major/critical issues that were
        # resolved (resolved_at IS NOT NULL) AND never escalated to an
        # incident (no row in incident_issues for that issue).
        escalated_issue_ids = set()
        if issues:
            linked = (
                self.db.query(IncidentIssue.issue_id)
                .filter(IncidentIssue.issue_id.in_([i.id for i in issues]))
                .all()
            )
            escalated_issue_ids = {r.issue_id for r in linked}

        incidents_avoided = sum(
            1
            for i in issues
            if i.severity in MAJOR_SEVERITIES
            and i.resolved_at is not None
            and i.id not in escalated_issue_ids
        )

        # KQI-066: estimated cost saved
        cost_map = self._get_cost_map(workspace_id)
        cost_saved = sum(cost_map.get(i.severity, 0) for i in issues)

        # Trend: daily issue count for the period
        trend_map: dict[date, int] = defaultdict(int)
        for i in issues:
            day = i.created_at.date() if i.created_at else None
            if day is not None:
                trend_map[day] += 1

        # Fill gaps so the chart has a point per day
        trend: list[IssuesTrendDataPoint] = []
        current = start.date()
        today = datetime.utcnow().date()
        while current <= today:
            trend.append(IssuesTrendDataPoint(date=current, count=trend_map.get(current, 0)))
            current += timedelta(days=1)

        result = BusinessValueSummaryResponse(
            issues_caught=issues_caught,
            issues_caught_trend=trend,
            estimated_incidents_avoided=incidents_avoided,
            estimated_cost_saved_usd=round(cost_saved, 2),
            has_data=issues_caught > 0,
        )

        self._set_cache(workspace_id, cache_key, result.model_dump(mode="json"))
        return result

    # ------------------------------------------------------------------
    # Top Flows by Value
    # ------------------------------------------------------------------

    def get_top_flows(
        self, workspace_id: UUID, period: str = "30d", limit: int = 10
    ) -> TopFlowsResponse:
        """Return flows ranked by business value (issues caught × severity weight)."""

        days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
        start = datetime.utcnow() - timedelta(days=days)

        org_flows = (
            self.db.query(DQFlow.id, DQFlow.name)
            .filter(DQFlow.workspace_id == workspace_id)
            .subquery()
        )

        rows = (
            self.db.query(
                FlowExecution.flow_id,
                org_flows.c.name.label("flow_name"),
                func.count(Issue.id).label("total_issues"),
                func.sum(
                    case(
                        (Issue.severity == "critical", 1),
                        else_=0,
                    )
                ).label("critical_count"),
                Issue.severity,
            )
            .join(FlowExecution, Issue.flow_execution_id == FlowExecution.id)
            .join(org_flows, FlowExecution.flow_id == org_flows.c.id)
            .filter(Issue.created_at >= start)
            .group_by(FlowExecution.flow_id, org_flows.c.name, Issue.severity)
            .all()
        )

        cost_map = self._get_cost_map(workspace_id)

        # Aggregate per flow
        flow_agg: dict[str, dict] = {}
        for r in rows:
            fid = str(r.flow_id)
            if fid not in flow_agg:
                flow_agg[fid] = {
                    "flow_id": r.flow_id,
                    "flow_name": r.flow_name or "",
                    "issues_caught": 0,
                    "critical_issues": 0,
                    "estimated_value_usd": 0.0,
                }
            flow_agg[fid]["issues_caught"] += r.total_issues or 0
            flow_agg[fid]["critical_issues"] += r.critical_count or 0
            flow_agg[fid]["estimated_value_usd"] += (r.total_issues or 0) * cost_map.get(
                r.severity, 0
            )

        # Sort by value descending
        ranked = sorted(flow_agg.values(), key=lambda x: x["estimated_value_usd"], reverse=True)

        entries = [
            TopFlowEntry(
                flow_id=f["flow_id"],
                flow_name=f["flow_name"],
                issues_caught=f["issues_caught"],
                critical_issues=f["critical_issues"],
                estimated_value_usd=round(f["estimated_value_usd"], 2),
            )
            for f in ranked[:limit]
        ]

        return TopFlowsResponse(flows=entries)
