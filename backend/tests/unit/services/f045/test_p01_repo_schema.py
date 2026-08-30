"""
F045 P01 — ORM + Repository + Schema Tests
============================================

15 tests covering NotificationEvent ORM model, Pydantic schemas, and repository CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest
from app.models.notification_event import NotificationEvent
from app.services.alerts.notification_event_models import (
    VALID_STATUSES,
    CreateNotificationEventRequest,
    NotificationEventResponse,
    NotificationEventSummary,
    UpdateNotificationEventStatusRequest,
)
from app.services.alerts.notification_event_repository import NotificationEventRepository

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


def _mock_db() -> MagicMock:
    return MagicMock()


# ── ORM Tests ────────────────────────────────────────────────────────────────


class TestNotificationEventORM:
    def test_notification_event_table_name(self):
        assert NotificationEvent.__tablename__ == "notification_events"

    def test_notification_event_columns(self):
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "alert_rule_id",
            "alert_channel_id",
            "recipient",
            "status",
            "payload",
            "retry_count",
            "max_retries",
            "last_error",
            "sent_at",
            "delivered_at",
            "created_at",
            "updated_at",
        }
        actual = {c.name for c in NotificationEvent.__table__.columns}
        assert expected == actual

    def test_notification_event_defaults(self):
        col_defaults = {
            c.name: c.default.arg if c.default is not None else None
            for c in NotificationEvent.__table__.columns
            if c.default is not None
        }
        assert col_defaults.get("status") == "pending"
        assert col_defaults.get("retry_count") == 0
        assert col_defaults.get("max_retries") == 3


# ── Pydantic Schema Tests ───────────────────────────────────────────────────


class TestPydanticSchemas:
    def test_create_request_valid(self):
        req = CreateNotificationEventRequest(
            alert_rule_id=uuid4(),
            alert_channel_id=uuid4(),
            recipient="admin@company.com",
        )
        assert req.status == "pending"
        assert req.max_retries == 3

    def test_create_request_missing_recipient(self):
        with pytest.raises(Exception):
            CreateNotificationEventRequest(
                alert_rule_id=uuid4(),
                alert_channel_id=uuid4(),
                recipient="",
            )

    def test_create_request_invalid_status(self):
        with pytest.raises(Exception):
            CreateNotificationEventRequest(
                alert_rule_id=uuid4(),
                alert_channel_id=uuid4(),
                recipient="x@y.com",
                status="unknown",
            )

    def test_update_status_request_valid(self):
        req = UpdateNotificationEventStatusRequest(status="sent")
        assert req.status == "sent"
        assert req.last_error is None

    def test_update_status_request_invalid_status(self):
        with pytest.raises(Exception):
            UpdateNotificationEventStatusRequest(status="bad_status")

    def test_response_model_fields(self):
        now = datetime.now(UTC)
        resp = NotificationEventResponse(
            id=uuid4(),
            workspace_id=uuid4(),
            alert_rule_id=uuid4(),
            alert_channel_id=uuid4(),
            recipient="admin@example.com",
            status="pending",
            payload=None,
            retry_count=0,
            max_retries=3,
            last_error=None,
            sent_at=None,
            delivered_at=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.status == "pending"
        assert resp.retry_count == 0


# ── Repository Tests ─────────────────────────────────────────────────────────


class TestNotificationEventRepository:
    def test_repo_insert_calls_add_flush(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        event = _make_event()
        result = repo.insert(db, event)
        db.add.assert_called_once_with(event)
        db.flush.assert_called_once()
        assert result is event

    def test_repo_get_by_id_and_workspace(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        ws = uuid4()
        eid = uuid4()
        repo.get_by_id_and_workspace(db, eid, ws)
        db.query.assert_called_once()

    def test_repo_list_by_workspace(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        ws = uuid4()
        repo.list_by_workspace(db, ws, limit=50, offset=0)
        db.query.assert_called_once()

    def test_repo_list_with_status_filter(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        ws = uuid4()
        repo.list_by_workspace(db, ws, status_filter="pending")
        db.query.assert_called_once()

    def test_repo_update_status(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        ws = uuid4()
        eid = uuid4()
        event = _make_event(id=eid, workspace_id=ws)
        db.query.return_value.filter.return_value.first.return_value = event
        result = repo.update_status(db, eid, ws, status="sent")
        assert result.status == "sent"
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(event)

    def test_repo_count_by_workspace_and_status(self):
        db = _mock_db()
        repo = NotificationEventRepository()
        ws = uuid4()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("pending", 5),
            ("sent", 10),
            ("failed", 2),
        ]
        result = repo.count_by_workspace_and_status(db, ws)
        assert result == {"pending": 5, "sent": 10, "failed": 2}
