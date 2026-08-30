"""
SQLAlchemy models for KQI (Key Quality Indicator) Dynamic Reports Engine.

Models:
- SLADefinition: Workspace-scoped SLA target times per severity level
- CostModel: Organization-scoped cost-per-incident configuration
- KQISnapshot: Historical daily snapshots of KQI values for trend charts
"""

import uuid

from sqlalchemy import TIMESTAMP, Column, Date, Float, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.database import Base


class SLADefinition(Base):
    """SLA target definition per workspace and severity level."""

    __tablename__ = "sla_definitions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    severity_level = Column(String(50), nullable=False)
    target_hours = Column(Float, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "severity_level", name="uq_sla_workspace_severity"),
        Index("ix_sla_definitions_workspace_id", "workspace_id"),
    )


class CostModel(Base):
    """Cost-per-incident configuration per organization and severity."""

    __tablename__ = "cost_models"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    severity = Column(String(50), nullable=False)
    estimated_cost_usd = Column(Float, nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "severity", name="uq_cost_model_workspace_severity"),
        Index("ix_cost_models_workspace_id", "workspace_id"),
    )

    # Default cost estimates by severity
    DEFAULT_COSTS = {
        "critical": 15000.0,
        "major": 5000.0,
        "minor": 1000.0,
        "info": 200.0,
    }


class KQISnapshot(Base):
    """Historical daily snapshot of a KQI value for trend visualization."""

    __tablename__ = "kqi_snapshots"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    kqi_id = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    snapshot_date = Column(Date, nullable=False)
    meta_data = Column("metadata", JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "kqi_id", "snapshot_date", name="uq_kqi_snapshot_workspace_kqi_date"
        ),
        Index("ix_kqi_snapshots_workspace_date", "workspace_id", "snapshot_date"),
        Index("ix_kqi_snapshots_kqi_id", "kqi_id"),
    )
