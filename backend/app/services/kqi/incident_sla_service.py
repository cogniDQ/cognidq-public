"""
IncidentSLAService — Incident SLA Analytics.

Computes SLA compliance metrics, breach analysis, compliance trends,
and enriched incident lists for the Incident SLA Dashboard.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.incident import Incident
from app.models.kqi import SLADefinition

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5

DEFAULT_SLA_HOURS: dict[str, float] = {
    "critical": 4.0,
    "major": 8.0,
    "minor": 24.0,
    "informational": 72.0,
}


class IncidentSLAService:
    """Service for computing Incident SLA analytics."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Cache helpers
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

        cache_entry = MetricsCache(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            metric_type=metric_type,
            metric_value=value,
            calculated_at=datetime.utcnow(),
        )
        self.db.add(cache_entry)
        self.db.commit()

    # ------------------------------------------------------------------
    # SLA target lookup
    # ------------------------------------------------------------------
    def _get_sla_map(self, workspace_id: UUID) -> dict[str, float]:
        """Return {severity_level: target_hours} from SlaDefinition or defaults."""
        rows = self.db.query(SLADefinition).filter(SLADefinition.workspace_id == workspace_id).all()
        sla_map = dict(DEFAULT_SLA_HOURS)
        for row in rows:
            sla_map[row.severity_level.lower()] = row.target_hours
        return sla_map

    # ------------------------------------------------------------------
    # Main endpoints
    # ------------------------------------------------------------------
    def get_metrics(
        self, workspace_id: UUID, period_days: int = 30, use_cache: bool = True
    ) -> dict:
        """SLA compliance rate, breach count, avg breach duration, MTTR."""
        cache_key = f"incident_sla_metrics_{period_days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        now = datetime.utcnow()
        since = now - timedelta(days=period_days)
        sla_map = self._get_sla_map(workspace_id)

        incidents = (
            self.db.query(Incident)
            .filter(
                and_(
                    Incident.workspace_id == workspace_id,
                    Incident.opened_at >= since,
                )
            )
            .all()
        )

        total = len(incidents)
        if total == 0:
            result = {
                "compliance_rate": 100.0,
                "breaches_count": 0,
                "avg_breach_duration_hours": 0.0,
                "mttr_hours": 0.0,
                "total_incidents": 0,
                "resolved_count": 0,
                "open_count": 0,
                "has_data": False,
            }
            self._set_cache(workspace_id, cache_key, result)
            return result

        compliant = 0
        breached = 0
        breach_durations: list[float] = []
        resolution_times: list[float] = []
        resolved_count = 0
        open_count = 0

        for inc in incidents:
            severity = (inc.severity or "minor").lower()
            target_h = sla_map.get(severity, DEFAULT_SLA_HOURS.get(severity, 24.0))

            if inc.resolved_at:
                resolved_count += 1
                resolution_h = (inc.resolved_at - inc.opened_at).total_seconds() / 3600
                resolution_times.append(resolution_h)
                if resolution_h <= target_h:
                    compliant += 1
                else:
                    breached += 1
                    breach_durations.append(resolution_h - target_h)
            else:
                open_count += 1
                elapsed_h = (now - inc.opened_at).total_seconds() / 3600
                if elapsed_h > target_h:
                    breached += 1
                    breach_durations.append(elapsed_h - target_h)
                else:
                    compliant += 1

        compliance_rate = round((compliant / total) * 100, 1) if total else 100.0
        avg_breach_duration = (
            round(sum(breach_durations) / len(breach_durations), 1) if breach_durations else 0.0
        )
        mttr = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0.0

        result = {
            "compliance_rate": compliance_rate,
            "breaches_count": breached,
            "avg_breach_duration_hours": avg_breach_duration,
            "mttr_hours": mttr,
            "total_incidents": total,
            "resolved_count": resolved_count,
            "open_count": open_count,
            "has_data": True,
        }
        self._set_cache(workspace_id, cache_key, result)
        return result

    def get_breaches_by_severity(
        self, workspace_id: UUID, period_days: int = 30, use_cache: bool = True
    ) -> dict:
        """Breach distribution grouped by severity level."""
        cache_key = f"incident_sla_breaches_severity_{period_days}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        now = datetime.utcnow()
        since = now - timedelta(days=period_days)
        sla_map = self._get_sla_map(workspace_id)

        incidents = (
            self.db.query(Incident)
            .filter(
                and_(
                    Incident.workspace_id == workspace_id,
                    Incident.opened_at >= since,
                )
            )
            .all()
        )

        breach_counts: dict[str, int] = {}
        for inc in incidents:
            severity = (inc.severity or "minor").lower()
            target_h = sla_map.get(severity, DEFAULT_SLA_HOURS.get(severity, 24.0))
            if inc.resolved_at:
                elapsed = (inc.resolved_at - inc.opened_at).total_seconds() / 3600
            else:
                elapsed = (now - inc.opened_at).total_seconds() / 3600
            if elapsed > target_h:
                label = severity.capitalize()
                breach_counts[label] = breach_counts.get(label, 0) + 1

        distribution = [
            {"name": k, "value": v} for k, v in sorted(breach_counts.items(), key=lambda x: -x[1])
        ]

        result = {"distribution": distribution, "has_data": len(distribution) > 0}
        self._set_cache(workspace_id, cache_key, result)
        return result

    def get_compliance_trend(
        self, workspace_id: UUID, weeks: int = 8, use_cache: bool = True
    ) -> dict:
        """Weekly SLA compliance rate and breach count over time."""
        cache_key = f"incident_sla_trend_{weeks}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return cached.metric_value

        now = datetime.utcnow()
        sla_map = self._get_sla_map(workspace_id)
        trend: list[dict] = []

        for w in range(weeks - 1, -1, -1):
            week_end = now - timedelta(weeks=w)
            week_start = week_end - timedelta(weeks=1)

            incidents = (
                self.db.query(Incident)
                .filter(
                    and_(
                        Incident.workspace_id == workspace_id,
                        Incident.opened_at >= week_start,
                        Incident.opened_at < week_end,
                    )
                )
                .all()
            )

            total = len(incidents)
            compliant = 0
            breaches = 0
            for inc in incidents:
                severity = (inc.severity or "minor").lower()
                target_h = sla_map.get(severity, DEFAULT_SLA_HOURS.get(severity, 24.0))
                if inc.resolved_at:
                    elapsed = (inc.resolved_at - inc.opened_at).total_seconds() / 3600
                else:
                    elapsed = (now - inc.opened_at).total_seconds() / 3600
                if elapsed <= target_h:
                    compliant += 1
                else:
                    breaches += 1

            compliance = round((compliant / total) * 100, 1) if total else 100.0
            label = week_start.strftime("%b %d")

            trend.append(
                {
                    "date": label,
                    "compliance": compliance,
                    "breaches": breaches,
                }
            )

        result = {
            "trend": trend,
            "has_data": any(t["breaches"] > 0 or t["compliance"] < 100 for t in trend),
        }
        self._set_cache(workspace_id, cache_key, result)
        return result

    def get_incidents_with_sla(
        self, workspace_id: UUID, period_days: int = 30, page: int = 1, page_size: int = 20
    ) -> dict:
        """Paginated incident list enriched with SLA target and elapsed time."""
        now = datetime.utcnow()
        since = now - timedelta(days=period_days)
        sla_map = self._get_sla_map(workspace_id)

        query = (
            self.db.query(Incident)
            .filter(
                and_(
                    Incident.workspace_id == workspace_id,
                    Incident.opened_at >= since,
                )
            )
            .order_by(Incident.opened_at.desc())
        )

        total = query.count()
        incidents = query.offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for inc in incidents:
            severity = (inc.severity or "minor").lower()
            target_h = sla_map.get(severity, DEFAULT_SLA_HOURS.get(severity, 24.0))

            if inc.resolved_at:
                elapsed_s = (inc.resolved_at - inc.opened_at).total_seconds()
            else:
                elapsed_s = (now - inc.opened_at).total_seconds()

            elapsed_h = elapsed_s / 3600
            breached = elapsed_h > target_h

            items.append(
                {
                    "id": str(inc.id),
                    "title": inc.title,
                    "severity": (inc.severity or "minor").capitalize(),
                    "priority": inc.priority or "P3",
                    "status": (inc.status or "open").capitalize(),
                    "created": inc.opened_at.isoformat() if inc.opened_at else None,
                    "sla_target_hours": target_h,
                    "elapsed_hours": round(elapsed_h, 1),
                    "breached": breached,
                    "acknowledged_at": inc.acknowledged_at.isoformat()
                    if inc.acknowledged_at
                    else None,
                    "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
                    "owner_id": str(inc.owner_id) if inc.owner_id else None,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_data": total > 0,
        }
