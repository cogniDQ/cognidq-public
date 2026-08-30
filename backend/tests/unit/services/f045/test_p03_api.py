"""
F045 P03 — Notification Event API Endpoint Tests (15 tests)
============================================================

Covers:
  - POST/GET/PATCH /workspaces/{ws}/notification-events
  - GET summary
  - Error mapping (201/200/404/422)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.alerts.notification_event_models import (
    NotificationEventResponse,
    NotificationEventSummary,
)
from app.services.alerts.notification_event_service import (
    NotificationEventNotFoundError,
    NotificationEventValidationError,
)

EVENTS_EP = "app.api.v1.endpoints.notification_events"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_EVENT_ID = uuid4()
_RULE_ID = uuid4()
_CHANNEL_ID = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.user_id = _USER
    actor.role = "admin"
    return actor


def _mock_response(**overrides) -> NotificationEventResponse:
    now = datetime.now(UTC)
    defaults = dict(
        id=_EVENT_ID,
        workspace_id=_WS,
        alert_rule_id=_RULE_ID,
        alert_channel_id=_CHANNEL_ID,
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
    defaults.update(overrides)
    return NotificationEventResponse(**defaults)


def _mock_body_create(**overrides):
    body = MagicMock()
    body.alert_rule_id = overrides.get("alert_rule_id", _RULE_ID)
    body.alert_channel_id = overrides.get("alert_channel_id", _CHANNEL_ID)
    body.recipient = overrides.get("recipient", "admin@example.com")
    body.payload = overrides.get("payload", None)
    body.status = overrides.get("status", "pending")
    body.max_retries = overrides.get("max_retries", 3)
    return body


def _mock_body_update(**overrides):
    body = MagicMock()
    body.status = overrides.get("status", "sent")
    body.last_error = overrides.get("last_error", None)
    body.retry_count = overrides.get("retry_count", None)
    return body


# ---------------------------------------------------------------------------
# POST Tests
# ---------------------------------------------------------------------------


class TestCreateNotificationEvent:
    @pytest.mark.asyncio
    async def test_create_201(self):
        from app.api.v1.endpoints.notification_events import create_notification_event

        resp = _mock_response()
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.log_event.return_value = resp
            result = await create_notification_event(
                workspace_id=_WS,
                body=_mock_body_create(),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_create_422_validation(self):
        from app.api.v1.endpoints.notification_events import create_notification_event

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.log_event.side_effect = NotificationEventValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await create_notification_event(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_payload(self):
        from app.api.v1.endpoints.notification_events import create_notification_event

        payload = {"subject": "Alert: Execution Failed", "severity": "critical"}
        resp = _mock_response(payload=payload)
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.log_event.return_value = resp
            result = await create_notification_event(
                workspace_id=_WS,
                body=_mock_body_create(payload=payload),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["payload"] == payload

    @pytest.mark.asyncio
    async def test_create_default_pending(self):
        from app.api.v1.endpoints.notification_events import create_notification_event

        resp = _mock_response(status="pending")
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.log_event.return_value = resp
            result = await create_notification_event(
                workspace_id=_WS,
                body=_mock_body_create(),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# GET Tests
# ---------------------------------------------------------------------------


class TestListAndGetNotificationEvents:
    @pytest.mark.asyncio
    async def test_list_200(self):
        from app.api.v1.endpoints.notification_events import list_notification_events

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.list_events.return_value = [_mock_response(), _mock_response()]
            result = await list_notification_events(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200
        body = json.loads(result.body)
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        from app.api.v1.endpoints.notification_events import list_notification_events

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.list_events.return_value = [_mock_response(status="sent")]
            result = await list_notification_events(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
                status_filter="sent",
            )
        assert result.status_code == 200
        body = json.loads(result.body)
        assert len(body) == 1

    @pytest.mark.asyncio
    async def test_get_200(self):
        from app.api.v1.endpoints.notification_events import get_notification_event

        resp = _mock_response()
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.get_event.return_value = resp
            result = await get_notification_event(
                workspace_id=_WS,
                event_id=_EVENT_ID,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_404(self):
        from app.api.v1.endpoints.notification_events import get_notification_event

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.get_event.side_effect = NotificationEventNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await get_notification_event(
                    workspace_id=_WS,
                    event_id=uuid4(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PATCH status Tests
# ---------------------------------------------------------------------------


class TestUpdateNotificationEventStatus:
    @pytest.mark.asyncio
    async def test_update_status_200(self):
        from app.api.v1.endpoints.notification_events import update_notification_event_status

        resp = _mock_response(status="sent", delivered_at=datetime.now(UTC))
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.update_event_status.return_value = resp
            result = await update_notification_event_status(
                workspace_id=_WS,
                event_id=_EVENT_ID,
                body=_mock_body_update(status="sent"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_update_status_404(self):
        from app.api.v1.endpoints.notification_events import update_notification_event_status

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.update_event_status.side_effect = NotificationEventNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await update_notification_event_status(
                    workspace_id=_WS,
                    event_id=uuid4(),
                    body=_mock_body_update(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_422(self):
        from app.api.v1.endpoints.notification_events import update_notification_event_status

        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.update_event_status.side_effect = NotificationEventValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await update_notification_event_status(
                    workspace_id=_WS,
                    event_id=_EVENT_ID,
                    body=_mock_body_update(status="pending"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_sets_delivered_at(self):
        from app.api.v1.endpoints.notification_events import update_notification_event_status

        now = datetime.now(UTC)
        resp = _mock_response(status="sent", delivered_at=now)
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.update_event_status.return_value = resp
            result = await update_notification_event_status(
                workspace_id=_WS,
                event_id=_EVENT_ID,
                body=_mock_body_update(status="sent"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["delivered_at"] is not None

    @pytest.mark.asyncio
    async def test_update_sets_last_error(self):
        from app.api.v1.endpoints.notification_events import update_notification_event_status

        resp = _mock_response(status="failed", last_error="Connection refused")
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.update_event_status.return_value = resp
            result = await update_notification_event_status(
                workspace_id=_WS,
                event_id=_EVENT_ID,
                body=_mock_body_update(status="failed", last_error="Connection refused"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["last_error"] == "Connection refused"


# ---------------------------------------------------------------------------
# GET summary Tests
# ---------------------------------------------------------------------------


class TestNotificationEventSummary:
    @pytest.mark.asyncio
    async def test_summary_200(self):
        from app.api.v1.endpoints.notification_events import get_notification_event_summary

        summary = NotificationEventSummary(pending=5, sent=10, failed=2, retrying=1)
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.get_summary.return_value = summary
            result = await get_notification_event_summary(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_summary_counts(self):
        from app.api.v1.endpoints.notification_events import get_notification_event_summary

        summary = NotificationEventSummary(pending=3, sent=7, failed=1, retrying=0)
        with patch(f"{EVENTS_EP}._svc") as svc_mock:
            svc_mock.get_summary.return_value = summary
            result = await get_notification_event_summary(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["pending"] == 3
        assert body["sent"] == 7
        assert body["failed"] == 1
        assert body["retrying"] == 0
