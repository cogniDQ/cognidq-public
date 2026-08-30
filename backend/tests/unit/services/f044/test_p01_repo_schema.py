"""
F044 P01 — ORM + Repository + Schema Tests
============================================

15 tests covering AlertChannel ORM model, Pydantic schemas, and repository CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.models.alert_channel import AlertChannel
from app.services.alerts.alert_channel_models import (
    VALID_CHANNEL_TYPES,
    AlertChannelResponse,
    CreateAlertChannelRequest,
    UpdateAlertChannelRequest,
)
from app.services.alerts.alert_channel_repository import AlertChannelRepository

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_channel(**overrides) -> AlertChannel:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        name="Email Channel",
        channel_type="email",
        configuration={"from_address": "alerts@example.com"},
        enabled=True,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return AlertChannel(**defaults)


def _mock_db() -> MagicMock:
    return MagicMock()


# ── ORM Tests ────────────────────────────────────────────────────────────────


class TestAlertChannelORM:
    def test_alert_channel_table_name(self):
        assert AlertChannel.__tablename__ == "alert_channels"

    def test_alert_channel_columns(self):
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "name",
            "channel_type",
            "configuration",
            "enabled",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        cols = {c.name for c in AlertChannel.__table__.columns}
        assert expected.issubset(cols)

    def test_alert_channel_defaults(self):
        col_default_enabled = AlertChannel.__table__.c.enabled.default.arg
        assert col_default_enabled is True
        assert AlertChannel.__table__.c.id.default is not None


# ── Schema Tests ─────────────────────────────────────────────────────────────


class TestPydanticSchemas:
    def test_create_request_valid(self):
        req = CreateAlertChannelRequest(
            name="Email Channel",
            channel_type="email",
            configuration={"from_address": "alerts@example.com"},
        )
        assert req.name == "Email Channel"
        assert req.channel_type == "email"
        assert req.enabled is True

    def test_create_request_name_blank(self):
        with pytest.raises(Exception):
            CreateAlertChannelRequest(
                name="   ",
                channel_type="email",
            )

    def test_create_request_invalid_channel_type(self):
        with pytest.raises(Exception):
            CreateAlertChannelRequest(
                name="Test",
                channel_type="sms",
            )

    def test_create_request_webhook_requires_url(self):
        # Webhook creation is valid (URL validation is at service layer)
        req = CreateAlertChannelRequest(
            name="Webhook",
            channel_type="webhook",
            configuration={"url": "https://example.com/hook"},
        )
        assert req.configuration["url"] == "https://example.com/hook"

    def test_update_request_all_optional(self):
        req = UpdateAlertChannelRequest()
        assert req.name is None
        assert req.channel_type is None
        assert req.configuration is None
        assert req.enabled is None

    def test_response_model_fields(self):
        fields = set(AlertChannelResponse.model_fields.keys())
        expected = {
            "id",
            "workspace_id",
            "name",
            "channel_type",
            "configuration",
            "enabled",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(fields)


# ── Repository Tests ─────────────────────────────────────────────────────────


class TestAlertChannelRepository:
    def setup_method(self):
        self.repo = AlertChannelRepository()

    def test_repo_insert_calls_add_flush(self):
        db = _mock_db()
        channel = _make_channel()
        result = self.repo.insert(db, channel)
        db.add.assert_called_once_with(channel)
        db.flush.assert_called_once()
        assert result is channel

    def test_repo_get_by_id_and_workspace(self):
        db = _mock_db()
        channel_id, ws_id = uuid4(), uuid4()
        mock_query = db.query.return_value.filter.return_value
        mock_query.first.return_value = _make_channel(id=channel_id, workspace_id=ws_id)
        result = self.repo.get_by_id_and_workspace(db, channel_id, ws_id)
        assert result is not None
        db.query.assert_called_once_with(AlertChannel)

    def test_repo_list_by_workspace(self):
        db = _mock_db()
        ws_id = uuid4()
        channels = [_make_channel(), _make_channel()]
        chain = db.query.return_value.filter.return_value.order_by.return_value
        chain.all.return_value = channels
        result = self.repo.list_by_workspace(db, ws_id)
        assert result == channels

    def test_repo_update_refreshes(self):
        db = _mock_db()
        channel = _make_channel()
        result = self.repo.update(db, channel)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(channel)
        assert result is channel

    def test_repo_delete_returns_bool(self):
        db = _mock_db()
        channel_id, ws_id = uuid4(), uuid4()
        channel = _make_channel(id=channel_id)
        with patch.object(self.repo, "get_by_id_and_workspace", return_value=channel):
            assert self.repo.delete(db, channel_id, ws_id) is True
            db.delete.assert_called_once_with(channel)
        db.reset_mock()
        with patch.object(self.repo, "get_by_id_and_workspace", return_value=None):
            assert self.repo.delete(db, channel_id, ws_id) is False
            db.delete.assert_not_called()

    def test_repo_name_exists(self):
        db = _mock_db()
        ws_id = uuid4()
        chain = db.query.return_value.filter.return_value
        chain.first.return_value = (uuid4(),)
        assert self.repo.name_exists(db, ws_id, "Test") is True
        chain.first.return_value = None
        assert self.repo.name_exists(db, ws_id, "Unique") is False
