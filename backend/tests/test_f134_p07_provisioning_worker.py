"""
F134 P07 — Tests for Provisioning Worker + Invitation Flow

Tests:
  - Invitation token signing and verification
  - SandboxProvisioningService provisioning + idempotency
  - GET /admin/sandboxes (list + detail)
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
from app.api.v1.endpoints.admin_sandboxes import router as sandboxes_router
from app.models.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

SECRET = "test-secret-key-for-hmac"
ADMIN_ACTOR_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
WORKSPACE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
JOB_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
REQUEST_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
SANDBOX_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _admin_actor():
    return ActorContext(actor_id=ADMIN_ACTOR_ID, actor_role="platform_admin")


def _viewer_actor():
    return ActorContext(
        actor_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        actor_role="platform_viewer",
    )


def _fake_sandbox(status: str = "active"):
    return {
        "id": str(SANDBOX_ID),
        "demo_request_id": str(REQUEST_ID),
        "tenant_id": str(TENANT_ID),
        "workspace_id": str(WORKSPACE_ID),
        "template_id": "general_dq",
        "status": status,
        "expires_at": datetime(2026, 5, 2, 0, 0, 0, tzinfo=UTC),
        "engagement_score": "low",
        "extension_count": 0,
        "created_at": datetime(2026, 4, 25, 0, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 25, 0, 0, 0, tzinfo=UTC),
    }


def _fake_request_row():
    return {
        "id": str(REQUEST_ID),
        "status": "approved",
        "work_email": "prospect@company.io",
        "first_name": "Alice",
        "last_name": "Smith",
        "company_name": "Acme Corp",
        "template_id": "general_dq",
        "access_profile_code": "mvp_default",
        "duration_days": 7,
    }


def _fake_job_row():
    return {
        "id": str(JOB_ID),
        "demo_request_id": str(REQUEST_ID),
        "sandbox_id": None,
        "status": "pending",
        "attempt_count": 0,
    }


# ── Invitation token tests ────────────────────────────────────────────────────


class TestInvitationToken:
    def test_generate_and_verify_round_trip(self):
        from app.services.sandbox.invitation import (
            generate_invitation_token,
            verify_invitation_token,
        )

        token = generate_invitation_token(
            user_id=str(ADMIN_ACTOR_ID),
            email="test@example.com",
            secret=SECRET,
        )
        payload = verify_invitation_token(token, secret=SECRET)
        assert payload is not None
        assert payload["user_id"] == str(ADMIN_ACTOR_ID)
        assert payload["email"] == "test@example.com"
        assert payload["purpose"] == "sandbox_invitation"

    def test_tampered_token_fails(self):
        from app.services.sandbox.invitation import (
            generate_invitation_token,
            verify_invitation_token,
        )

        token = generate_invitation_token(
            user_id="user-1",
            email="test@example.com",
            secret=SECRET,
        )
        tampered = token[:-4] + "XXXX"
        assert verify_invitation_token(tampered, secret=SECRET) is None

    def test_wrong_secret_fails(self):
        from app.services.sandbox.invitation import (
            generate_invitation_token,
            verify_invitation_token,
        )

        token = generate_invitation_token(
            user_id="user-1",
            email="test@example.com",
            secret=SECRET,
        )
        assert verify_invitation_token(token, secret="wrong-secret") is None

    def test_expired_token_fails(self):
        from app.services.sandbox.invitation import (
            generate_invitation_token,
            verify_invitation_token,
        )

        past_now = datetime(2025, 1, 1, tzinfo=UTC)
        token = generate_invitation_token(
            user_id="user-1",
            email="test@example.com",
            secret=SECRET,
            now=past_now,
            ttl_days=7,
        )
        # Verify at a time well past expiry
        future_now = datetime(2026, 1, 1, tzinfo=UTC)
        assert verify_invitation_token(token, secret=SECRET, now=future_now) is None

    def test_invalid_format_returns_none(self):
        from app.services.sandbox.invitation import verify_invitation_token

        assert verify_invitation_token("not-a-valid-token", secret=SECRET) is None
        assert verify_invitation_token("", secret=SECRET) is None

    def test_token_is_non_empty_string(self):
        from app.services.sandbox.invitation import generate_invitation_token

        token = generate_invitation_token(
            user_id="user-1",
            email="test@example.com",
            secret=SECRET,
        )
        assert isinstance(token, str)
        assert len(token) > 20
        assert "." in token


# ── SandboxProvisioningService tests ─────────────────────────────────────────


class TestSandboxProvisioningService:
    def _make_svc(self, db):
        from app.services.sandbox.provisioning_service import SandboxProvisioningService

        svc = SandboxProvisioningService(db, invitation_secret=SECRET)

        # Mock all repos
        svc._request_repo = MagicMock()
        svc._job_repo = MagicMock()
        svc._env_repo = MagicMock()
        svc._profile_repo = MagicMock()
        svc._seeder_service = MagicMock()

        # Default setup
        svc._job_repo.find_by_id.return_value = _fake_job_row()
        svc._request_repo.find_by_id.return_value = _fake_request_row()
        svc._profile_repo.find_by_code.return_value = {
            "id": str(uuid.uuid4()),
            "code": "mvp_default",
        }

        env_row = {
            **_fake_sandbox("provisioning"),
            "user_id": str(uuid.uuid4()),
        }
        svc._env_repo.create.return_value = env_row
        svc._env_repo.update_status.return_value = {**env_row, "status": "active"}

        # No existing env (not idempotent path)
        db.execute.return_value.fetchone.return_value = None

        return svc

    def test_raises_when_job_not_found(self):
        from app.services.sandbox.provisioning_service import (
            ProvisioningError,
            SandboxProvisioningService,
        )

        db = MagicMock()
        svc = SandboxProvisioningService(db, invitation_secret=SECRET)
        svc._job_repo = MagicMock()
        svc._job_repo.find_by_id.return_value = None

        with pytest.raises(ProvisioningError, match="not found"):
            svc.provision(job_id=JOB_ID)

    def test_idempotent_when_env_already_exists(self):
        from app.services.sandbox.provisioning_service import SandboxProvisioningService

        db = MagicMock()
        svc = self._make_svc(db)
        # Return existing env from idempotency check
        db.execute.return_value.fetchone.return_value = MagicMock(_mapping=_fake_sandbox("active"))

        result = svc.provision(job_id=JOB_ID)
        assert result["status"] == "active"
        # No further DB work should have happened
        svc._env_repo.create.assert_not_called()

    def test_provision_calls_seeder(self):
        from app.services.sandbox.provisioning_service import SandboxProvisioningService

        db = MagicMock()
        svc = self._make_svc(db)

        svc.provision(job_id=JOB_ID)
        svc._seeder_service.seed.assert_called_once()

    def test_provision_marks_job_succeeded(self):
        from app.services.sandbox.provisioning_service import SandboxProvisioningService

        db = MagicMock()
        svc = self._make_svc(db)

        svc.provision(job_id=JOB_ID)

        # Check that update was called with status='succeeded'
        update_calls = [
            c for c in svc._job_repo.update.call_args_list if c.kwargs.get("status") == "succeeded"
        ]
        assert len(update_calls) >= 1

    def test_provision_emits_email_stub(self):
        from app.services.sandbox.provisioning_service import (
            SandboxProvisioningService,
            emit_sandbox_approved_email,
        )

        db = MagicMock()
        svc = self._make_svc(db)

        with patch(
            "app.services.sandbox.provisioning_service.emit_sandbox_approved_email"
        ) as mock_email:
            svc.provision(job_id=JOB_ID)
            mock_email.assert_called_once()

    def test_provision_returns_invitation_token(self):
        from app.services.sandbox.provisioning_service import SandboxProvisioningService

        db = MagicMock()
        svc = self._make_svc(db)

        result = svc.provision(job_id=JOB_ID)
        assert "invitation_token" in result
        assert isinstance(result["invitation_token"], str)
        assert "." in result["invitation_token"]

    def test_provision_fails_when_seeder_raises(self):
        from app.services.sandbox.provisioning_service import (
            ProvisioningError,
            SandboxProvisioningService,
        )

        db = MagicMock()
        svc = self._make_svc(db)
        svc._seeder_service.seed.side_effect = RuntimeError("seeder boom")

        with pytest.raises(ProvisioningError, match="seeder"):
            svc.provision(job_id=JOB_ID)

        # Job must be marked failed
        failed_calls = [
            c for c in svc._job_repo.update.call_args_list if c.kwargs.get("status") == "failed"
        ]
        assert len(failed_calls) >= 1


# ── Admin sandboxes endpoint tests ────────────────────────────────────────────


def _make_sandboxes_client(mock_db, actor_factory=_admin_actor):
    _app = FastAPI()
    _app.include_router(sandboxes_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    return TestClient(_app, raise_server_exceptions=False)


class TestListSandboxesEndpoint:
    def test_returns_200_for_admin(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.list_all"
        ) as mock_list:
            mock_list.return_value = ([_fake_sandbox()], 1)
            client = _make_sandboxes_client(mock_db)
            resp = client.get("/api/v1/admin/sandboxes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "active"

    def test_returns_403_for_viewer(self):
        mock_db = MagicMock()
        client = _make_sandboxes_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get("/api/v1/admin/sandboxes")
        assert resp.status_code == 403

    def test_passes_status_filter(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.list_all"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            client = _make_sandboxes_client(mock_db)
            client.get("/api/v1/admin/sandboxes?status=active")
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["status"] == "active"

    def test_empty_list(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.list_all"
        ) as mock_list:
            mock_list.return_value = ([], 0)
            client = _make_sandboxes_client(mock_db)
            resp = client.get("/api/v1/admin/sandboxes")
        assert resp.json()["total"] == 0


class TestGetSandboxEndpoint:
    def test_returns_200_when_found(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.find_by_id"
        ) as mock_get:
            mock_get.return_value = _fake_sandbox()
            client = _make_sandboxes_client(mock_db)
            resp = client.get(f"/api/v1/admin/sandboxes/{SANDBOX_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(SANDBOX_ID)

    def test_returns_404_when_not_found(self):
        mock_db = MagicMock()
        with patch(
            "app.services.sandbox.sandbox_environment_repository.SandboxEnvironmentRepository.find_by_id"
        ) as mock_get:
            mock_get.return_value = None
            client = _make_sandboxes_client(mock_db)
            resp = client.get(f"/api/v1/admin/sandboxes/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_403_for_wrong_role(self):
        mock_db = MagicMock()
        client = _make_sandboxes_client(mock_db, actor_factory=_viewer_actor)
        resp = client.get(f"/api/v1/admin/sandboxes/{SANDBOX_ID}")
        assert resp.status_code == 403
