"""
Pydantic schemas for KQI (Key Quality Indicator) Dynamic Reports Engine.

Response models for all KQI API endpoints covering:
- Coverage & Inventory (KQI-001 to KQI-019)
- Operational Intelligence (KQI-026 to KQI-030)
- Dataset Quality Profile (KQI-031 to KQI-040)
- Check Intelligence (KQI-041 to KQI-046)
- Business Value (KQI-064 to KQI-066)
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

# ============================================================
# Coverage & Inventory Schemas (KQI-001 to KQI-019)
# ============================================================


class CoverageInventoryResponse(BaseModel):
    """KQI-001 to KQI-010: Dataset and flow inventory metrics."""

    total_datasets: int = Field(0, description="KQI-001: Total registered datasets")
    datasets_analyzed: int = Field(
        0, description="KQI-002: Datasets with at least one check execution"
    )
    datasets_analyzed_pct: float = Field(0.0, description="KQI-002: % of datasets analyzed")
    datasets_analyzed_24h: int = Field(0, description="KQI-003: Datasets analyzed in last 24h")
    datasets_without_flows: int = Field(0, description="KQI-004: Datasets with no flow coverage")
    total_flows: int = Field(0, description="KQI-005: Total DQ flows")
    active_flows: int = Field(0, description="KQI-006: Flows with status=active")
    active_flows_pct: float = Field(0.0, description="KQI-006: % of active flows")
    paused_flows: int = Field(0, description="KQI-007: Paused flows")
    failed_flows: int = Field(0, description="KQI-008: Flows whose last execution failed")
    avg_datasets_per_flow: float = Field(0.0, description="KQI-009: Mean datasets per flow")
    avg_checks_per_flow: float = Field(0.0, description="KQI-010: Mean check nodes per flow")
    has_data: bool = Field(True, description="Whether any execution data exists")


class DimensionCount(BaseModel):
    """Count of checks per DQ dimension."""

    dimension: str
    count: int


class CheckInventoryResponse(BaseModel):
    """KQI-011 to KQI-013: Check inventory by dimension and type."""

    total_checks: int = Field(0, description="KQI-011: Total check node configurations")
    checks_by_dimension: list[DimensionCount] = Field(
        default_factory=list, description="KQI-012: Checks by DQ dimension"
    )
    standard_checks: int = Field(0, description="KQI-013: Standard template checks")
    custom_checks: int = Field(0, description="KQI-013: Custom business rule checks")
    standard_checks_pct: float = Field(0.0, description="KQI-013: % standard checks")
    has_data: bool = Field(False, description="Whether any check data exists")


class GovernanceMaturityResponse(BaseModel):
    """KQI-014 to KQI-018: Governance maturity / metadata coverage."""

    datasets_with_owner_pct: float = Field(0.0, description="KQI-014: % datasets with owner")
    datasets_with_criticality_pct: float = Field(
        0.0, description="KQI-015: % datasets with criticality"
    )
    datasets_with_domain_pct: float = Field(0.0, description="KQI-016: % datasets with domain")
    datasets_with_thresholds_pct: float = Field(
        0.0, description="KQI-017: % datasets with thresholds"
    )
    checks_with_sla_pct: float = Field(0.0, description="KQI-018: % checks with SLA targets")
    has_data: bool = Field(False, description="Whether any dataset data exists")


class CoverageTrendDataPoint(BaseModel):
    """Single data point in the coverage growth trend."""

    date: date
    datasets: int = 0
    flows: int = 0
    checks: int = 0


class CoverageTrendResponse(BaseModel):
    """KQI-019: Coverage growth over time from KQI snapshots."""

    data_points: list[CoverageTrendDataPoint] = Field(default_factory=list)
    has_data: bool = Field(False, description="Whether any trend data exists")


# ============================================================
# Operational Intelligence Schemas (KQI-026 to KQI-030)
# ============================================================


class OperationalSummaryResponse(BaseModel):
    """KQI-026 to KQI-030: Operational intelligence summary."""

    runs_per_day: float = Field(0.0, description="KQI-026: Average executions per day")
    success_rate: float = Field(0.0, description="KQI-027: % of successful executions")
    failure_rate: float = Field(0.0, description="KQI-028: % of failed executions")
    mttr_hours: float | None = Field(None, description="KQI-029: Mean Time to Recovery in hours")
    quality_stability_index: float = Field(
        100.0, description="KQI-030: Quality Stability Index (0-100)"
    )
    has_data: bool = Field(True, description="Whether any execution data exists")


class TimelineDataPoint(BaseModel):
    """Single day in the execution timeline."""

    date: date
    success: int = 0
    partial: int = 0
    failed: int = 0


class OperationalTimelineResponse(BaseModel):
    """Daily execution breakdown for timeline charts."""

    data_points: list[TimelineDataPoint] = Field(default_factory=list)
    has_data: bool = Field(False, description="Whether any timeline data exists")


class CheckHeatmapCell(BaseModel):
    """Single cell in the check performance heatmap."""

    x: str  # date or day label
    y: str  # check name
    value: float  # pass rate %


class CheckHeatmapResponse(BaseModel):
    """Check performance heatmap data (checks × time)."""

    data: list[CheckHeatmapCell] = Field(default_factory=list)
    has_data: bool = Field(False, description="Whether any heatmap data exists")


class RecentAlertItem(BaseModel):
    """A recent alert/notification event for display."""

    date: str
    check: str
    severity: str
    message: str
    resolved: bool


class RecentAlertsResponse(BaseModel):
    """Recent alerts for the flow history dashboard."""

    alerts: list[RecentAlertItem] = Field(default_factory=list)
    has_data: bool = Field(False, description="Whether any alert data exists")


# ============================================================
# Dataset Quality Profile Schemas (KQI-031 to KQI-040)
# ============================================================


class ColumnCoverage(BaseModel):
    """Per-column check coverage info."""

    column: str
    checks_count: int = 0
    coverage_pct: float = 0.0


class WorstCheck(BaseModel):
    """The check with the lowest pass rate."""

    name: str
    pass_rate: float


class UnstableColumn(BaseModel):
    """The column with the highest result variance."""

    name: str
    variance: float


class DatasetProfileResponse(BaseModel):
    """KQI-031 to KQI-040: Full dataset quality profile."""

    dataset_id: UUID
    dataset_name: str
    overall_score: float = Field(0.0, description="KQI-031: Weighted DQ score (0-100)")
    dimension_scores: dict = Field(
        default_factory=dict, description="KQI-032 to KQI-036: Scores by dimension"
    )
    worst_check: WorstCheck | None = Field(None, description="KQI-037: Lowest pass rate check")
    most_unstable_column: UnstableColumn | None = Field(
        None, description="KQI-038: Highest variance column"
    )
    days_since_healthy: int | None = Field(None, description="KQI-039: Days since last 100% pass")
    column_coverage: list[ColumnCoverage] = Field(
        default_factory=list, description="KQI-040: Per-column coverage"
    )
    has_data: bool = Field(True)


# ============================================================
# Check Intelligence Schemas (KQI-041 to KQI-046)
# ============================================================


class HealthDistributionItem(BaseModel):
    """Check health status distribution entry."""

    status: str  # effective, noisy, always_pass, always_fail, duplicate
    count: int


class CheckIntelligenceSummaryResponse(BaseModel):
    """KQI-041 to KQI-046: Check effectiveness summary."""

    noisy_checks_count: int = Field(0, description="KQI-041: Checks with flip rate > 30%")
    always_passing_count: int = Field(0, description="KQI-042: 100% pass in last 90 days")
    always_failing_count: int = Field(0, description="KQI-043: >90% fail in last 30 days")
    duplicate_checks_count: int = Field(0, description="KQI-044: Redundant checks")
    effectiveness_score: float = Field(0.0, description="KQI-045: Overall effectiveness (0-100)")
    health_distribution: list[HealthDistributionItem] = Field(
        default_factory=list, description="KQI-046: Distribution by health status"
    )
    has_data: bool = Field(True)


class ProblematicCheck(BaseModel):
    """Single problematic check with recommendation."""

    check_id: str
    flow_id: UUID
    flow_name: str
    check_name: str
    classification: str  # noisy, always_pass, always_fail, duplicate
    flip_rate: float | None = None
    pass_rate_30d: float | None = None
    recommendation: str


class ProblematicChecksResponse(BaseModel):
    """Paginated list of problematic checks."""

    checks: list[ProblematicCheck] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


# ============================================================
# Business Value Schemas (KQI-064 to KQI-066)
# ============================================================


class IssuesTrendDataPoint(BaseModel):
    """Issues caught per period."""

    date: date
    count: int = 0


class BusinessValueSummaryResponse(BaseModel):
    """KQI-064 to KQI-066: Business value metrics."""

    issues_caught: int = Field(0, description="KQI-064: Auto-detected issues in period")
    issues_caught_trend: list[IssuesTrendDataPoint] = Field(default_factory=list)
    estimated_incidents_avoided: int = Field(
        0, description="KQI-065: Issues resolved before escalation"
    )
    estimated_cost_saved_usd: float = Field(
        0.0, description="KQI-066: Dollar value of issues caught"
    )
    has_data: bool = Field(True)


class TopFlowEntry(BaseModel):
    """A flow ranked by business value."""

    flow_id: UUID
    flow_name: str
    issues_caught: int = 0
    critical_issues: int = 0
    estimated_value_usd: float = 0.0


class TopFlowsResponse(BaseModel):
    """Most valuable flows ranked by issues detected."""

    flows: list[TopFlowEntry] = Field(default_factory=list)


# ============================================================
# Cost Model Configuration Schemas
# ============================================================

VALID_SEVERITIES = {"critical", "major", "minor", "info"}


class CostModelEntry(BaseModel):
    """Cost configuration for a single severity level."""

    severity: str = Field(..., description="Severity level: critical, major, minor, or info")
    estimated_cost_usd: float = Field(
        ..., gt=0, description="Estimated cost in USD per issue of this severity"
    )

    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")
        return v

    def model_post_init(self, __context) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(VALID_SEVERITIES)}")


class CostModelResponse(BaseModel):
    """Current cost model configuration for the workspace."""

    costs: list[CostModelEntry] = Field(default_factory=list)
    is_custom: bool = Field(False, description="True if workspace has overridden the default costs")


class CostModelUpdateRequest(BaseModel):
    """Request body for updating the workspace cost model."""

    costs: list[CostModelEntry] = Field(
        ..., min_length=1, description="Cost entries to upsert (one per severity)"
    )
