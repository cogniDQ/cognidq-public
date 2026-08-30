"""
DatasetQualityService — KQI-031 to KQI-040.

Computes per-dataset quality profiles: dimension scores, overall weighted score,
worst check, most unstable column, days since healthy, and column coverage.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.models.dashboard import MetricsCache
from app.models.datasource import DataSource, DataSourceSchema
from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.kqi import (
    ColumnCoverage,
    DatasetProfileResponse,
    UnstableColumn,
    WorstCheck,
)

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 5

# Weight map for overall DQ score
DIMENSION_WEIGHTS = {
    "completeness": 0.25,
    "validity": 0.20,
    "uniqueness": 0.20,
    "consistency": 0.15,
    "timeliness": 0.10,
    "accuracy": 0.10,
}


class DatasetQualityService:
    """Service for computing per-dataset quality profile KQIs."""

    def __init__(self, db: Session):
        self.db = db

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

    def _get_date_range(self, period: str):
        end = datetime.utcnow()
        days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 30)
        return end - timedelta(days=days), end

    # ------------------------------------------------------------------
    # KQI-031 to KQI-040: Dataset Quality Profile
    # ------------------------------------------------------------------

    def get_profile(
        self,
        workspace_id: UUID,
        dataset_id: UUID,
        period: str = "30d",
        use_cache: bool = True,
    ) -> DatasetProfileResponse:
        """Return full quality profile for a single dataset."""

        cache_key = f"kqi_dataset_profile_{dataset_id}_{period}"
        if use_cache:
            cached = self._get_cached(workspace_id, cache_key)
            if cached:
                return DatasetProfileResponse(**cached.metric_value)

        # Resolve dataset — try control.datasets table first, fall back to data sources
        ds_row = self.db.execute(
            sa_text("""
                SELECT d.dataset_id, d.dataset_name, d.physical_identifier,
                       d.data_source_id, d.schema_name,
                       ds.source_name
                FROM control.datasets d
                JOIN control.data_sources ds ON ds.data_source_id = d.data_source_id
                WHERE d.dataset_id = :dataset_id
                  AND d.workspace_id = :workspace_id
                LIMIT 1
            """),
            {"dataset_id": str(dataset_id), "workspace_id": str(workspace_id)},
        ).fetchone()

        if ds_row:
            dataset_name = ds_row.dataset_name
            physical_id = ds_row.physical_identifier
            data_source_id = ds_row.data_source_id
        else:
            # Fallback: treat dataset_id as a DataSource id
            dataset = (
                self.db.query(DataSource)
                .filter(
                    and_(
                        DataSource.id == dataset_id,
                        DataSource.workspace_id == workspace_id,
                    )
                )
                .first()
            )

            if not dataset:
                return DatasetProfileResponse(
                    dataset_id=dataset_id,
                    dataset_name="Unknown",
                    has_data=False,
                )
            dataset_name = dataset.name
            physical_id = None
            data_source_id = dataset.id

        start_date, end_date = self._get_date_range(period)

        # Build filters for check results
        result_filters = [
            DQFlow.workspace_id == workspace_id,
            FlowNodeResult.node_type == "check",
            FlowNodeResult.status.in_(["completed", "failed"]),
            FlowNodeResult.created_at >= start_date,
            FlowNodeResult.created_at <= end_date,
        ]
        # Match by table_name in result_data using the dataset's physical_identifier
        if physical_id:
            result_filters.append(FlowNodeResult.result_data["table_name"].astext == physical_id)

        # Get all check results for this dataset in the period
        check_results = (
            self.db.query(
                FlowNodeResult.id,
                FlowNodeResult.node_id,
                FlowNodeResult.execution_id,
                FlowNodeResult.result_data,
                FlowNodeResult.created_at,
                FlowExecution.flow_id,
            )
            .join(FlowExecution, FlowNodeResult.execution_id == FlowExecution.id)
            .join(DQFlow, FlowExecution.flow_id == DQFlow.id)
            .filter(and_(*result_filters))
            .order_by(FlowNodeResult.created_at)
            .all()
        )

        if not check_results:
            result = DatasetProfileResponse(
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                has_data=False,
            )
            self._set_cache(workspace_id, cache_key, result.model_dump(mode="json"))
            return result

        # KQI-032 to KQI-036: Dimension scores (avg pass_rate per dimension)
        dimension_scores = self._compute_dimension_scores(check_results)

        # KQI-031: Overall weighted score
        overall_score = self._compute_overall_score(dimension_scores)

        # KQI-037: Worst check
        worst_check = self._find_worst_check(check_results)

        # KQI-038: Most unstable column
        most_unstable = self._find_most_unstable_column(check_results)

        # KQI-039: Days since healthy (last 100% pass)
        days_since_healthy = self._compute_days_since_healthy(check_results)

        # KQI-040: Column coverage
        column_coverage = self._compute_column_coverage(workspace_id, data_source_id, check_results)

        result = DatasetProfileResponse(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            worst_check=worst_check,
            most_unstable_column=most_unstable,
            days_since_healthy=days_since_healthy,
            column_coverage=column_coverage,
            has_data=True,
        )

        self._set_cache(workspace_id, cache_key, result.model_dump(mode="json"))
        return result

    def _compute_dimension_scores(self, check_results) -> dict[str, float]:
        """Compute average pass_rate per DQ dimension."""
        dimension_rates: dict[str, list[float]] = defaultdict(list)

        for cr in check_results:
            rd = cr.result_data or {}
            check_type = rd.get("check_type", "").lower()
            pass_rate = rd.get("pass_rate")
            if check_type and pass_rate is not None:
                try:
                    dimension_rates[check_type].append(float(pass_rate))
                except (ValueError, TypeError):
                    pass

        return {
            dim: round(sum(rates) / len(rates), 1)
            for dim, rates in dimension_rates.items()
            if rates
        }

    def _compute_overall_score(self, dimension_scores: dict[str, float]) -> float:
        """Compute weighted overall DQ score from dimension scores."""
        if not dimension_scores:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0
        for dim, score in dimension_scores.items():
            weight = DIMENSION_WEIGHTS.get(dim, 0.10)
            weighted_sum += score * weight
            total_weight += weight

        return round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0

    def _find_worst_check(self, check_results) -> WorstCheck | None:
        """Find the check with the lowest average pass_rate."""
        check_rates: dict[str, list[float]] = defaultdict(list)

        for cr in check_results:
            rd = cr.result_data or {}
            check_name = rd.get("check_name") or rd.get("rule_name") or cr.node_id
            pass_rate = rd.get("pass_rate")
            if pass_rate is not None:
                try:
                    check_rates[check_name].append(float(pass_rate))
                except (ValueError, TypeError):
                    pass

        if not check_rates:
            return None

        worst_name = min(check_rates, key=lambda k: sum(check_rates[k]) / len(check_rates[k]))
        worst_avg = round(sum(check_rates[worst_name]) / len(check_rates[worst_name]), 1)
        return WorstCheck(name=worst_name, pass_rate=worst_avg)

    def _find_most_unstable_column(self, check_results) -> UnstableColumn | None:
        """Find the column with the highest pass_rate variance."""
        column_rates: dict[str, list[float]] = defaultdict(list)

        for cr in check_results:
            rd = cr.result_data or {}
            column = rd.get("column_name") or rd.get("column")
            pass_rate = rd.get("pass_rate")
            if column and pass_rate is not None:
                try:
                    column_rates[column].append(float(pass_rate))
                except (ValueError, TypeError):
                    pass

        if not column_rates:
            return None

        def _variance(rates: list[float]) -> float:
            if len(rates) < 2:
                return 0.0
            mean = sum(rates) / len(rates)
            return sum((r - mean) ** 2 for r in rates) / len(rates)

        most_unstable_col = max(column_rates, key=lambda k: _variance(column_rates[k]))
        var = _variance(column_rates[most_unstable_col])
        if var == 0:
            return None
        return UnstableColumn(name=most_unstable_col, variance=round(math.sqrt(var), 1))

    def _compute_days_since_healthy(self, check_results) -> int | None:
        """Find days since all checks for this dataset passed at 100%."""
        # Group by execution, check if all pass_rate >= 100 (or close to it)
        exec_dates: dict[str, list[float]] = defaultdict(list)
        exec_timestamps: dict[str, datetime] = {}

        for cr in check_results:
            rd = cr.result_data or {}
            pass_rate = rd.get("pass_rate")
            exec_id = str(cr.execution_id)
            if pass_rate is not None:
                try:
                    exec_dates[exec_id].append(float(pass_rate))
                except (ValueError, TypeError):
                    pass
            if cr.created_at and (
                exec_id not in exec_timestamps or cr.created_at > exec_timestamps[exec_id]
            ):
                exec_timestamps[exec_id] = cr.created_at

        # Find the most recent execution where ALL checks had pass_rate >= 99.9
        last_healthy = None
        for exec_id, rates in exec_dates.items():
            if rates and all(r >= 99.9 for r in rates):
                ts = exec_timestamps.get(exec_id)
                if ts and (last_healthy is None or ts > last_healthy):
                    last_healthy = ts

        if last_healthy is None:
            return None

        return (datetime.utcnow() - last_healthy).days

    def _compute_column_coverage(
        self, workspace_id: UUID, data_source_id: UUID, check_results
    ) -> list[ColumnCoverage]:
        """Compute per-column check coverage."""
        # Get schema columns for this dataset
        schema_columns = (
            self.db.query(DataSourceSchema.column_name)
            .filter(DataSourceSchema.data_source_id == data_source_id)
            .distinct()
            .all()
        )

        all_columns = {row.column_name for row in schema_columns}

        # Columns that have checks
        checked_columns: dict[str, int] = defaultdict(int)
        for cr in check_results:
            rd = cr.result_data or {}
            col = rd.get("column_name") or rd.get("column")
            if col:
                checked_columns[col] += 1

        if not all_columns:
            # No schema info, just return what we have from checks
            return [
                ColumnCoverage(column=col, checks_count=cnt, coverage_pct=100.0)
                for col, cnt in sorted(checked_columns.items())
            ]

        total_checks = max(len(set(cr.node_id for cr in check_results)), 1)
        result = []
        for col in sorted(all_columns):
            cnt = checked_columns.get(col, 0)
            pct = round(cnt / total_checks * 100, 1) if total_checks > 0 else 0.0
            result.append(
                ColumnCoverage(column=col, checks_count=cnt, coverage_pct=min(pct, 100.0))
            )

        return result
