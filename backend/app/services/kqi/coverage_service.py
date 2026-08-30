"""
CoverageService — KQI-001 to KQI-019.

Computes dataset, flow, and check inventory metrics,
governance maturity percentages, and coverage growth trends.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import String, and_, cast, distinct, func
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.datasource import DataSource
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.models.kqi import KQISnapshot, SLADefinition
from app.schemas.kqi import (
    CheckInventoryResponse,
    CoverageInventoryResponse,
    CoverageTrendDataPoint,
    CoverageTrendResponse,
    DimensionCount,
    GovernanceMaturityResponse,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5


class CoverageService:
    """Service for computing coverage and inventory KQIs."""

    def __init__(self, db: Session):
        self.db = db

    def _get_cached(self, workspace_id: UUID, metric_type: str):
        """Check MetricsCache for a recent cached value."""
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
        """Write a value into MetricsCache."""
        import uuid as _uuid

        cache_entry = MetricsCache(
            id=_uuid.uuid4(),
            workspace_id=workspace_id,
            metric_type=metric_type,
            metric_value=value,
            calculated_at=datetime.utcnow(),
        )
        self.db.merge(cache_entry)
        self.db.commit()

    # ------------------------------------------------------------------
    # KQI-001 to KQI-010: Dataset & Flow Inventory
    # ------------------------------------------------------------------

    def get_inventory(
        self, workspace_id: UUID, use_cache: bool = True
    ) -> CoverageInventoryResponse:
        """Return combined dataset and flow inventory metrics."""

        if use_cache:
            cached = self._get_cached(workspace_id, "kqi_coverage_inventory")
            if cached:
                return CoverageInventoryResponse(**cached.metric_value)

        # KQI-001: Total datasets
        total_datasets = (
            self.db.query(func.count(DataSource.id))
            .filter(DataSource.workspace_id == workspace_id)
            .scalar()
            or 0
        )

        # KQI-002: Datasets analyzed (distinct sources referenced in check results)
        analyzed_subq = (
            self.db.query(
                distinct(
                    func.coalesce(
                        FlowNodeResult.result_data["dataset"].astext,
                        FlowNodeResult.result_data["table_name"].astext,
                        FlowNodeResult.result_data["source_name"].astext,
                    )
                )
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.result_data.isnot(None),
                )
            )
        )
        datasets_analyzed = analyzed_subq.count()
        datasets_analyzed_pct = round(
            min((datasets_analyzed / total_datasets * 100) if total_datasets > 0 else 0, 100.0), 1
        )

        # KQI-003: Datasets analyzed in last 24 hours
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        datasets_analyzed_24h = (
            self.db.query(
                distinct(
                    func.coalesce(
                        FlowNodeResult.result_data["dataset"].astext,
                        FlowNodeResult.result_data["table_name"].astext,
                        FlowNodeResult.result_data["source_name"].astext,
                    )
                )
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.status.in_(["completed", "failed"]),
                    FlowNodeResult.result_data.isnot(None),
                    FlowNodeResult.created_at >= cutoff_24h,
                )
            )
            .count()
        )

        # KQI-004: Datasets without flows
        datasets_without_flows = max(0, total_datasets - datasets_analyzed)

        # KQI-005: Total flows
        total_flows = (
            self.db.query(func.count(DQFlow.id))
            .filter(DQFlow.workspace_id == workspace_id)
            .scalar()
            or 0
        )

        # KQI-006: Active flows
        active_flows = (
            self.db.query(func.count(DQFlow.id))
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    DQFlow.status == "active",
                )
            )
            .scalar()
            or 0
        )
        active_flows_pct = round((active_flows / total_flows * 100) if total_flows > 0 else 0, 1)

        # KQI-007: Paused flows
        paused_flows = (
            self.db.query(func.count(DQFlow.id))
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    DQFlow.status == "inactive",
                )
            )
            .scalar()
            or 0
        )

        # KQI-008: Failed flows (flows whose LAST execution has status='failed')
        # Subquery: latest execution per flow
        latest_exec_subq = (
            self.db.query(
                FlowExecution.flow_id,
                func.max(FlowExecution.started_at).label("max_started"),
            )
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(DQFlow.workspace_id == workspace_id)
            .group_by(FlowExecution.flow_id)
            .subquery()
        )
        failed_flows = (
            self.db.query(func.count(distinct(FlowExecution.flow_id)))
            .join(
                latest_exec_subq,
                and_(
                    FlowExecution.flow_id == latest_exec_subq.c.flow_id,
                    FlowExecution.started_at == latest_exec_subq.c.max_started,
                ),
            )
            .filter(FlowExecution.status == "failed")
            .scalar()
            or 0
        )

        # KQI-009: Avg datasets per flow
        # Count distinct source_name per flow from check results
        datasets_per_flow_subq = (
            self.db.query(
                DQFlow.id.label("flow_id"),
                func.count(
                    distinct(
                        func.coalesce(
                            FlowNodeResult.result_data["dataset"].astext,
                            FlowNodeResult.result_data["table_name"].astext,
                            FlowNodeResult.result_data["source_name"].astext,
                        )
                    )
                ).label("ds_count"),
            )
            .join(FlowExecution, FlowExecution.flow_id == DQFlow.id)
            .join(FlowNodeResult, FlowNodeResult.execution_id == FlowExecution.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type.in_(["check", "source"]),
                    FlowNodeResult.result_data.isnot(None),
                )
            )
            .group_by(DQFlow.id)
            .subquery()
        )
        avg_datasets = self.db.query(func.avg(datasets_per_flow_subq.c.ds_count)).scalar()
        avg_datasets_per_flow = round(float(avg_datasets or 0), 1)

        # KQI-010: Avg checks per flow
        checks_per_flow_subq = (
            self.db.query(
                DQFlow.id.label("flow_id"),
                func.count(distinct(FlowNodeResult.node_id)).label("check_count"),
            )
            .join(FlowExecution, FlowExecution.flow_id == DQFlow.id)
            .join(FlowNodeResult, FlowNodeResult.execution_id == FlowExecution.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                )
            )
            .group_by(DQFlow.id)
            .subquery()
        )
        avg_checks = self.db.query(func.avg(checks_per_flow_subq.c.check_count)).scalar()
        avg_checks_per_flow = round(float(avg_checks or 0), 1)

        has_data = total_datasets > 0 or total_flows > 0

        result = CoverageInventoryResponse(
            total_datasets=total_datasets,
            datasets_analyzed=datasets_analyzed,
            datasets_analyzed_pct=datasets_analyzed_pct,
            datasets_analyzed_24h=datasets_analyzed_24h,
            datasets_without_flows=datasets_without_flows,
            total_flows=total_flows,
            active_flows=active_flows,
            active_flows_pct=active_flows_pct,
            paused_flows=paused_flows,
            failed_flows=failed_flows,
            avg_datasets_per_flow=avg_datasets_per_flow,
            avg_checks_per_flow=avg_checks_per_flow,
            has_data=has_data,
        )

        self._set_cache(workspace_id, "kqi_coverage_inventory", result.model_dump())
        return result

    # ------------------------------------------------------------------
    # KQI-011 to KQI-013: Check Inventory
    # ------------------------------------------------------------------

    def get_check_inventory(
        self, workspace_id: UUID, use_cache: bool = True
    ) -> CheckInventoryResponse:
        """Return check counts by dimension and standard vs custom."""

        if use_cache:
            cached = self._get_cached(workspace_id, "kqi_coverage_checks")
            if cached:
                return CheckInventoryResponse(**cached.metric_value)

        # KQI-011: Total distinct check nodes across all flows (by flow_id+node_id)
        total_checks = (
            self.db.query(
                func.count(
                    distinct(
                        func.concat(
                            cast(FlowExecution.flow_id, String), ":", FlowNodeResult.node_id
                        )
                    )
                )
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                )
            )
            .scalar()
            or 0
        )

        # KQI-012: Checks by dimension (extract check_type from result_data)
        dimension_rows = (
            self.db.query(
                FlowNodeResult.result_data["check_type"].astext.label("dimension"),
                func.count(
                    distinct(
                        func.concat(
                            cast(FlowExecution.flow_id, String), ":", FlowNodeResult.node_id
                        )
                    )
                ).label("cnt"),
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(
                and_(
                    DQFlow.workspace_id == workspace_id,
                    FlowNodeResult.node_type == "check",
                    FlowNodeResult.result_data.isnot(None),
                    FlowNodeResult.result_data["check_type"].astext.isnot(None),
                )
            )
            .group_by(FlowNodeResult.result_data["check_type"].astext)
            .all()
        )
        checks_by_dimension = [
            DimensionCount(dimension=row.dimension, count=row.cnt)
            for row in dimension_rows
            if row.dimension
        ]

        # KQI-013: Standard vs custom — treat known dimensions as standard
        standard_dimensions = {
            "completeness",
            "validity",
            "uniqueness",
            "consistency",
            "timeliness",
            "accuracy",
            "conformity",
            "reconciliation",
        }
        standard_checks = sum(
            d.count for d in checks_by_dimension if d.dimension in standard_dimensions
        )
        custom_checks = total_checks - standard_checks
        standard_pct = round((standard_checks / total_checks * 100) if total_checks > 0 else 0, 1)

        result = CheckInventoryResponse(
            total_checks=total_checks,
            checks_by_dimension=checks_by_dimension,
            standard_checks=standard_checks,
            custom_checks=max(0, custom_checks),
            standard_checks_pct=standard_pct,
            has_data=total_checks > 0,
        )

        self._set_cache(workspace_id, "kqi_coverage_checks", result.model_dump())
        return result

    # ------------------------------------------------------------------
    # KQI-014 to KQI-018: Governance Maturity
    # ------------------------------------------------------------------

    def get_governance_maturity(
        self, workspace_id: UUID, use_cache: bool = True
    ) -> GovernanceMaturityResponse:
        """Return metadata coverage percentages for datasets."""

        if use_cache:
            cached = self._get_cached(workspace_id, "kqi_coverage_governance")
            if cached:
                return GovernanceMaturityResponse(**cached.metric_value)

        total_datasets = (
            self.db.query(func.count(DataSource.id))
            .filter(DataSource.workspace_id == workspace_id)
            .scalar()
            or 0
        )

        if total_datasets == 0:
            result = GovernanceMaturityResponse()
        else:
            # KQI-014 through KQI-016: Check metadata fields on DataSource
            # connection_config is JSON type; use cast to JSONB for subscript operators
            config_jsonb = cast(DataSource.connection_config, PG_JSONB)

            def _pct_with_field(field_name: str) -> float:
                """Count sources where connection_config has a non-empty field."""
                count = (
                    self.db.query(func.count(DataSource.id))
                    .filter(
                        and_(
                            DataSource.workspace_id == workspace_id,
                            config_jsonb.has_key(field_name),
                            func.jsonb_extract_path_text(config_jsonb, field_name) != "",
                        )
                    )
                    .scalar()
                    or 0
                )
                return round(count / total_datasets * 100, 1) if total_datasets > 0 else 0.0

            datasets_with_owner_pct = _pct_with_field("owner")
            datasets_with_criticality_pct = _pct_with_field("criticality")
            datasets_with_domain_pct = _pct_with_field("domain")

            # KQI-017: Datasets with thresholds (have at least one check with threshold)
            result_jsonb = cast(FlowNodeResult.result_data, PG_JSONB)
            datasets_with_thresholds = (
                self.db.query(
                    func.count(
                        distinct(
                            func.coalesce(
                                func.jsonb_extract_path_text(result_jsonb, "dataset"),
                                func.jsonb_extract_path_text(result_jsonb, "table_name"),
                                func.jsonb_extract_path_text(result_jsonb, "source_name"),
                            )
                        )
                    )
                )
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.result_data.isnot(None),
                        result_jsonb.has_key("threshold"),
                    )
                )
                .scalar()
                or 0
            )
            datasets_with_thresholds_pct = round(
                min(datasets_with_thresholds / total_datasets * 100, 100.0), 1
            )

            # KQI-018: Checks with SLA (count checks that have linked SLA definitions)
            total_checks = (
                self.db.query(
                    func.count(
                        distinct(
                            func.concat(
                                cast(FlowExecution.flow_id, String), ":", FlowNodeResult.node_id
                            )
                        )
                    )
                )
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                    )
                )
                .scalar()
                or 0
            )
            # SLA coverage based on SLA definitions existing for the workspace
            try:
                sla_count = self.db.query(func.count(SLADefinition.id)).scalar() or 0
                checks_with_sla_pct = (
                    round(min(sla_count / max(total_checks, 1) * 100, 100.0), 1)
                    if sla_count > 0
                    else 0.0
                )
            except Exception:
                self.db.rollback()
                logger.debug("sla_definitions table not available")
                checks_with_sla_pct = 0.0

            result = GovernanceMaturityResponse(
                datasets_with_owner_pct=datasets_with_owner_pct,
                datasets_with_criticality_pct=datasets_with_criticality_pct,
                datasets_with_domain_pct=datasets_with_domain_pct,
                datasets_with_thresholds_pct=datasets_with_thresholds_pct,
                checks_with_sla_pct=checks_with_sla_pct,
                has_data=True,
            )

        self._set_cache(workspace_id, "kqi_coverage_governance", result.model_dump())
        return result

    # ------------------------------------------------------------------
    # KQI-019: Coverage Growth Trend
    # ------------------------------------------------------------------

    def get_coverage_trend(self, workspace_id: UUID, period: str = "30d") -> CoverageTrendResponse:
        """Return historical coverage growth from execution data."""

        period_days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 30)
        start_date = datetime.utcnow().date() - timedelta(days=period_days)

        # Try KQI snapshots first, fall back to execution-based trend
        try:
            snapshots = (
                self.db.query(
                    KQISnapshot.snapshot_date,
                    KQISnapshot.kqi_id,
                    KQISnapshot.value,
                )
                .filter(
                    and_(
                        KQISnapshot.workspace_id == workspace_id,
                        KQISnapshot.kqi_id.in_(["KQI-002", "KQI-005", "KQI-011"]),
                        KQISnapshot.snapshot_date >= start_date,
                    )
                )
                .order_by(KQISnapshot.snapshot_date)
                .all()
            )
        except Exception:
            self.db.rollback()
            logger.debug("kqi_snapshots table not available, using execution-based trend")
            snapshots = []

        if snapshots:
            # Group by date from snapshots
            date_map: dict = {}
            for snap in snapshots:
                if snap.snapshot_date not in date_map:
                    date_map[snap.snapshot_date] = CoverageTrendDataPoint(date=snap.snapshot_date)
                dp = date_map[snap.snapshot_date]
                if snap.kqi_id == "KQI-002":
                    dp.datasets = int(snap.value)
                elif snap.kqi_id == "KQI-005":
                    dp.flows = int(snap.value)
                elif snap.kqi_id == "KQI-011":
                    dp.checks = int(snap.value)
            data_points = sorted(date_map.values(), key=lambda x: x.date)
        else:
            # Fallback: build trend from flow_executions by day
            result_jsonb = cast(FlowNodeResult.result_data, PG_JSONB)
            rows = (
                self.db.query(
                    func.date_trunc("day", FlowExecution.started_at).label("day"),
                    func.count(
                        distinct(
                            func.coalesce(
                                func.jsonb_extract_path_text(result_jsonb, "dataset"),
                                func.jsonb_extract_path_text(result_jsonb, "table_name"),
                            )
                        )
                    ).label("datasets"),
                    func.count(distinct(FlowExecution.id)).label("flows"),
                    func.count(
                        distinct(
                            func.concat(
                                cast(FlowExecution.flow_id, String), ":", FlowNodeResult.node_id
                            )
                        )
                    ).label("checks"),
                )
                .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
                .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
                .filter(
                    and_(
                        DQFlow.workspace_id == workspace_id,
                        FlowNodeResult.node_type == "check",
                        FlowNodeResult.result_data.isnot(None),
                        FlowExecution.started_at >= start_date,
                    )
                )
                .group_by(func.date_trunc("day", FlowExecution.started_at))
                .order_by(func.date_trunc("day", FlowExecution.started_at))
                .all()
            )
            data_points = [
                CoverageTrendDataPoint(
                    date=row.day.date() if row.day else start_date,
                    datasets=row.datasets or 0,
                    flows=row.flows or 0,
                    checks=row.checks or 0,
                )
                for row in rows
            ]

        return CoverageTrendResponse(
            data_points=data_points,
            has_data=len(data_points) > 0,
        )
