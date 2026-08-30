"""
SQLAlchemy models for dashboards and reporting.
"""

import uuid

from sqlalchemy import DECIMAL, JSON, TIMESTAMP, UUID, Boolean, Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Dashboard(Base):
    """Dashboard model for custom user dashboards."""

    __tablename__ = "dashboards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    layout = Column(JSON, nullable=False, default=list)  # List of widget positions
    is_public = Column(Boolean, default=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User")
    widgets = relationship(
        "DashboardWidget", back_populates="dashboard", cascade="all, delete-orphan"
    )


class DashboardWidget(Base):
    """Dashboard widget model."""

    __tablename__ = "dashboard_widgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dashboard_id = Column(
        UUID(as_uuid=True), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False
    )
    widget_type = Column(
        String(50), nullable=False
    )  # kpi, line_chart, bar_chart, pie_chart, table, gauge, heatmap
    title = Column(String(255), nullable=False)
    query_config = Column(JSON, nullable=False, default=dict)
    position = Column(JSON, nullable=False, default=dict)  # {x, y, w, h}
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    dashboard = relationship("Dashboard", back_populates="widgets")


class Report(Base):
    """Report definition model."""

    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    report_type = Column(
        String(50), nullable=False
    )  # executive, detailed, source, trend, compliance
    config = Column(JSON, nullable=False, default=dict)
    schedule = Column(JSON)  # {frequency, recipients, enabled}
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User")
    executions = relationship(
        "ReportExecution", back_populates="report", cascade="all, delete-orphan"
    )


class ReportExecution(Base):
    """Report execution history model."""

    __tablename__ = "report_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(
        String(50), nullable=False, default="pending"
    )  # pending, running, completed, failed
    file_path = Column(Text)
    file_format = Column(String(20))  # pdf, excel, csv, json
    error_message = Column(Text)
    execution_time_seconds = Column(DECIMAL(10, 2))
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    report = relationship("Report", back_populates="executions")


class MetricsCache(Base):
    """Cached aggregated metrics for performance."""

    __tablename__ = "metrics_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    metric_type = Column(
        String(100), nullable=False
    )  # overall_score, pass_rate, category_breakdown, etc.
    metric_key = Column(String(255))  # additional identifier
    metric_value = Column(JSON, nullable=False)
    time_period = Column(String(50))  # day, week, month, all_time
    calculated_at = Column(TIMESTAMP, server_default=func.now())
    created_at = Column(TIMESTAMP, server_default=func.now())
