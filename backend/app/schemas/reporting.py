"""
Pydantic schemas for dashboards and reporting.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ========== Dashboard Schemas ==========


class WidgetPosition(BaseModel):
    """Widget position and size in grid layout."""

    x: int = Field(..., description="X position in grid")
    y: int = Field(..., description="Y position in grid")
    w: int = Field(..., description="Width in grid units")
    h: int = Field(..., description="Height in grid units")


class WidgetQueryConfig(BaseModel):
    """Configuration for widget data query."""

    metric_type: str = Field(..., description="Type of metric to display")
    data_source_id: UUID | None = None
    flow_id: UUID | None = None
    category: str | None = None
    time_period: str | None = "30d"  # 7d, 30d, 90d, 1y, all
    filters: dict[str, Any] | None = None


class DashboardWidgetCreate(BaseModel):
    """Schema for creating a dashboard widget."""

    widget_type: str = Field(
        ..., description="kpi, line_chart, bar_chart, pie_chart, table, gauge, heatmap"
    )
    title: str = Field(..., min_length=1, max_length=255)
    query_config: WidgetQueryConfig
    position: WidgetPosition


class DashboardWidgetUpdate(BaseModel):
    """Schema for updating a dashboard widget."""

    title: str | None = Field(None, min_length=1, max_length=255)
    query_config: WidgetQueryConfig | None = None
    position: WidgetPosition | None = None


class DashboardWidgetResponse(BaseModel):
    """Response schema for dashboard widget."""

    id: UUID
    dashboard_id: UUID
    widget_type: str
    title: str
    query_config: dict[str, Any]
    position: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardCreate(BaseModel):
    """Schema for creating a dashboard."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    layout: list[dict[str, Any]] = Field(default_factory=list)
    is_public: bool = False


class DashboardUpdate(BaseModel):
    """Schema for updating a dashboard."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    layout: list[dict[str, Any]] | None = None
    is_public: bool | None = None


class DashboardResponse(BaseModel):
    """Response schema for dashboard."""

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    layout: list[dict[str, Any]]
    is_public: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    widgets: list[DashboardWidgetResponse] = []

    model_config = ConfigDict(from_attributes=True)


class DashboardList(BaseModel):
    """List of dashboards with pagination."""

    dashboards: list[DashboardResponse]
    total: int
    page: int
    page_size: int


# ========== Report Schemas ==========


class ReportSchedule(BaseModel):
    """Report schedule configuration."""

    enabled: bool = True
    frequency: str = Field(..., description="daily, weekly, monthly")
    day_of_week: int | None = None  # 0-6 for weekly
    day_of_month: int | None = None  # 1-31 for monthly
    time: str = "09:00"  # HH:MM
    recipients: list[str] = Field(default_factory=list)  # email addresses
    formats: list[str] = Field(default_factory=lambda: ["pdf"])  # pdf, excel, csv


class ReportConfig(BaseModel):
    """Report configuration."""

    date_range: str | None = "30d"
    data_source_ids: list[UUID] | None = None
    flow_ids: list[UUID] | None = None
    categories: list[str] | None = None
    include_charts: bool = True
    include_violations: bool = True
    include_recommendations: bool = True


class ReportCreate(BaseModel):
    """Schema for creating a report."""

    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., description="executive, detailed, source, trend, compliance")
    config: ReportConfig
    schedule: ReportSchedule | None = None


class ReportUpdate(BaseModel):
    """Schema for updating a report."""

    name: str | None = Field(None, min_length=1, max_length=255)
    report_type: str | None = None
    config: ReportConfig | None = None
    schedule: ReportSchedule | None = None


class ReportResponse(BaseModel):
    """Response schema for report."""

    id: UUID
    workspace_id: UUID
    name: str
    report_type: str
    config: dict[str, Any]
    schedule: dict[str, Any] | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportExecutionResponse(BaseModel):
    """Response schema for report execution."""

    id: UUID
    report_id: UUID
    workspace_id: UUID
    status: str
    file_path: str | None
    file_format: str | None
    error_message: str | None
    execution_time_seconds: float | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportList(BaseModel):
    """List of reports with pagination."""

    reports: list[ReportResponse]
    total: int
    page: int
    page_size: int


# ========== Metrics Schemas ==========


class OverviewMetrics(BaseModel):
    """Overall KPI metrics."""

    total_rules: int
    total_executions: int
    average_pass_rate: float
    dq_score: float
    critical_violations: int
    total_data_sources: int
    total_flows: int
    last_updated: datetime


class TrendDataPoint(BaseModel):
    """Single data point in a trend."""

    timestamp: datetime
    value: float
    label: str | None = None


class TrendMetrics(BaseModel):
    """Time series trend data."""

    metric_name: str
    data_points: list[TrendDataPoint]
    time_period: str


class CategoryMetrics(BaseModel):
    """Metrics breakdown by category."""

    category: str
    total_rules: int
    total_executions: int
    pass_rate: float
    avg_execution_time: float


class CategoryBreakdown(BaseModel):
    """Category breakdown metrics."""

    categories: list[CategoryMetrics]
    total: int


class SourceMetrics(BaseModel):
    """Metrics for a single data source."""

    source_id: UUID
    source_name: str
    total_rules: int
    total_executions: int
    pass_rate: float
    last_execution: datetime | None
    health_status: str  # healthy, warning, critical


class SourceBreakdown(BaseModel):
    """Data source breakdown metrics."""

    sources: list[SourceMetrics]
    total: int


class ScorecardDimension(BaseModel):
    """Single dimension in the scorecard."""

    dimension: str
    score: float
    weight: float
    issues_count: int
    trend: str  # improving, declining, stable


class Scorecard(BaseModel):
    """Data quality scorecard."""

    overall_score: float
    dimensions: list[ScorecardDimension]
    total_issues: int
    critical_issues: int
    trend: str
    last_updated: datetime


# ========== Export Schemas ==========


class ExportRequest(BaseModel):
    """Request schema for data export."""

    export_type: str = Field(..., description="rules, violations, executions")
    format: str = Field(..., description="csv, excel, json, pdf")
    filters: dict[str, Any] | None = None
    date_range: str | None = "30d"


class ExportResponse(BaseModel):
    """Response schema for export request."""

    export_id: UUID
    status: str
    download_url: str | None
    created_at: datetime
