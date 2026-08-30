"""
Alert Channel ORM Model — F044 Alert Channel and Recipient Targeting

Maps to the ``public.alert_channels`` table created by
migration 022_f044_alert_channels.sql.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class AlertChannel(Base):
    """Notification channel (email or webhook) for alert delivery."""

    __tablename__ = "alert_channels"

    # --- Primary key ---
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant / workspace scope ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # --- Content ---
    name = Column(String(200), nullable=False)
    channel_type = Column(String(50), nullable=False)
    configuration = Column(JSONB, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)

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
