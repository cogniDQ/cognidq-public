"""
OperationalIntelligenceService — KQI-026 to KQI-030.

Computes execution frequency, success/failure rates, Mean Time to Recovery,
Quality Stability Index, and daily execution timelines.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Float, and_, cast, func
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.kqi import (
    CheckHeatmapCell,
    CheckHeatmapResponse,
    OperationalSummaryResponse,
    OperationalTimelineResponse,
    RecentAlertItem,
    RecentAlertsResponse,
    TimelineDataPoint,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5


class OperationalIntelligenceService:
    """Service for computing operational intelligence KQIs."""

    def __init__(self, db: Session):
        self.db = db

    def _get_date_range(self, period: str) -> tuple[datetime, datetime]:
        end = datetime.utcnow()
        days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 30)
        return end - timedelta(days=days), end

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
        self.db.merge(entry)
        self.db.commit()

    # ------------------------------------------------------------------
    # KQI-026 to KQI-030: Operational Summary
    # ------------------------------------------------------------------

    def get_summary(
        self, workspace_id: UUID, period: str = "30d", use_cache: bool = True
    ) -> OperationalSummaryResponse:
        """Return runs/day, success rate, failure rate, MTTR, QSI."""

        cache_key = f"kqi_operational_summary_{period}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return OperationalSummaryResponse(**cached.metric_value)

        start_date, end_date = self._get_date_range(period)

        # Fetch all executions in period
        executions = (
            self.db.query(
                FlowExecution.id,
                FlowExecution.flow_id,
                FlowExecution.status,
                FlowExecution.started_at,
            )
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowExecution.started_at >= start_date,
                    FlowExecution.started_at <= end_date,
                )
            )
            .order_by(FlowExecution.started_at)
            .all()
        )

        total_executions = len(executions)
        if total_executions == 0:
            result = OperationalSummaryResponse(has_data=False)
            self._set_cache(workspace_id, cache_key, result.model_dump())
            return result

        # KQI-026: Runs per day
        unique_dates = set()
        for ex in executions:
            if ex.started_at:
                unique_dates.add(ex.started_at.date())
        num_days = max(len(unique_dates), 1)
        runs_per_day = round(total_executions / num_days, 1)

        # KQI-027, KQI-028: Success/Failure rates
        completed = sum(1 for ex in executions if ex.status == "completed")
        failed = sum(1 for ex in executions if ex.status == "failed")
        success_rate = round(completed / total_executions * 100, 1)
        failure_rate = round(failed / total_executions * 100, 1)

        # KQI-029: MTTR
        mttr_hours = self._calculate_mttr(executions)

        # KQI-030: Quality Stability Index
        qsi = self._calculate_qsi(workspace_id, start_date, end_date)

        result = OperationalSummaryResponse(
            runs_per_day=runs_per_day,
            success_rate=success_rate,
            failure_rate=failure_rate,
            mttr_hours=mttr_hours,
            quality_stability_index=qsi,
            has_data=True,
        )

        self._set_cache(workspace_id, cache_key, result.model_dump())
        return result

    def _calculate_mttr(self, executions) -> float | None:
        """
        Calculate Mean Time to Recovery.

        For each flow, find consecutive (failed, completed) pairs.
        MTTR = average of (success.started_at - failure.started_at) across all flows.
        """
        # Group executions by flow_id, ordered by started_at
        by_flow = defaultdict(list)
        for ex in executions:
            by_flow[ex.flow_id].append(ex)

        recovery_times: list[float] = []

        for flow_id, flow_execs in by_flow.items():
            sorted_execs = sorted(flow_execs, key=lambda x: x.started_at or datetime.min)
            in_failure = False
            failure_start = None

            for ex in sorted_execs:
                if ex.status == "failed" and not in_failure:
                    in_failure = True
                    failure_start = ex.started_at
                elif ex.status == "completed" and in_failure:
                    if failure_start and ex.started_at:
                        delta = (ex.started_at - failure_start).total_seconds() / 3600.0
                        recovery_times.append(delta)
                    in_failure = False
                    failure_start = None

        if not recovery_times:
            return None

        return round(sum(recovery_times) / len(recovery_times), 2)

    def _calculate_qsi(self, workspace_id: UUID, start_date: datetime, end_date: datetime) -> float:
        """
        Calculate Quality Stability Index (0-100).

        QSI = max(0, 100 - stddev(pass_rates_per_execution))
        If only 1 execution, QSI = 100.
        """
        # Get average pass_rate per execution
        rows = (
            self.db.query(
                FlowExecution.id,
                func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)).label(
                    "avg_pass_rate"
                ),
            )
            .join(FlowNodeResult, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowExecution.started_at >= start_date,
                    FlowExecution.started_at <= end_date,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
            .group_by(FlowExecution.id)
            .order_by(FlowExecution.started_at.desc())
            .limit(30)
            .all()
        )

        pass_rates = [float(r.avg_pass_rate) for r in rows if r.avg_pass_rate is not None]

        if len(pass_rates) <= 1:
            return 100.0

        mean = sum(pass_rates) / len(pass_rates)
        variance = sum((p - mean) ** 2 for p in pass_rates) / len(pass_rates)
        std_dev = math.sqrt(variance)

        return round(max(0.0, 100.0 - std_dev), 1)

    # ------------------------------------------------------------------
    # Execution Timeline
    # ------------------------------------------------------------------

    def get_timeline(self, workspace_id: UUID, period: str = "30d") -> OperationalTimelineResponse:
        """Return daily execution counts by outcome for chart rendering."""

        start_date, end_date = self._get_date_range(period)

        rows = (
            self.db.query(
                func.date(FlowExecution.started_at).label("exec_date"),
                FlowExecution.status,
                func.count(FlowExecution.id).label("cnt"),
            )
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowExecution.started_at >= start_date,
                    FlowExecution.started_at <= end_date,
                )
            )
            .group_by(func.date(FlowExecution.started_at), FlowExecution.status)
            .order_by(func.date(FlowExecution.started_at))
            .all()
        )

        date_map: dict = {}
        for row in rows:
            d = row.exec_date
            if d not in date_map:
                date_map[d] = TimelineDataPoint(date=d)
            dp = date_map[d]
            if row.status == "completed":
                dp.success = row.cnt
            elif row.status == "failed":
                dp.failed = row.cnt
            else:
                dp.partial += row.cnt

        data_points = sorted(date_map.values(), key=lambda x: x.date)
        return OperationalTimelineResponse(
            data_points=data_points,
            has_data=len(data_points) > 0,
        )

    # ------------------------------------------------------------------
    # Check Performance Heatmap
    # ------------------------------------------------------------------

    def get_check_heatmap(self, workspace_id: UUID, period: str = "30d") -> CheckHeatmapResponse:
        """Return pass rate per check per day for heatmap rendering."""

        start_date, end_date = self._get_date_range(period)

        rows = (
            self.db.query(
                func.date(FlowExecution.started_at).label("exec_date"),
                FlowNodeResult.node_id,
                FlowNodeResult.result_data,
                func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)).label(
                    "avg_pass_rate"
                ),
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowExecution.started_at >= start_date,
                    FlowExecution.started_at <= end_date,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
            .group_by(
                func.date(FlowExecution.started_at),
                FlowNodeResult.node_id,
                FlowNodeResult.result_data,
            )
            .order_by(func.date(FlowExecution.started_at))
            .all()
        )

        # Aggregate: (date, check_name) → list of pass_rates
        agg: dict = {}
        check_names: dict = {}  # node_id → display name
        for row in rows:
            d = str(row.exec_date)
            node_id = row.node_id
            rd = row.result_data or {}
            check_name = rd.get("check_name") or rd.get("rule_name") or node_id
            check_names[node_id] = check_name

            key = (d, node_id)
            if key not in agg:
                agg[key] = []
            if row.avg_pass_rate is not None:
                agg[key].append(float(row.avg_pass_rate))

        cells = []
        for (d, node_id), rates in agg.items():
            if rates:
                avg_rate = round(sum(rates) / len(rates), 1)
                cells.append(
                    CheckHeatmapCell(
                        x=d,
                        y=check_names.get(node_id, node_id),
                        value=avg_rate,
                    )
                )

        return CheckHeatmapResponse(data=cells, has_data=len(cells) > 0)

    # ------------------------------------------------------------------
    # Recent Alerts
    # ------------------------------------------------------------------

    def get_recent_alerts(self, workspace_id: UUID, limit: int = 20) -> RecentAlertsResponse:
        """Return recent alerts from failed check executions."""

        from app.models.flow import DQFlow, FlowExecution, FlowNodeResult

        rows = (
            self.db.query(
                FlowExecution.started_at,
                FlowNodeResult.node_id,
                FlowNodeResult.result_data,
                FlowNodeResult.status,
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["failed", "warning"]),
                )
            )
            .order_by(FlowExecution.started_at.desc())
            .limit(limit)
            .all()
        )

        alerts = []
        for row in rows:
            rd = row.result_data or {}
            check_name = rd.get("check_name") or rd.get("rule_name") or row.node_id
            pass_rate = rd.get("pass_rate")

            # Determine severity based on pass rate
            if pass_rate is not None:
                pr = float(pass_rate)
                if pr < 50:
                    severity = "Critical"
                elif pr < 70:
                    severity = "High"
                elif pr < 90:
                    severity = "Medium"
                else:
                    severity = "Low"
            else:
                severity = "High" if row.status == "failed" else "Medium"

            message = rd.get("error_message") or rd.get("message") or f"Check {row.status}"
            if pass_rate is not None:
                message = f"Pass rate: {round(float(pass_rate), 1)}% — {message}"

            alerts.append(
                RecentAlertItem(
                    date=row.started_at.strftime("%Y-%m-%d %H:%M") if row.started_at else "",
                    check=check_name,
                    severity=severity,
                    message=message,
                    resolved=row.status != "failed",
                )
            )

        return RecentAlertsResponse(alerts=alerts, has_data=len(alerts) > 0)
