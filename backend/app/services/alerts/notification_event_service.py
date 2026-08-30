"""
F045 Notification Event Service
=================================

Service-layer CRUD for notification events with validation, status transitions, and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notification_event import NotificationEvent
from app.services.alerts.notification_event_models import (
    VALID_STATUSES,
    NotificationEventResponse,
    NotificationEventSummary,
)
from app.services.alerts.notification_event_repository import NotificationEventRepository
from app.services.audit.hooks import build_notification_event_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Status transition rules
# ---------------------------------------------------------------------------

# From which statuses can you transition to which
ALLOWED_TRANSITIONS: dict[str, frozenset] = {
    "pending": frozenset({"sent", "failed", "retrying"}),
    "retrying": frozenset({"sent", "failed", "retrying"}),
    "sent": frozenset(),  # terminal
    "failed": frozenset(),  # terminal
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NotificationEventValidationError(Exception):
    """Raised when notification event input fails validation."""


class NotificationEventNotFoundError(Exception):
    """Raised when a notification event is not found in the workspace."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NotificationEventService:
    """CRUD for notification events."""

    def __init__(
        self,
        repo: NotificationEventRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or NotificationEventRepository()
        self._audit = audit_service or AuditService()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _to_response(ev: NotificationEvent) -> NotificationEventResponse:
        return NotificationEventResponse(
            id=ev.id,
            workspace_id=ev.workspace_id,
            alert_rule_id=ev.alert_rule_id,
            alert_channel_id=ev.alert_channel_id,
            recipient=ev.recipient,
            status=ev.status,
            payload=ev.payload,
            retry_count=ev.retry_count,
            max_retries=ev.max_retries,
            last_error=ev.last_error,
            sent_at=ev.sent_at,
            delivered_at=ev.delivered_at,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        )

    # -- create ---------------------------------------------------------------

    def log_event(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        alert_rule_id: UUID,
        alert_channel_id: UUID,
        recipient: str,
        payload: dict | None = None,
        status: str = "pending",
        max_retries: int = 3,
        audit_ctx: AuditContext | None = None,
    ) -> NotificationEventResponse:
        recipient = (recipient or "").strip()
        if not recipient:
            raise NotificationEventValidationError("recipient must not be blank")
        if status not in VALID_STATUSES:
            raise NotificationEventValidationError(f"invalid status: {status}")

        event = NotificationEvent(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            alert_rule_id=alert_rule_id,
            alert_channel_id=alert_channel_id,
            recipient=recipient,
            status=status,
            payload=payload,
            retry_count=0,
            max_retries=max_retries,
        )
        event = self._repo.insert(db, event)

        if audit_ctx is not None:
            entry = build_notification_event_audit_entry(
                ctx=audit_ctx,
                action="notification_event_created",
                workspace_id=workspace_id,
                notification_event_id=event.id,
                after_state={"recipient": recipient, "status": status},
            )
            self._audit.write(db, entry)

        return self._to_response(event)

    # -- read -----------------------------------------------------------------

    def get_event(
        self,
        db: Session,
        *,
        event_id: UUID,
        workspace_id: UUID,
    ) -> NotificationEventResponse:
        ev = self._repo.get_by_id_and_workspace(db, event_id, workspace_id)
        if ev is None:
            raise NotificationEventNotFoundError(f"notification event {event_id} not found")
        return self._to_response(ev)

    def list_events(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        status_filter: str | None = None,
        rule_filter: UUID | None = None,
        channel_filter: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NotificationEventResponse]:
        events = self._repo.list_by_workspace(
            db,
            workspace_id,
            status_filter=status_filter,
            rule_filter=rule_filter,
            channel_filter=channel_filter,
            limit=limit,
            offset=offset,
        )
        return [self._to_response(e) for e in events]

    # -- update status --------------------------------------------------------

    def update_event_status(
        self,
        db: Session,
        *,
        event_id: UUID,
        workspace_id: UUID,
        status: str,
        last_error: str | None = None,
        retry_count: int | None = None,
        audit_ctx: AuditContext | None = None,
    ) -> NotificationEventResponse:
        if status not in VALID_STATUSES:
            raise NotificationEventValidationError(f"invalid status: {status}")

        # Fetch current event
        ev = self._repo.get_by_id_and_workspace(db, event_id, workspace_id)
        if ev is None:
            raise NotificationEventNotFoundError(f"notification event {event_id} not found")

        # Validate transition
        allowed = ALLOWED_TRANSITIONS.get(ev.status, frozenset())
        if status not in allowed:
            raise NotificationEventValidationError(
                f"cannot transition from '{ev.status}' to '{status}'"
            )

        before_status = ev.status
        kwargs: dict = {"status": status}
        if last_error is not None:
            kwargs["last_error"] = last_error
        if retry_count is not None:
            kwargs["retry_count"] = retry_count

        now = datetime.now(UTC)
        if status == "sent":
            kwargs["delivered_at"] = now
            if ev.sent_at is None:
                kwargs["sent_at"] = now
        elif status == "retrying":
            if retry_count is None:
                kwargs["retry_count"] = ev.retry_count + 1

        updated = self._repo.update_status(db, event_id, workspace_id, **kwargs)

        if audit_ctx is not None and updated is not None:
            entry = build_notification_event_audit_entry(
                ctx=audit_ctx,
                action="notification_event_status_updated",
                workspace_id=workspace_id,
                notification_event_id=event_id,
                after_state={"status": status},
                before_state={"status": before_status},
            )
            self._audit.write(db, entry)

        return self._to_response(updated)

    # -- summary --------------------------------------------------------------

    def get_summary(
        self,
        db: Session,
        *,
        workspace_id: UUID,
    ) -> NotificationEventSummary:
        counts = self._repo.count_by_workspace_and_status(db, workspace_id)
        return NotificationEventSummary(
            pending=counts.get("pending", 0),
            sent=counts.get("sent", 0),
            failed=counts.get("failed", 0),
            retrying=counts.get("retrying", 0),
        )
