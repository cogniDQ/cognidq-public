"""
F045 P02 — NotificationEventService Tests
==========================================

15 tests covering service-layer CRUD, validation, status transitions, and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.models.notification_event import NotificationEvent
from app.services.alerts.notification_event_service import (
    NotificationEventNotFoundError,
    NotificationEventService,
    NotificationEventValidationError,
)
from app.services.audit.models import AuditContext

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_event(**overrides) -> NotificationEvent:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        alert_rule_id=uuid4(),
        alert_channel_id=uuid4(),
        recipient="admin@example.com",
        status="pending",
        payload={"subject": "Alert fired"},
        retry_count=0,
        max_retries=3,
        last_error=None,
        sent_at=None,
        delivered_at=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return NotificationEvent(**defaults)


def _make_ctx(**overrides) -> AuditContext:
    defaults = dict(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_type="user",
        actor_role="admin",
        request_id=None,
        source_ip=None,
    )
    defaults.update(overrides)
    return AuditContext(**defaults)


def _build_service(repo=None, audit=None):
    repo = repo or MagicMock()
    audit = audit or MagicMock()
    return NotificationEventService(repo=repo, audit_service=audit), repo, audit


# ── Create Tests ─────────────────────────────────────────────────────────────


class TestLogEvent:
    def test_log_event_success(self):
        svc, repo, _ = _build_service()
        event = _make_event()
        repo.insert.return_value = event

        result = svc.log_event(
            MagicMock(),
            workspace_id=event.workspace_id,
            tenant_id=event.tenant_id,
            alert_rule_id=event.alert_rule_id,
            alert_channel_id=event.alert_channel_id,
            recipient="admin@example.com",
        )
        assert result.status == "pending"
        repo.insert.assert_called_once()

    def test_log_event_with_payload(self):
        svc, repo, _ = _build_service()
        payload = {"subject": "Testing", "body": "Content"}
        event = _make_event(payload=payload)
        repo.insert.return_value = event

        result = svc.log_event(
            MagicMock(),
            workspace_id=event.workspace_id,
            tenant_id=event.tenant_id,
            alert_rule_id=event.alert_rule_id,
            alert_channel_id=event.alert_channel_id,
            recipient="admin@example.com",
            payload=payload,
        )
        assert result.payload == payload

    def test_log_event_validation_bad_recipient(self):
        svc, _, _ = _build_service()
        with pytest.raises(NotificationEventValidationError):
            svc.log_event(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                alert_rule_id=uuid4(),
                alert_channel_id=uuid4(),
                recipient="   ",
            )

    def test_log_event_audit_written(self):
        svc, repo, audit = _build_service()
        event = _make_event()
        repo.insert.return_value = event

        svc.log_event(
            MagicMock(),
            workspace_id=event.workspace_id,
            tenant_id=event.tenant_id,
            alert_rule_id=event.alert_rule_id,
            alert_channel_id=event.alert_channel_id,
            recipient="admin@example.com",
            audit_ctx=_make_ctx(),
        )
        audit.write.assert_called_once()


# ── Read Tests ───────────────────────────────────────────────────────────────


class TestReadEvents:
    def test_get_event_success(self):
        svc, repo, _ = _build_service()
        event = _make_event()
        repo.get_by_id_and_workspace.return_value = event

        result = svc.get_event(MagicMock(), event_id=event.id, workspace_id=event.workspace_id)
        assert result.id == event.id

    def test_get_event_not_found(self):
        svc, repo, _ = _build_service()
        repo.get_by_id_and_workspace.return_value = None

        with pytest.raises(NotificationEventNotFoundError):
            svc.get_event(MagicMock(), event_id=uuid4(), workspace_id=uuid4())

    def test_list_events_no_filter(self):
        svc, repo, _ = _build_service()
        repo.list_by_workspace.return_value = [_make_event(), _make_event()]

        result = svc.list_events(MagicMock(), workspace_id=uuid4())
        assert len(result) == 2

    def test_list_events_status_filter(self):
        svc, repo, _ = _build_service()
        repo.list_by_workspace.return_value = [_make_event(status="sent")]

        result = svc.list_events(MagicMock(), workspace_id=uuid4(), status_filter="sent")
        repo.list_by_workspace.assert_called_once()
        assert len(result) == 1

    def test_list_events_rule_filter(self):
        svc, repo, _ = _build_service()
        rule_id = uuid4()
        repo.list_by_workspace.return_value = [_make_event(alert_rule_id=rule_id)]

        result = svc.list_events(MagicMock(), workspace_id=uuid4(), rule_filter=rule_id)
        repo.list_by_workspace.assert_called_once()
        assert len(result) == 1


# ── Update Status Tests ─────────────────────────────────────────────────────


class TestUpdateStatus:
    def test_update_status_to_sent(self):
        svc, repo, _ = _build_service()
        event = _make_event(status="pending")
        repo.get_by_id_and_workspace.return_value = event
        updated = _make_event(status="sent", delivered_at=datetime.now(UTC))
        repo.update_status.return_value = updated

        result = svc.update_event_status(
            MagicMock(),
            event_id=event.id,
            workspace_id=event.workspace_id,
            status="sent",
        )
        assert result.status == "sent"

    def test_update_status_to_failed(self):
        svc, repo, _ = _build_service()
        event = _make_event(status="pending")
        repo.get_by_id_and_workspace.return_value = event
        updated = _make_event(status="failed", last_error="Connection refused")
        repo.update_status.return_value = updated

        result = svc.update_event_status(
            MagicMock(),
            event_id=event.id,
            workspace_id=event.workspace_id,
            status="failed",
            last_error="Connection refused",
        )
        assert result.status == "failed"
        assert result.last_error == "Connection refused"

    def test_update_status_to_retrying(self):
        svc, repo, _ = _build_service()
        event = _make_event(status="pending", retry_count=0)
        repo.get_by_id_and_workspace.return_value = event
        updated = _make_event(status="retrying", retry_count=1)
        repo.update_status.return_value = updated

        result = svc.update_event_status(
            MagicMock(),
            event_id=event.id,
            workspace_id=event.workspace_id,
            status="retrying",
        )
        assert result.status == "retrying"

    def test_update_status_not_found(self):
        svc, repo, _ = _build_service()
        repo.get_by_id_and_workspace.return_value = None

        with pytest.raises(NotificationEventNotFoundError):
            svc.update_event_status(
                MagicMock(),
                event_id=uuid4(),
                workspace_id=uuid4(),
                status="sent",
            )

    def test_update_status_invalid_transition(self):
        svc, repo, _ = _build_service()
        event = _make_event(status="sent")
        repo.get_by_id_and_workspace.return_value = event

        with pytest.raises(NotificationEventValidationError, match="cannot transition"):
            svc.update_event_status(
                MagicMock(),
                event_id=event.id,
                workspace_id=event.workspace_id,
                status="pending",
            )


# ── Summary Test ─────────────────────────────────────────────────────────────


class TestSummary:
    def test_get_summary_returns_counts(self):
        svc, repo, _ = _build_service()
        repo.count_by_workspace_and_status.return_value = {
            "pending": 3,
            "sent": 10,
            "failed": 2,
        }

        result = svc.get_summary(MagicMock(), workspace_id=uuid4())
        assert result.pending == 3
        assert result.sent == 10
        assert result.failed == 2
        assert result.retrying == 0
