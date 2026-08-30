"""
Incident ORM Models — F038 Manual Incident Creation

Maps to the ``public.incidents`` and ``public.incident_issues`` tables
created by migration 019_f038_incidents.sql.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class Incident(Base):
    """Manually-created incident grouping one or more data-quality issues."""

    __tablename__ = "incidents"

    # --- Primary key ---
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant / workspace scope ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # --- Content ---
    title = Column(String(500), nullable=False)
    severity = Column(String(30), nullable=False)
    priority = Column(String(10), nullable=False)
    status = Column(String(30), nullable=False, default="open")
    impact_summary = Column(Text, nullable=True)

    # --- Ownership ---
    owner_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Timestamps ---
    opened_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at = Column(TIMESTAMP(timezone=True), nullable=True)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    closed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- Content (lifecycle) ---
    resolution_summary = Column(Text, nullable=True)

    # --- External ticketing (F060) ---
    external_ticket_id = Column(String(255), nullable=True)
    external_ticket_url = Column(Text, nullable=True)
    external_system = Column(String(100), nullable=True)

    # --- Relationships ---
    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by_user_id])
    linked_issues = relationship(
        "IncidentIssue",
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class IncidentIssue(Base):
    """Junction table linking incidents to issues."""

    __tablename__ = "incident_issues"

    incident_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    issue_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    linked_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    linked_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Relationships ---
    incident = relationship("Incident", back_populates="linked_issues")
