"""
F044 P03 — Alert Channel API Endpoint Tests (15 tests)
=======================================================

Covers:
  - POST/GET/PATCH/DELETE /workspaces/{ws}/alert-channels
  - Error mapping (201/200/204/404/409/422)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.alerts.alert_channel_models import AlertChannelResponse
from app.services.alerts.alert_channel_service import (
    AlertChannelNotFoundError,
    AlertChannelValidationError,
    DuplicateAlertChannelNameError,
)

CHANNELS_EP = "app.api.v1.endpoints.alert_channels"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_CHANNEL_ID = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.user_id = _USER
    actor.role = "admin"
    return actor


def _mock_response(**overrides) -> AlertChannelResponse:
    now = datetime.now(UTC)
    defaults = dict(
        id=_CHANNEL_ID,
        workspace_id=_WS,
        name="Email Channel",
        channel_type="email",
        configuration={"from_address": "alerts@example.com"},
        enabled=True,
        created_by_user_id=_USER,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return AlertChannelResponse(**defaults)


def _mock_body_create(**overrides):
    body = MagicMock()
    body.name = overrides.get("name", "Email Channel")
    body.channel_type = overrides.get("channel_type", "email")
    body.configuration = overrides.get("configuration", {"from_address": "alerts@example.com"})
    body.enabled = overrides.get("enabled", True)
    return body


def _mock_body_update(**overrides):
    body = MagicMock()
    body.name = overrides.get("name", None)
    body.channel_type = overrides.get("channel_type", None)
    body.configuration = overrides.get("configuration", None)
    body.enabled = overrides.get("enabled", None)
    return body


# ---------------------------------------------------------------------------
# POST Tests
# ---------------------------------------------------------------------------


class TestCreateAlertChannel:
    @pytest.mark.asyncio
    async def test_create_201(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        resp = _mock_response()
        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.return_value = resp
            result = await create_alert_channel(
                workspace_id=_WS,
                body=_mock_body_create(),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_create_409_duplicate(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.side_effect = DuplicateAlertChannelNameError("dup")
            with pytest.raises(Exception) as exc_info:
                await create_alert_channel(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_422_validation(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.side_effect = AlertChannelValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await create_alert_channel(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_422_invalid_type(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.side_effect = AlertChannelValidationError(
                "Invalid channel type"
            )
            with pytest.raises(Exception) as exc_info:
                await create_alert_channel(
                    workspace_id=_WS,
                    body=_mock_body_create(channel_type="sms"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_webhook_config_stored(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        config = {"url": "https://hooks.example.com/alert", "headers": {"X-Token": "abc"}}
        resp = _mock_response(channel_type="webhook", configuration=config)
        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.return_value = resp
            result = await create_alert_channel(
                workspace_id=_WS,
                body=_mock_body_create(channel_type="webhook", configuration=config),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["configuration"] == config
        assert body["channel_type"] == "webhook"

    @pytest.mark.asyncio
    async def test_create_email_config_stored(self):
        from app.api.v1.endpoints.alert_channels import create_alert_channel

        config = {"from_address": "noreply@corp.com", "cc": ["ops@corp.com"]}
        resp = _mock_response(channel_type="email", configuration=config)
        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.create_channel.return_value = resp
            result = await create_alert_channel(
                workspace_id=_WS,
                body=_mock_body_create(channel_type="email", configuration=config),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        body = json.loads(result.body)
        assert body["configuration"] == config
        assert body["channel_type"] == "email"


# ---------------------------------------------------------------------------
# GET Tests
# ---------------------------------------------------------------------------


class TestListAndGetAlertChannels:
    @pytest.mark.asyncio
    async def test_list_200(self):
        from app.api.v1.endpoints.alert_channels import list_alert_channels

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.list_channels.return_value = [_mock_response(), _mock_response()]
            result = await list_alert_channels(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200
        body = json.loads(result.body)
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_get_200(self):
        from app.api.v1.endpoints.alert_channels import get_alert_channel

        resp = _mock_response()
        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.get_channel.return_value = resp
            result = await get_alert_channel(
                workspace_id=_WS,
                channel_id=_CHANNEL_ID,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_404(self):
        from app.api.v1.endpoints.alert_channels import get_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.get_channel.side_effect = AlertChannelNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await get_alert_channel(
                    workspace_id=_WS,
                    channel_id=uuid4(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PATCH Tests
# ---------------------------------------------------------------------------


class TestUpdateAlertChannel:
    @pytest.mark.asyncio
    async def test_patch_200(self):
        from app.api.v1.endpoints.alert_channels import update_alert_channel

        resp = _mock_response(name="Updated Channel")
        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.update_channel.return_value = resp
            result = await update_alert_channel(
                workspace_id=_WS,
                channel_id=_CHANNEL_ID,
                body=_mock_body_update(name="Updated Channel"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_404(self):
        from app.api.v1.endpoints.alert_channels import update_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.update_channel.side_effect = AlertChannelNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await update_alert_channel(
                    workspace_id=_WS,
                    channel_id=uuid4(),
                    body=_mock_body_update(name="X"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_409_duplicate_name(self):
        from app.api.v1.endpoints.alert_channels import update_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.update_channel.side_effect = DuplicateAlertChannelNameError("dup")
            with pytest.raises(Exception) as exc_info:
                await update_alert_channel(
                    workspace_id=_WS,
                    channel_id=_CHANNEL_ID,
                    body=_mock_body_update(name="Taken"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_422(self):
        from app.api.v1.endpoints.alert_channels import update_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.update_channel.side_effect = AlertChannelValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await update_alert_channel(
                    workspace_id=_WS,
                    channel_id=_CHANNEL_ID,
                    body=_mock_body_update(channel_type="sms"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# DELETE Tests
# ---------------------------------------------------------------------------


class TestDeleteAlertChannel:
    @pytest.mark.asyncio
    async def test_delete_204(self):
        from app.api.v1.endpoints.alert_channels import delete_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.delete_channel.return_value = None
            result = await delete_alert_channel(
                workspace_id=_WS,
                channel_id=_CHANNEL_ID,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_404(self):
        from app.api.v1.endpoints.alert_channels import delete_alert_channel

        with patch(f"{CHANNELS_EP}._svc") as svc_mock:
            svc_mock.delete_channel.side_effect = AlertChannelNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await delete_alert_channel(
                    workspace_id=_WS,
                    channel_id=uuid4(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404
