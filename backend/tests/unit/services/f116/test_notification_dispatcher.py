"""
F120 — Notification Dispatcher Tests (F116)
=============================================

Tests for the NotificationDispatcher service: email/webhook delivery,
retry logic, pending batch processing, and test notifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.services.alerts.notification_dispatcher import (
    NotificationDispatcher,
    NotificationDispatchError,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_event(**overrides):
    defaults = dict(
        id=uuid4(),
        workspace_id=uuid4(),
        alert_rule_id=uuid4(),
        alert_channel_id=uuid4(),
        recipient="user@example.com",
        status="pending",
        payload={"subject": "Alert", "body": "Something happened"},
        retry_count=0,
        max_retries=3,
        last_error=None,
        sent_at=None,
        delivered_at=None,
    )
    defaults.update(overrides)
    m = MagicMock(**defaults)
    # Make attributes settable
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_channel(channel_type="email", enabled=True, **config_overrides):
    config = {
        "smtp_host": "mail.test",
        "smtp_port": 587,
        "smtp_username": "u",
        "smtp_password": "p",
        "smtp_tls": False,
        "from_address": "no-reply@test.com",
    }
    if channel_type == "webhook":
        config = {"url": "https://hooks.test/notify"}
    config.update(config_overrides)
    ch = MagicMock()
    ch.id = uuid4()
    ch.workspace_id = uuid4()
    ch.channel_type = channel_type
    ch.configuration = config
    ch.enabled = enabled
    return ch


def _mock_db(event=None, channel=None):
    db = MagicMock()

    def side_effect(model):
        q = MagicMock()
        filt = MagicMock()
        if hasattr(model, "__tablename__"):
            if model.__tablename__ == "notification_events":
                filt.first.return_value = event
            elif model.__tablename__ == "alert_channels":
                filt.first.return_value = channel
        q.filter.return_value = filt
        return q

    db.query.side_effect = side_effect
    return db


# ── Dispatch Event Tests ─────────────────────────────────────────────────────


class TestDispatchEvent:
    def setup_method(self):
        self.dispatcher = NotificationDispatcher()

    def test_event_not_found_returns_false(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert self.dispatcher.dispatch_event(db, uuid4()) is False

    def test_skips_already_sent(self):
        event = _make_event(status="sent")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = event
        assert self.dispatcher.dispatch_event(db, event.id) is False

    @patch.object(NotificationDispatcher, "_deliver_email")
    def test_email_success(self, mock_email):
        event = _make_event()
        channel = _make_channel("email")
        db = _mock_db(event, channel)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is True
        assert event.status == "sent"
        assert event.sent_at is not None
        mock_email.assert_called_once()

    @patch.object(NotificationDispatcher, "_deliver_webhook")
    def test_webhook_success(self, mock_webhook):
        event = _make_event()
        channel = _make_channel("webhook")
        db = _mock_db(event, channel)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is True
        assert event.status == "sent"
        mock_webhook.assert_called_once()

    def test_channel_not_found_marks_failed(self):
        event = _make_event()
        db = _mock_db(event, None)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is False
        assert event.status == "failed"

    def test_disabled_channel_marks_failed(self):
        event = _make_event()
        channel = _make_channel(enabled=False)
        db = _mock_db(event, channel)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is False
        assert event.status == "failed"

    @patch.object(NotificationDispatcher, "_deliver_email", side_effect=Exception("SMTP timeout"))
    def test_retry_on_failure(self, _):
        event = _make_event(retry_count=0, max_retries=3)
        channel = _make_channel("email")
        db = _mock_db(event, channel)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is False
        assert event.status == "retrying"
        assert event.retry_count == 1

    @patch.object(NotificationDispatcher, "_deliver_email", side_effect=Exception("dead"))
    def test_permanent_failure_after_max_retries(self, _):
        event = _make_event(retry_count=2, max_retries=3)
        channel = _make_channel("email")
        db = _mock_db(event, channel)
        result = self.dispatcher.dispatch_event(db, event.id)
        assert result is False
        assert event.status == "failed"
        assert event.retry_count == 3


# ── Dispatch Pending Tests ───────────────────────────────────────────────────


class TestDispatchPending:
    def setup_method(self):
        self.dispatcher = NotificationDispatcher()

    @patch.object(NotificationDispatcher, "dispatch_event", return_value=True)
    def test_processes_pending_batch(self, mock_dispatch):
        events = [_make_event() for _ in range(3)]
        db = MagicMock()
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = events

        counts = self.dispatcher.dispatch_pending(db, batch_size=10)
        assert counts["sent"] == 3
        assert mock_dispatch.call_count == 3

    def test_empty_batch(self):
        db = MagicMock()
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = []
        counts = self.dispatcher.dispatch_pending(db)
        assert counts == {"sent": 0, "failed": 0, "skipped": 0}


# ── Webhook Delivery Tests ───────────────────────────────────────────────────


class TestWebhookDelivery:
    def setup_method(self):
        self.dispatcher = NotificationDispatcher()

    @patch("app.services.alerts.notification_dispatcher.httpx.Client")
    def test_webhook_posts_payload(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client
        resp = MagicMock(status_code=200)
        mock_client.post.return_value = resp

        config = {"url": "https://hooks.test/notify", "secret": "s3cret"}
        event = _make_event()
        self.dispatcher._deliver_webhook(config, event)

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["headers"]["X-Webhook-Secret"] == "s3cret"

    @patch("app.services.alerts.notification_dispatcher.httpx.Client")
    def test_webhook_error_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client
        resp = MagicMock(status_code=500, text="Internal Server Error")
        mock_client.post.return_value = resp

        config = {"url": "https://hooks.test/fail"}
        with pytest.raises(NotificationDispatchError, match="500"):
            self.dispatcher._deliver_webhook(config, _make_event())

    def test_webhook_no_url_raises(self):
        with pytest.raises(NotificationDispatchError, match="URL not configured"):
            self.dispatcher._deliver_webhook({}, _make_event())


# ── Send Test Tests ──────────────────────────────────────────────────────────


class TestSendTest:
    def setup_method(self):
        self.dispatcher = NotificationDispatcher()

    def test_channel_not_found_raises(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(NotificationDispatchError, match="not found"):
            self.dispatcher.send_test(db, uuid4(), uuid4())

    @patch.object(NotificationDispatcher, "_deliver_email")
    def test_send_test_email_success(self, mock_email):
        channel = _make_channel("email")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = channel
        result = self.dispatcher.send_test(db, channel.id, channel.workspace_id)
        assert result["success"] is True
        mock_email.assert_called_once()

    @patch.object(NotificationDispatcher, "_deliver_webhook", side_effect=Exception("conn refused"))
    def test_send_test_failure_returns_message(self, _):
        channel = _make_channel("webhook")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = channel
        result = self.dispatcher.send_test(db, channel.id, channel.workspace_id)
        assert result["success"] is False
        assert "conn refused" in result["message"]
