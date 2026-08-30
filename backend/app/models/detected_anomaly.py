"""F5 — Persisted anomaly ORM model."""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.models.database import Base


class DetectedAnomaly(Base):
    __tablename__ = "detected_anomalies"
    __table_args__ = {"schema": "public"}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)

    anomaly_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)

    dataset = Column(String(255))
    column_name = Column(String(255))
    rule_id = Column(PG_UUID(as_uuid=True))

    summary = Column(Text, nullable=False)
    current_value = Column(String(255))
    expected_value = Column(String(255))
    deviation = Column(String(255))

    status = Column(String(20), nullable=False, default="open")
    detected_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at = Column(TIMESTAMP(timezone=True))
    acknowledged_by = Column(PG_UUID(as_uuid=True))
    resolved_at = Column(TIMESTAMP(timezone=True))
    resolved_by = Column(PG_UUID(as_uuid=True))
    notes = Column(Text)

    fingerprint = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
