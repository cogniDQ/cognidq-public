"""
F134 P09 — Tests for Sandbox Lifecycle Workers + Extension Endpoint

Tests:
  - SandboxService.extend (happy, max-extensions, short-note)
  - SandboxService.suspend (happy, invalid state)
  - SandboxService.archive (happy, invalid state)
  - SandboxService.delete (happy, force, not-archived)
  - SandboxService.scan_expiring (FrozenClock, reminder windows, suspend at expiry)
  - SandboxService.cleanup_expired (grace period)
  - Admin endpoints: extend/suspend/archive/delete (200, 404, 409, 422, 403)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    tenant_api_error_handler,
)
from app.api.v1.endpoints.admin_sandboxes import router as admin_router
from app.lib.time import FrozenClock
from app.models.database import get_db
from app.services.sandbox.sandbox_service import (
    SandboxNotFoundError,
    SandboxService,
    SandboxStateError,
    SandboxValidationError,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

ADMIN_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SANDBOX_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
VIEWER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


def _admin_actor():
    return ActorContext(actor_id=ADMIN_ID, actor_role="platform_admin")


def _viewer_actor():
    return ActorContext(actor_id=VIEWER_ID, actor_role="platform_viewer")


def _fake_sandbox(status="active", extension_count=0, expires_at=None):
    return {
        "id": str(SANDBOX_ID),
        "status": status,
        "extension_count": extension_count,
        "expires_at": expires_at or (NOW + timedelta(days=7)),
        "provisioned_at": NOW,
        "updated_at": NOW,
    }


def _make_client(mock_db, actor_factory=_admin_actor):
    _app = FastAPI()
    _app.include_router(admin_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    return TestClient(_app, raise_server_exceptions=False)


# ── SandboxService.extend ─────────────────────────────────────────────────────


class TestSandboxServiceExtend:
    def _make_svc(self):
        db = MagicMock()
        env_repo = MagicMock()
        ext_repo = MagicMock()
        svc = SandboxService(db, env_repo=env_repo, ext_repo=ext_repo)
        return svc, env_repo, ext_repo

    def test_happy_path_extends_expiry(self):
        svc, env_repo, ext_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(extension_count=0)
        env_repo.increment_extension.return_value = _fake_sandbox(extension_count=1)

        result = svc.extend(
            sandbox_id=SANDBOX_ID,
            note="Need more time for evaluation",
            admin_id=ADMIN_ID,
        )
        env_repo.increment_extension.assert_called_once()
        ext_repo.create.assert_called_once()
        assert result is not None

    def test_raises_validation_error_on_short_note(self):
        svc, env_repo, _ = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(extension_count=0)

        with pytest.raises(SandboxValidationError, match="note"):
            svc.extend(sandbox_id=SANDBOX_ID, note="short", admin_id=ADMIN_ID)

    def test_raises_validation_error_on_max_extensions(self):
        svc, env_repo, _ = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(extension_count=2)

        with pytest.raises(SandboxValidationError, match="extension"):
            svc.extend(
                sandbox_id=SANDBOX_ID,
                note="This is a valid long enough note",
                admin_id=ADMIN_ID,
            )

    def test_raises_not_found_when_missing(self):
        svc, env_repo, _ = self._make_svc()
        env_repo.find_by_id.return_value = None

        with pytest.raises(SandboxNotFoundError):
            svc.extend(
                sandbox_id=SANDBOX_ID,
                note="This is a valid long enough note",
                admin_id=ADMIN_ID,
            )


# ── SandboxService.suspend ────────────────────────────────────────────────────


class TestSandboxServiceSuspend:
    def _make_svc(self):
        db = MagicMock()
        env_repo = MagicMock()
        svc = SandboxService(db, env_repo=env_repo)
        return svc, env_repo

    def test_happy_path_suspends_active(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="active")
        env_repo.update_status.return_value = _fake_sandbox(status="suspended")

        result = svc.suspend(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)
        env_repo.update_status.assert_called_once()
        assert result["status"] == "suspended"

    def test_raises_state_error_when_already_suspended(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="suspended")

        with pytest.raises(SandboxStateError):
            svc.suspend(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)

    def test_raises_state_error_when_archived(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="archived")

        with pytest.raises(SandboxStateError):
            svc.suspend(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)


# ── SandboxService.archive ────────────────────────────────────────────────────


class TestSandboxServiceArchive:
    def _make_svc(self):
        db = MagicMock()
        env_repo = MagicMock()
        svc = SandboxService(db, env_repo=env_repo)
        return svc, env_repo

    def test_happy_path_archives_suspended(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="suspended")
        env_repo.update_status.return_value = _fake_sandbox(status="archived")

        result = svc.archive(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)
        assert result["status"] == "archived"

    def test_archives_expired_sandbox(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="expired")
        env_repo.update_status.return_value = _fake_sandbox(status="archived")

        result = svc.archive(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)
        assert result is not None

    def test_raises_state_error_for_active(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="active")

        with pytest.raises(SandboxStateError, match="Suspend"):
            svc.archive(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)


# ── SandboxService.delete ─────────────────────────────────────────────────────


class TestSandboxServiceDelete:
    def _make_svc(self):
        db = MagicMock()
        env_repo = MagicMock()
        svc = SandboxService(db, env_repo=env_repo)
        return svc, env_repo

    def test_happy_path_deletes_archived(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="archived")
        svc.delete(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)
        env_repo.update_status.assert_called_once_with(
            sandbox_id=SANDBOX_ID, status="deleted", set_deleted_at=True
        )

    def test_raises_state_error_when_not_archived(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="active")

        with pytest.raises(SandboxStateError, match="Archive"):
            svc.delete(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID)

    def test_force_deletes_non_archived(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="active")

        svc.delete(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID, force=True)
        env_repo.update_status.assert_called_once()

    def test_raises_state_error_when_already_deleted(self):
        svc, env_repo = self._make_svc()
        env_repo.find_by_id.return_value = _fake_sandbox(status="deleted")

        with pytest.raises(SandboxStateError, match="already deleted"):
            svc.delete(sandbox_id=SANDBOX_ID, admin_id=ADMIN_ID, force=True)


# ── SandboxService.scan_expiring ──────────────────────────────────────────────


class TestSandboxServiceScanExpiring:
    def test_suspends_expired_active_sandbox(self):
        """FrozenClock at NOW; sandbox expired 1 hour ago → should be expired."""
        db = MagicMock()
        env_repo = MagicMock()
        clock = FrozenClock(NOW)
        svc = SandboxService(db, clock=clock, env_repo=env_repo)

        expired_sandbox = _fake_sandbox(
            status="active",
            expires_at=NOW - timedelta(hours=1),
        )
        expired_sandbox["id"] = str(SANDBOX_ID)
        env_repo.list_expiring.return_value = [expired_sandbox]

        result = svc.scan_expiring()
        assert result["expired"] == 1
        env_repo.update_status.assert_called_once_with(
            sandbox_id=SANDBOX_ID,
            status="expired",
            set_suspended_at=False,
        )

    def test_skips_non_active_sandbox(self):
        db = MagicMock()
        env_repo = MagicMock()
        clock = FrozenClock(NOW)
        svc = SandboxService(db, clock=clock, env_repo=env_repo)

        env_repo.list_expiring.return_value = [
            {**_fake_sandbox(status="suspended"), "id": str(SANDBOX_ID)}
        ]
        result = svc.scan_expiring()
        assert result["expired"] == 0

    def test_returns_summary_dict(self):
        db = MagicMock()
        env_repo = MagicMock()
        env_repo.list_expiring.return_value = []
        svc = SandboxService(db, env_repo=env_repo)
        result = svc.scan_expiring()
        assert "reminders_sent" in result
        assert "expired" in result
        assert "scanned_at" in result


# ── SandboxService.cleanup_expired ───────────────────────────────────────────


class TestSandboxServiceCleanup:
    def test_archives_expired_sandboxes(self):
        db = MagicMock()
        env_repo = MagicMock()
        env_repo.list_ready_for_cleanup.return_value = [
            {**_fake_sandbox(status="expired"), "id": str(SANDBOX_ID)}
        ]
        svc = SandboxService(db, env_repo=env_repo)

        result = svc.cleanup_expired(grace_days=1)
        assert result["archived"] == 1

    def test_skips_active_sandbox(self):
        db = MagicMock()
        env_repo = MagicMock()
        env_repo.list_ready_for_cleanup.return_value = [
            {**_fake_sandbox(status="active"), "id": str(SANDBOX_ID)}
        ]
        svc = SandboxService(db, env_repo=env_repo)

        result = svc.cleanup_expired()
        assert result["archived"] == 0


# ── Admin lifecycle endpoints ─────────────────────────────────────────────────


class TestExtendSandboxEndpoint:
    def test_returns_200_on_success(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "extend") as mock_extend:
            mock_extend.return_value = _fake_sandbox(extension_count=1)
            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/sandboxes/{SANDBOX_ID}/extend",
                json={"note": "Extending for evaluation purposes", "extra_days": 7},
            )
        assert resp.status_code == 200

    def test_returns_404_when_not_found(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "extend", side_effect=SandboxNotFoundError("x")):
            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/sandboxes/{SANDBOX_ID}/extend",
                json={"note": "Extending for evaluation purposes"},
            )
        assert resp.status_code == 404

    def test_returns_422_on_validation_error(self):
        mock_db = MagicMock()
        with patch.object(
            SandboxService, "extend", side_effect=SandboxValidationError("note: too short")
        ):
            client = _make_client(mock_db)
            resp = client.post(
                f"/api/v1/admin/sandboxes/{SANDBOX_ID}/extend",
                json={"note": "hi"},
            )
        assert resp.status_code == 422

    def test_returns_403_for_viewer(self):
        mock_db = MagicMock()
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.post(
            f"/api/v1/admin/sandboxes/{SANDBOX_ID}/extend",
            json={"note": "Extending for evaluation purposes"},
        )
        assert resp.status_code == 403


class TestSuspendSandboxEndpoint:
    def test_returns_200_on_success(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "suspend") as mock_suspend:
            mock_suspend.return_value = _fake_sandbox(status="suspended")
            client = _make_client(mock_db)
            resp = client.post(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/suspend")
        assert resp.status_code == 200

    def test_returns_409_on_state_error(self):
        mock_db = MagicMock()
        with patch.object(
            SandboxService, "suspend", side_effect=SandboxStateError("already suspended")
        ):
            client = _make_client(mock_db)
            resp = client.post(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/suspend")
        assert resp.status_code == 409


class TestArchiveSandboxEndpoint:
    def test_returns_200_on_success(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "archive") as mock_archive:
            mock_archive.return_value = _fake_sandbox(status="archived")
            client = _make_client(mock_db)
            resp = client.post(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/archive")
        assert resp.status_code == 200

    def test_returns_409_when_active(self):
        mock_db = MagicMock()
        with patch.object(
            SandboxService, "archive", side_effect=SandboxStateError("Suspend first")
        ):
            client = _make_client(mock_db)
            resp = client.post(f"/api/v1/admin/sandboxes/{SANDBOX_ID}/archive")
        assert resp.status_code == 409


class TestDeleteSandboxEndpoint:
    def test_returns_204_on_success(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "delete"):
            client = _make_client(mock_db)
            resp = client.delete(f"/api/v1/admin/sandboxes/{SANDBOX_ID}")
        assert resp.status_code == 204

    def test_returns_409_when_not_archived(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "delete", side_effect=SandboxStateError("Archive first")):
            client = _make_client(mock_db)
            resp = client.delete(f"/api/v1/admin/sandboxes/{SANDBOX_ID}")
        assert resp.status_code == 409

    def test_force_param_passed(self):
        mock_db = MagicMock()
        with patch.object(SandboxService, "delete") as mock_delete:
            client = _make_client(mock_db)
            client.delete(f"/api/v1/admin/sandboxes/{SANDBOX_ID}?force=true")
        call_kwargs = mock_delete.call_args.kwargs
        assert call_kwargs.get("force") is True

    def test_returns_403_for_viewer(self):
        mock_db = MagicMock()
        client = _make_client(mock_db, actor_factory=_viewer_actor)
        resp = client.delete(f"/api/v1/admin/sandboxes/{SANDBOX_ID}")
        assert resp.status_code == 403
