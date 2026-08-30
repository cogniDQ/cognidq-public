"""
Alert Rule ORM Model — F043 Alert Rule Configuration

Maps to the ``public.alert_rules`` table created by
migration 021_f043_alert_rules.sql.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class AlertRule(Base):
    """Configurable alert trigger with conditions and recipients."""

    __tablename__ = "alert_rules"

    # --- Primary key ---
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant / workspace scope ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # --- Content ---
    name = Column(String(200), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    conditions = Column(JSONB, nullable=True)
    recipient_user_ids = Column(JSONB, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    # --- F044 extensions ---
    channel_ids = Column(JSONB, nullable=True)
    recipient_roles = Column(JSONB, nullable=True)

    # --- Ownership ---
    created_by_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Timestamps ---
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- Relationships ---
    creator = relationship("User", foreign_keys=[created_by_user_id])
