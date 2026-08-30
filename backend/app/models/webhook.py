"""
F059 — Webhook and Event Delivery — ORM Models
================================================

Maps to the tables created by migration 024_f059_webhooks.sql:
  - webhook_subscriptions
  - webhook_delivery_log
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class WebhookSubscription(Base):
    """A registered webhook endpoint for a workspace.

    Stores the target URL, HMAC signing key, and the set of event types
    (``execution_failed``, ``issue_created``, ``incident_created``,
    ``incident_updated``) that trigger this subscription.
    """

    __tablename__ = "webhook_subscriptions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)
    name = Column(String(200), nullable=False)
    target_url = Column(Text, nullable=False)
    secret_key = Column(Text, nullable=False)
    event_types = Column(ARRAY(Text), nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # --- relationships ---
    delivery_logs = relationship(
        "WebhookDeliveryLog",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class WebhookDeliveryLog(Base):
    """Records each attempt to deliver a webhook event payload.

    ``status`` progresses: pending → retrying → delivered | failed | abandoned.
    """

    __tablename__ = "webhook_delivery_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    next_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    http_response_code = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    delivered_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- relationships ---
    subscription = relationship("WebhookSubscription", back_populates="delivery_logs")
