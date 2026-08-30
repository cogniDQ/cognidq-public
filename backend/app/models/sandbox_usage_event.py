"""
F134 — Demo Sandbox Provisioning
SandboxUsageEvent ORM model (control.sandbox_usage_events — range-partitioned).
"""

import enum

from sqlalchemy import TIMESTAMP, BigInteger, Column, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func

from app.models.database import Base


class SandboxUsageEventType(str, enum.Enum):
    LOGIN = "login"
    PAGE_VIEW = "page_view"
    CHECK_EXECUTED = "check_executed"
    RULE_CREATED = "rule_created"
    RULE_EDITED = "rule_edited"
    DATASET_VIEWED = "dataset_viewed"
    ISSUE_OPENED = "issue_opened"
    ISSUE_STATUS_CHANGED = "issue_status_changed"
    DASHBOARD_VIEWED = "dashboard_viewed"
    ONBOARDING_STEP_COMPLETED = "onboarding_step_completed"
    INVITATION_ACCEPTED = "invitation_accepted"
    EXTENSION_REQUESTED = "extension_requested"
    SYSTEM_NOTIFICATION = "system_notification"


class SandboxUsageEvent(Base):
    """An immutable usage event for a sandbox (range-partitioned by occurred_at)."""

    __tablename__ = "sandbox_usage_events"
    __table_args__ = {"schema": "control"}

    # Composite PK required for partitioned tables in SQLAlchemy
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(
        TIMESTAMP(timezone=True), primary_key=True, nullable=False, server_default=func.now()
    )
    sandbox_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    user_id = Column(PGUUID(as_uuid=True), nullable=True)
    event_type = Column(String(50), nullable=False)
    event_payload = Column(JSONB, nullable=False, server_default="{}")
    request_id = Column(PGUUID(as_uuid=True), nullable=True)
    source_ip = Column(INET, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SandboxUsageEvent type={self.event_type!r} sandbox={self.sandbox_id}>"
