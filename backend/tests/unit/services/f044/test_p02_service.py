"""
F044 P02 — AlertChannelService Tests
======================================

15 tests covering service-layer CRUD, validation, and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.models.alert_channel import AlertChannel
from app.services.alerts.alert_channel_service import (
    AlertChannelNotFoundError,
    AlertChannelService,
    AlertChannelValidationError,
    DuplicateAlertChannelNameError,
)
from app.services.audit.models import AuditContext

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


def _mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.name_exists.return_value = False
    return repo


def _mock_audit() -> MagicMock:
    return MagicMock()


def _audit_ctx() -> AuditContext:
    return AuditContext(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_type="user",
        actor_role="admin",
        request_id=None,
        source_ip=None,
    )


def _svc(repo=None, audit=None) -> AlertChannelService:
    return AlertChannelService(
        repo=repo or _mock_repo(),
        audit_service=audit or _mock_audit(),
    )


# ── Create Tests ─────────────────────────────────────────────────────────────


class TestCreateChannel:
    def test_create_channel_success(self):
        repo = _mock_repo()
        ch = _make_channel()
        repo.insert.return_value = ch
        svc = _svc(repo=repo)
        result = svc.create_channel(
            MagicMock(),
            workspace_id=ch.workspace_id,
            tenant_id=ch.tenant_id,
            created_by_user_id=ch.created_by_user_id,
            name=ch.name,
            channel_type="email",
            configuration={"from_address": "a@b.com"},
        )
        assert result.name == ch.name
        repo.insert.assert_called_once()

    def test_create_email_channel(self):
        repo = _mock_repo()
        ch = _make_channel(channel_type="email")
        repo.insert.return_value = ch
        svc = _svc(repo=repo)
        result = svc.create_channel(
            MagicMock(),
            workspace_id=ch.workspace_id,
            tenant_id=ch.tenant_id,
            created_by_user_id=ch.created_by_user_id,
            name="Email",
            channel_type="email",
            configuration={},
        )
        assert result.channel_type == "email"

    def test_create_webhook_channel(self):
        repo = _mock_repo()
        ch = _make_channel(channel_type="webhook", configuration={"url": "https://example.com"})
        repo.insert.return_value = ch
        svc = _svc(repo=repo)
        result = svc.create_channel(
            MagicMock(),
            workspace_id=ch.workspace_id,
            tenant_id=ch.tenant_id,
            created_by_user_id=ch.created_by_user_id,
            name="Webhook",
            channel_type="webhook",
            configuration={"url": "https://example.com"},
        )
        assert result.channel_type == "webhook"

    def test_create_name_validation(self):
        svc = _svc()
        with pytest.raises(AlertChannelValidationError, match="name"):
            svc.create_channel(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="   ",
                channel_type="email",
                configuration={},
            )

    def test_create_invalid_channel_type(self):
        svc = _svc()
        with pytest.raises(AlertChannelValidationError, match="channel_type"):
            svc.create_channel(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Test",
                channel_type="sms",
                configuration={},
            )

    def test_create_duplicate_name(self):
        repo = _mock_repo()
        repo.name_exists.return_value = True
        svc = _svc(repo=repo)
        with pytest.raises(DuplicateAlertChannelNameError):
            svc.create_channel(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Dup",
                channel_type="email",
                configuration={},
            )

    def test_create_audit_written(self):
        repo = _mock_repo()
        audit = _mock_audit()
        ch = _make_channel()
        repo.insert.return_value = ch
        svc = _svc(repo=repo, audit=audit)
        svc.create_channel(
            MagicMock(),
            workspace_id=ch.workspace_id,
            tenant_id=ch.tenant_id,
            created_by_user_id=ch.created_by_user_id,
            name=ch.name,
            channel_type="email",
            configuration={},
            audit_ctx=_audit_ctx(),
        )
        audit.write.assert_called_once()
        entry = audit.write.call_args[0][1]
        assert entry.action_type == "alert_channel_created"


# ── Read Tests ───────────────────────────────────────────────────────────────


class TestReadChannels:
    def test_get_channel_success(self):
        repo = _mock_repo()
        ch = _make_channel()
        repo.get_by_id_and_workspace.return_value = ch
        svc = _svc(repo=repo)
        result = svc.get_channel(MagicMock(), channel_id=ch.id, workspace_id=ch.workspace_id)
        assert result.id == ch.id

    def test_get_channel_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertChannelNotFoundError):
            svc.get_channel(MagicMock(), channel_id=uuid4(), workspace_id=uuid4())

    def test_list_channels(self):
        repo = _mock_repo()
        channels = [_make_channel(), _make_channel()]
        repo.list_by_workspace.return_value = channels
        svc = _svc(repo=repo)
        result = svc.list_channels(MagicMock(), workspace_id=uuid4())
        assert len(result) == 2


# ── Update Tests ─────────────────────────────────────────────────────────────


class TestUpdateChannel:
    def test_update_channel_success(self):
        repo = _mock_repo()
        ch = _make_channel()
        repo.get_by_id_and_workspace.return_value = ch
        repo.update.return_value = ch
        svc = _svc(repo=repo)
        result = svc.update_channel(
            MagicMock(),
            channel_id=ch.id,
            workspace_id=ch.workspace_id,
            name="Updated",
        )
        assert result is not None
        repo.update.assert_called_once()

    def test_update_channel_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertChannelNotFoundError):
            svc.update_channel(MagicMock(), channel_id=uuid4(), workspace_id=uuid4(), name="X")

    def test_update_duplicate_name(self):
        repo = _mock_repo()
        ch = _make_channel()
        repo.get_by_id_and_workspace.return_value = ch
        repo.name_exists.return_value = True
        svc = _svc(repo=repo)
        with pytest.raises(DuplicateAlertChannelNameError):
            svc.update_channel(
                MagicMock(),
                channel_id=ch.id,
                workspace_id=ch.workspace_id,
                name="Taken",
            )


# ── Delete Tests ─────────────────────────────────────────────────────────────


class TestDeleteChannel:
    def test_delete_channel_success(self):
        repo = _mock_repo()
        audit = _mock_audit()
        ch = _make_channel()
        repo.get_by_id_and_workspace.return_value = ch
        svc = _svc(repo=repo, audit=audit)
        svc.delete_channel(
            MagicMock(),
            channel_id=ch.id,
            workspace_id=ch.workspace_id,
            audit_ctx=_audit_ctx(),
        )
        repo.delete.assert_called_once()
        audit.write.assert_called_once()

    def test_delete_channel_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertChannelNotFoundError):
            svc.delete_channel(MagicMock(), channel_id=uuid4(), workspace_id=uuid4())
