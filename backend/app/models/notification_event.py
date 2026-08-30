"""
Notification Event ORM Model — F045 Notification Event Logging

Maps to the ``public.notification_events`` table created by
migration 023_f045_notification_events.sql.
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class NotificationEvent(Base):
    """Tracks individual notification delivery attempts."""

    __tablename__ = "notification_events"

    # --- Primary key ---
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # --- Tenant / workspace scope ---
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # --- References ---
    alert_rule_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("alert_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_channel_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("alert_channels.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Content ---
    recipient = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    payload = Column(JSONB, nullable=True)

    # --- Retry ---
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    last_error = Column(Text, nullable=True)

    # --- Timestamps ---
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    delivered_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- Relationships ---
    alert_rule = relationship("AlertRule", foreign_keys=[alert_rule_id])
    alert_channel = relationship("AlertChannel", foreign_keys=[alert_channel_id])
