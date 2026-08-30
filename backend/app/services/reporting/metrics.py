"""
Metrics aggregation service for data quality reporting.

Aggregates execution results from flow node results and calculates KPIs.
"""

import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, cast, desc, func, text
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.reporting import (
    CategoryBreakdown,
    CategoryMetrics,
    OverviewMetrics,
    Scorecard,
    ScorecardDimension,
    SourceBreakdown,
    SourceMetrics,
    TrendDataPoint,
    TrendMetrics,
)

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for aggregating and calculating data quality metrics from flow executions."""

    def __init__(self, db: Session):
        self.db = db

    def _get_date_range(self, period: str = "30d") -> tuple[datetime, datetime]:
        """Convert period string to date range."""
        end_date = datetime.utcnow()

        period_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }

        if period == "all":
            start_date = datetime(2020, 1, 1)  # Or earliest record
        else:
            days = period_map.get(period, 30)
            start_date = end_date - timedelta(days=days)

        return start_date, end_date

    def get_overview_metrics(
        self,
        workspace_id: UUID,
        use_cache: bool = True,
        flow_id: UUID | None = None,
        execution_id: UUID | None = None,
    ) -> OverviewMetrics:
        """
        Get overall KPI metrics for organization or specific flow from flow node results.

        Args:
            workspace_id: Organization ID
            use_cache: Whether to use cached metrics
            flow_id: Optional flow ID to get metrics for a specific flow
            execution_id: Optional execution ID to get metrics for a specific execution

        Returns:
            OverviewMetrics with current KPIs
        """
        # Check cache first
        if use_cache:
            cached = (
                self.db.query(MetricsCache)
                .filter(
                    and_(
                        MetricsCache.workspace_id == workspace_id,
                        MetricsCache.metric_type == "overview",
                        MetricsCache.calculated_at > datetime.utcnow() - timedelta(minutes=5),
                    )
                )
                .first()
            )

            if cached:
                return OverviewMetrics(**cached.metric_value)

        # Total flows
        flows_query = self.db.query(func.count(DQFlow.id)).filter(
            DQFlow.workspace_id == workspace_id
        )
        if flow_id:
            flows_query = flows_query.filter(DQFlow.id == flow_id)
        total_flows = flows_query.scalar() or 0

        # Total check executions (count check nodes)
        executions_query = (
            self.db.query(func.count(FlowNodeResult.id))
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(
                        ["completed", "failed"]
                    ),  # Include both completed and failed checks
                )
            )
        )
        if flow_id:
            executions_query = executions_query.filter(DQFlow.id == flow_id)
        if execution_id:
            executions_query = executions_query.filter(FlowNodeResult.execution_id == execution_id)
        total_executions = executions_query.scalar() or 0

        # Calculate average pass rate from flow_node_results (use AVG of pass_rate field).
        # Cast to Float so partial-failure rates like 89.95 aren't truncated to 89.
        avg_pass_rate_query = (
            self.db.query(func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)))
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
        )
        if flow_id:
            avg_pass_rate_query = avg_pass_rate_query.filter(DQFlow.id == flow_id)
        if execution_id:
            avg_pass_rate_query = avg_pass_rate_query.filter(
                FlowNodeResult.execution_id == execution_id
            )
        avg_pass_rate = float(avg_pass_rate_query.scalar() or 0.0)

        # Count critical violations (checks with pass_rate < 80%)
        violations_query = (
            self.db.query(func.count(FlowNodeResult.id))
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    cast(FlowNodeResult.result_data["pass_rate"], Float) < 80,
                )
            )
        )
        if flow_id:
            violations_query = violations_query.filter(DQFlow.id == flow_id)
        if execution_id:
            violations_query = violations_query.filter(FlowNodeResult.execution_id == execution_id)
        critical_violations = violations_query.scalar() or 0

        # Total data sources (canonical control.data_sources, not legacy public.data_sources)
        total_data_sources = (
            self.db.execute(
                text(
                    "SELECT COUNT(*) FROM control.data_sources "
                    "WHERE workspace_id = CAST(:wid AS UUID) AND archived_at IS NULL"
                ),
                {"wid": str(workspace_id)},
            ).scalar()
            or 0
        )

        # Calculate DQ Score
        dq_score = self._calculate_dq_score(workspace_id, flow_id, execution_id)

        metrics = OverviewMetrics(
            total_rules=total_flows,  # Using flows as "rules"
            total_executions=total_executions,
            average_pass_rate=round(avg_pass_rate, 2),
            dq_score=dq_score,
            critical_violations=critical_violations,
            total_data_sources=total_data_sources,
            total_flows=total_flows,
            last_updated=datetime.utcnow(),
        )

        # Cache the result
        self._cache_metric(
            workspace_id=workspace_id, metric_type="overview", metric_value=metrics.model_dump()
        )

        return metrics

    def get_trend_metrics(
        self, workspace_id: UUID, metric_name: str = "pass_rate", period: str = "30d"
    ) -> TrendMetrics:
        """
        Get time series trend data.

        Args:
            workspace_id: Organization ID
            metric_name: Metric to track (pass_rate, execution_count, dq_score)
            period: Time period (7d, 30d, 90d, 1y, all)

        Returns:
            TrendMetrics with time series data
        """
        start_date, end_date = self._get_date_range(period)

        # Get daily aggregates
        if metric_name == "pass_rate":
            data_points = self._get_pass_rate_trend(workspace_id, start_date, end_date)
        elif metric_name == "execution_count":
            data_points = self._get_execution_count_trend(workspace_id, start_date, end_date)
        elif metric_name == "dq_score":
            data_points = self._get_dq_score_trend(workspace_id, start_date, end_date)
        else:
            data_points = []

        return TrendMetrics(metric_name=metric_name, data_points=data_points, time_period=period)

    def get_category_breakdown(
        self, workspace_id: UUID, period: str = "30d", flow_id: UUID | None = None
    ) -> CategoryBreakdown:
        """
        Get metrics breakdown by DQ category from check_type in result_data.

        Args:
            workspace_id: Organization ID
            period: Time period for metrics
            flow_id: Optional flow ID to filter by specific flow

        Returns:
            CategoryBreakdown with metrics per category
        """
        start_date, end_date = self._get_date_range(period)

        categories = []

        # Define DQ categories
        dq_categories = [
            "completeness",
            "validity",
            "uniqueness",
            "consistency",
            "timeliness",
            "accuracy",
        ]

        for category in dq_categories:
            # Count executions in this category
            executions_query = (
                self.db.query(func.count(FlowNodeResult.id))
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.status.in_(["completed", "failed"]),
                        FlowNodeResult.result_data["check_type"].astext == category,
                        FlowNodeResult.created_at >= start_date,
                        FlowNodeResult.created_at <= end_date,
                    )
                )
            )
            if flow_id:
                executions_query = executions_query.filter(DQFlow.id == flow_id)
            total_executions = executions_query.scalar() or 0

            # Calculate pass rate as AVG(pass_rate) — matches get_overview_metrics().
            # NOTE: do NOT use COUNT(rows_failed==0) / COUNT(*); a check that scored
            # 89.95% with any failed rows would otherwise be counted as 0% passed.
            avg_pass_rate_query = (
                self.db.query(func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)))
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.status.in_(["completed", "failed"]),
                        FlowNodeResult.result_data["check_type"].astext == category,
                        FlowNodeResult.created_at >= start_date,
                        FlowNodeResult.created_at <= end_date,
                    )
                )
            )
            if flow_id:
                avg_pass_rate_query = avg_pass_rate_query.filter(DQFlow.id == flow_id)
            pass_rate = float(avg_pass_rate_query.scalar() or 0.0)

            # Average execution time
            avg_time_query = (
                self.db.query(func.avg(FlowNodeResult.duration_seconds))
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.status.in_(["completed", "failed"]),
                        FlowNodeResult.result_data["check_type"].astext == category,
                        FlowNodeResult.created_at >= start_date,
                        FlowNodeResult.created_at <= end_date,
                    )
                )
            )
            if flow_id:
                avg_time_query = avg_time_query.filter(DQFlow.id == flow_id)
            avg_time = avg_time_query.scalar() or 0.0

            # Count unique flows for this category (as "rules")
            rules_query = (
                self.db.query(func.count(func.distinct(DQFlow.id)))
                .join(FlowExecution, DQFlow.id == FlowExecution.flow_id)
                .join(FlowNodeResult, FlowExecution.id == FlowNodeResult.execution_id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.result_data["check_type"].astext == category,
                    )
                )
            )
            if flow_id:
                rules_query = rules_query.filter(DQFlow.id == flow_id)
            total_rules = rules_query.scalar() or 0

            if total_executions > 0:
                categories.append(
                    CategoryMetrics(
                        category=category,
                        total_rules=total_rules,
                        total_executions=total_executions,
                        pass_rate=round(pass_rate, 2),
                        avg_execution_time=round(float(avg_time), 2),
                    )
                )

        return CategoryBreakdown(categories=categories, total=len(categories))

    def get_source_breakdown(
        self, workspace_id: UUID, period: str = "30d", flow_id: UUID | None = None
    ) -> SourceBreakdown:
        """
        Get metrics breakdown by data source.

        Args:
            workspace_id: Organization ID
            period: Time period for metrics
            flow_id: Optional flow ID to filter by specific flow

        Returns:
            SourceBreakdown with metrics per source
        """
        start_date, end_date = self._get_date_range(period)

        # Get all data sources from canonical schema (control.data_sources). The
        # legacy ORM model targets public.data_sources which is not used here.
        _rows = self.db.execute(
            text(
                "SELECT data_source_id AS id, source_name AS name "
                "FROM control.data_sources "
                "WHERE workspace_id = CAST(:wid AS UUID) AND archived_at IS NULL"
            ),
            {"wid": str(workspace_id)},
        ).fetchall()
        sources = [SimpleNamespace(id=r.id, name=r.name) for r in _rows]

        source_metrics = []

        for source in sources:
            # Count flows using this source
            flows_query = (
                self.db.query(func.count(func.distinct(DQFlow.id)))
                .join(FlowExecution, DQFlow.id == FlowExecution.flow_id)
                .join(FlowNodeResult, FlowExecution.id == FlowNodeResult.execution_id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "source",
                        FlowNodeResult.result_data["output_data"]["data_source"]["id"].astext
                        == str(source.id),
                    )
                )
            )

            if flow_id:
                flows_query = flows_query.filter(DQFlow.id == flow_id)

            total_rules = flows_query.scalar() or 0

            # Count check executions for this source
            executions_query = (
                self.db.query(func.count(FlowNodeResult.id))
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.status.in_(["completed", "failed"]),
                        FlowNodeResult.result_data["output_data"]["data_source"]["id"].astext
                        == str(source.id),
                        FlowNodeResult.created_at >= start_date,
                        FlowNodeResult.created_at <= end_date,
                    )
                )
            )

            if flow_id:
                executions_query = executions_query.filter(DQFlow.id == flow_id)

            total_executions = executions_query.scalar() or 0

            # Calculate pass rate as AVG(pass_rate) — matches get_overview_metrics().
            avg_pass_rate_query = (
                self.db.query(func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)))
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.status.in_(["completed", "failed"]),
                        FlowNodeResult.result_data["output_data"]["data_source"]["id"].astext
                        == str(source.id),
                        FlowNodeResult.created_at >= start_date,
                        FlowNodeResult.created_at <= end_date,
                    )
                )
            )

            if flow_id:
                avg_pass_rate_query = avg_pass_rate_query.filter(DQFlow.id == flow_id)

            pass_rate = float(avg_pass_rate_query.scalar() or 0.0)

            # Last execution
            last_exec_query = (
                self.db.query(FlowExecution.started_at)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .join(FlowNodeResult, FlowExecution.id == FlowNodeResult.execution_id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.result_data["output_data"]["data_source"]["id"].astext
                        == str(source.id),
                    )
                )
            )

            if flow_id:
                last_exec_query = last_exec_query.filter(DQFlow.id == flow_id)

            last_execution = last_exec_query.order_by(desc(FlowExecution.started_at)).first()

            # Determine health status
            if pass_rate >= 95:
                health_status = "healthy"
            elif pass_rate >= 80:
                health_status = "warning"
            else:
                health_status = "critical"

            # Only include sources that have been used
            if total_executions > 0:
                source_metrics.append(
                    SourceMetrics(
                        source_id=str(source.id),
                        source_name=source.name,
                        total_rules=total_rules,
                        total_executions=total_executions,
                        pass_rate=round(pass_rate, 2),
                        last_execution=last_execution[0] if last_execution else None,
                        health_status=health_status,
                    )
                )

        return SourceBreakdown(sources=source_metrics, total=len(source_metrics))

    def get_scorecard(self, workspace_id: UUID, period: str = "30d") -> Scorecard:
        """
        Calculate data quality scorecard with dimensional breakdown.

        Args:
            workspace_id: Organization ID
            period: Time period for scorecard

        Returns:
            Scorecard with overall score and dimension breakdown
        """
        # Get current-period category metrics
        category_breakdown = self.get_category_breakdown(workspace_id, period)

        # Get previous-period averages by category for trend comparison.
        prev_pass_rate_by_cat = self._get_prev_period_pass_rate_by_category(workspace_id, period)
        prev_overall = self._get_prev_period_overall_pass_rate(workspace_id, period)

        dimensions = []
        total_score = 0.0
        total_weight = 0.0
        total_issues = 0
        critical_issues = 0

        # Weight for each dimension. Sum = 1.0 so weighted mean is bounded 0..100
        # when every dimension has data.
        dimension_weights = {
            "completeness": 0.25,
            "validity": 0.20,
            "uniqueness": 0.20,
            "consistency": 0.15,
            "timeliness": 0.10,
            "accuracy": 0.10,
        }

        for cat_metric in category_breakdown.categories:
            weight = dimension_weights.get(cat_metric.category, 0.1)
            score = cat_metric.pass_rate

            # Count issues (failed executions)
            issues = cat_metric.total_executions - int(cat_metric.total_executions * score / 100)
            if score < 80:
                critical_issues += issues

            prev_score = prev_pass_rate_by_cat.get(cat_metric.category)
            trend = self._trend_from_delta(score, prev_score)

            dimensions.append(
                ScorecardDimension(
                    dimension=cat_metric.category,
                    score=round(score, 2),
                    weight=weight,
                    issues_count=issues,
                    trend=trend,
                )
            )

            total_score += score * weight
            total_weight += weight
            total_issues += issues

        # Weighted mean — divide by sum of weights actually present so absent
        # dimensions don't drag the score down to 0.
        overall_score = total_score / total_weight if total_weight > 0 else 0.0
        overall_trend = self._trend_from_delta(overall_score, prev_overall)

        return Scorecard(
            overall_score=round(overall_score, 2),
            dimensions=dimensions,
            total_issues=total_issues,
            critical_issues=critical_issues,
            trend=overall_trend,
            last_updated=datetime.utcnow(),
        )

    # ========== Helper Methods ==========

    @staticmethod
    def _trend_from_delta(curr: float, prev: float | None, threshold: float = 1.0) -> str:
        """Classify a change between two pass-rate values as up/down/stable.

        ``threshold`` is in percentage points: changes within ±1pp are reported
        as ``"stable"`` to avoid jitter. Returns ``"stable"`` when no prior
        value is available so callers don't have to guard against ``None``.
        """
        if prev is None:
            return "stable"
        diff = curr - prev
        if diff > threshold:
            return "up"
        if diff < -threshold:
            return "down"
        return "stable"

    def _previous_period_window(self, period: str) -> tuple[datetime, datetime]:
        """Return the (start, end) of the period immediately preceding ``period``.

        For ``period="30d"`` the previous window is the 30 days ending exactly
        when the current window begins.
        """
        cur_start, _cur_end = self._get_date_range(period)
        period_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        days = period_map.get(period, 30)
        prev_end = cur_start
        prev_start = prev_end - timedelta(days=days)
        return prev_start, prev_end

    def _get_prev_period_pass_rate_by_category(
        self, workspace_id: UUID, period: str
    ) -> dict[str, float]:
        """Return ``{category: avg_pass_rate}`` for the previous period."""
        prev_start, prev_end = self._previous_period_window(period)
        rows = (
            self.db.query(
                FlowNodeResult.result_data["check_type"].astext.label("category"),
                func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)).label(
                    "avg_pass_rate"
                ),
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.created_at >= prev_start,
                    FlowNodeResult.created_at < prev_end,
                )
            )
            .group_by(FlowNodeResult.result_data["check_type"].astext)
            .all()
        )
        return {r.category: float(r.avg_pass_rate) for r in rows if r.avg_pass_rate is not None}

    def _get_prev_period_overall_pass_rate(self, workspace_id: UUID, period: str) -> float | None:
        """Return overall AVG(pass_rate) for the previous period, or None if no data."""
        prev_start, prev_end = self._previous_period_window(period)
        value = (
            self.db.query(func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)))
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.created_at >= prev_start,
                    FlowNodeResult.created_at < prev_end,
                )
            )
            .scalar()
        )
        return float(value) if value is not None else None

    def _calculate_dq_score(
        self, workspace_id: UUID, flow_id: UUID | None = None, execution_id: UUID | None = None
    ) -> float:
        """Calculate overall DQ score (0-100) using average pass rate."""
        avg_score_query = (
            self.db.query(func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)))
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
        )
        if flow_id:
            avg_score_query = avg_score_query.filter(DQFlow.id == flow_id)
        if execution_id:
            avg_score_query = avg_score_query.filter(FlowNodeResult.execution_id == execution_id)

        score = float(avg_score_query.scalar() or 0.0)
        return round(score, 2)

    def _get_pass_rate_trend(
        self, workspace_id: UUID, start_date: datetime, end_date: datetime
    ) -> list[TrendDataPoint]:
        """Get daily pass rate trend from flow executions.

        Uses AVG(pass_rate) per day (matches get_overview_metrics()) instead of
        COUNT(rows_failed==0) / COUNT(*), and includes both "completed" and
        "failed" node statuses for consistency with the overview KPI.
        """
        query = (
            self.db.query(
                func.date(FlowNodeResult.created_at).label("date"),
                func.avg(cast(FlowNodeResult.result_data["pass_rate"], Float)).label(
                    "avg_pass_rate"
                ),
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.created_at >= start_date,
                    FlowNodeResult.created_at <= end_date,
                )
            )
            .group_by(func.date(FlowNodeResult.created_at))
            .order_by("date")
        )

        results = query.all()

        data_points = []
        for row in results:
            pass_rate = float(row.avg_pass_rate or 0.0)
            data_points.append(
                TrendDataPoint(
                    timestamp=datetime.combine(row.date, datetime.min.time()),
                    value=round(pass_rate, 2),
                )
            )

        return data_points

    def _get_execution_count_trend(
        self, workspace_id: UUID, start_date: datetime, end_date: datetime
    ) -> list[TrendDataPoint]:
        """Get daily execution count trend from flow executions."""
        query = (
            self.db.query(
                func.date(FlowExecution.started_at).label("date"),
                func.count(FlowExecution.id).label("count"),
            )
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowExecution.started_at >= start_date,
                    FlowExecution.started_at <= end_date,
                )
            )
            .group_by(func.date(FlowExecution.started_at))
            .order_by("date")
        )

        results = query.all()

        data_points = []
        for row in results:
            data_points.append(
                TrendDataPoint(
                    timestamp=datetime.combine(row.date, datetime.min.time()),
                    value=float(row.count),
                )
            )

        return data_points

    def _get_dq_score_trend(
        self, workspace_id: UUID, start_date: datetime, end_date: datetime
    ) -> list[TrendDataPoint]:
        """Get daily DQ score trend."""
        # Similar to pass rate trend
        return self._get_pass_rate_trend(workspace_id, start_date, end_date)

    def _cache_metric(
        self,
        workspace_id: UUID,
        metric_type: str,
        metric_value: dict[str, Any],
        metric_key: str | None = None,
        time_period: str | None = None,
    ):
        """Cache calculated metric for performance."""
        try:
            cache_entry = MetricsCache(
                workspace_id=workspace_id,
                metric_type=metric_type,
                metric_key=metric_key,
                metric_value=metric_value,
                time_period=time_period,
            )
            self.db.add(cache_entry)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to cache metric: {e}")
            self.db.rollback()

    def get_column_metrics(
        self, workspace_id: UUID, flow_id: UUID | None = None, execution_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """
        Get metrics aggregated by column.

        Args:
            workspace_id: Organization ID
            flow_id: Optional flow ID to filter
            execution_id: Optional execution ID to filter

        Returns:
            List of column metrics with pass rates and check counts
        """
        # Get all check results
        query = (
            self.db.query(FlowNodeResult)
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
        )

        if flow_id:
            query = query.filter(DQFlow.id == flow_id)
        if execution_id:
            query = query.filter(FlowNodeResult.execution_id == execution_id)

        results = query.all()

        logger.info(
            f"🔍 Column Metrics Query returned {len(results)} results for execution_id={execution_id}, flow_id={flow_id}"
        )

        # Aggregate by column
        column_data = {}
        for result in results:
            data = result.result_data or {}
            columns = data.get("checked_columns", [])
            pass_rate = data.get("pass_rate", 0)
            rows_scanned = data.get("rows_scanned", 0)
            rows_failed = data.get("rows_failed", 0)
            check_type = data.get("check_type", "unknown")

            logger.debug(
                f"  Node {result.node_id}: {len(columns)} columns, pass_rate={pass_rate}, check_type={check_type}"
            )
            logger.debug(f"  Columns: {columns}")

            for column in columns:
                if column not in column_data:
                    column_data[column] = {
                        "column_name": column,
                        "checks": [],
                        "total_rows_scanned": 0,
                        "total_rows_failed": 0,
                        "check_count": 0,
                    }

                column_data[column]["checks"].append(
                    {
                        "check_type": check_type,
                        "pass_rate": pass_rate,
                        "rows_scanned": rows_scanned,
                        "rows_failed": rows_failed,
                    }
                )
                column_data[column]["total_rows_scanned"] += rows_scanned
                column_data[column]["total_rows_failed"] += rows_failed
                column_data[column]["check_count"] += 1

        # Calculate aggregate metrics per column
        column_metrics = []
        for column_name, data in column_data.items():
            avg_pass_rate = (
                sum(c["pass_rate"] for c in data["checks"]) / len(data["checks"])
                if data["checks"]
                else 0
            )

            # Determine status based on average pass rate
            if avg_pass_rate >= 95:
                status = "healthy"
            elif avg_pass_rate >= 80:
                status = "warning"
            else:
                status = "critical"

            column_metrics.append(
                {
                    "column_name": column_name,
                    "check_count": data["check_count"],
                    "avg_pass_rate": round(avg_pass_rate, 2),
                    "total_rows_scanned": data["total_rows_scanned"],
                    "total_rows_failed": data["total_rows_failed"],
                    "status": status,
                    "checks": data["checks"],
                }
            )

        # Sort by avg_pass_rate ascending (worst first)
        column_metrics.sort(key=lambda x: x["avg_pass_rate"])

        return column_metrics

    def get_dimensional_breakdown(
        self, workspace_id: UUID, flow_id: UUID | None = None, execution_id: UUID | None = None
    ) -> dict[str, Any]:
        """
        Get metrics aggregated by dimension type (structural, semantic, statistical).

        Dimension mapping:
        - Structural: completeness, uniqueness, consistency
        - Semantic: validity, conformity, accuracy
        - Statistical: distribution, outliers, patterns

        Args:
            workspace_id: Organization ID
            flow_id: Optional flow ID to filter
            execution_id: Optional execution ID to filter

        Returns:
            Dictionary with dimensional breakdown
        """
        # Map check types to dimension categories
        dimension_map = {
            "completeness": "structural",
            "uniqueness": "structural",
            "consistency": "structural",
            "validity": "semantic",
            "conformity": "semantic",
            "accuracy": "semantic",
            "business_rule": "semantic",
            "distribution": "statistical",
            "outliers": "statistical",
            "patterns": "statistical",
        }

        # Get all check results
        query = (
            self.db.query(FlowNodeResult)
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                )
            )
        )

        if flow_id:
            query = query.filter(DQFlow.id == flow_id)
        if execution_id:
            query = query.filter(FlowNodeResult.execution_id == execution_id)

        results = query.all()

        logger.info(
            f"🔍 Dimensional Breakdown Query returned {len(results)} results for execution_id={execution_id}, flow_id={flow_id}"
        )

        # Aggregate by check type and dimension
        check_type_data = {}
        dimension_data = {
            "structural": {"checks": [], "total_rows": 0, "failed_rows": 0},
            "semantic": {"checks": [], "total_rows": 0, "failed_rows": 0},
            "statistical": {"checks": [], "total_rows": 0, "failed_rows": 0},
        }

        for result in results:
            data = result.result_data or {}
            check_type = data.get("check_type", "unknown")
            pass_rate = data.get("pass_rate", 0)
            rows_scanned = data.get("rows_scanned", 0)
            rows_failed = data.get("rows_failed", 0)

            logger.debug(f"  Check: {check_type}, pass_rate={pass_rate}, rows={rows_scanned}")

            # Aggregate by check type
            if check_type not in check_type_data:
                check_type_data[check_type] = {
                    "check_type": check_type,
                    "check_count": 0,
                    "total_rows_scanned": 0,
                    "total_rows_failed": 0,
                    "pass_rates": [],
                }

            check_type_data[check_type]["check_count"] += 1
            check_type_data[check_type]["total_rows_scanned"] += rows_scanned
            check_type_data[check_type]["total_rows_failed"] += rows_failed
            check_type_data[check_type]["pass_rates"].append(pass_rate)

            # Aggregate by dimension category
            dimension = dimension_map.get(check_type, "structural")
            dimension_data[dimension]["checks"].append(pass_rate)
            dimension_data[dimension]["total_rows"] += rows_scanned
            dimension_data[dimension]["failed_rows"] += rows_failed

        # Calculate metrics per check type
        check_type_metrics = []
        for check_type, data in check_type_data.items():
            avg_pass_rate = (
                sum(data["pass_rates"]) / len(data["pass_rates"]) if data["pass_rates"] else 0
            )
            dimension = dimension_map.get(check_type, "structural")

            check_type_metrics.append(
                {
                    "check_type": check_type,
                    "dimension": dimension,
                    "check_count": data["check_count"],
                    "avg_pass_rate": round(avg_pass_rate, 2),
                    "total_rows_scanned": data["total_rows_scanned"],
                    "total_rows_failed": data["total_rows_failed"],
                }
            )

        # Calculate metrics per dimension
        dimension_metrics = []
        for dimension, data in dimension_data.items():
            if data["checks"]:
                avg_pass_rate = sum(data["checks"]) / len(data["checks"])
                check_count = len(data["checks"])
            else:
                avg_pass_rate = 0
                check_count = 0

            dimension_metrics.append(
                {
                    "dimension": dimension,
                    "check_count": check_count,
                    "avg_pass_rate": round(avg_pass_rate, 2),
                    "total_rows_scanned": data["total_rows"],
                    "total_rows_failed": data["failed_rows"],
                    "status": "healthy"
                    if avg_pass_rate >= 95
                    else "warning"
                    if avg_pass_rate >= 80
                    else "critical",
                }
            )

        return {"by_dimension": dimension_metrics, "by_check_type": check_type_metrics}
