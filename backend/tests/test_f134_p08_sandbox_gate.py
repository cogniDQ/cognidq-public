"""
F134 P08 — Tests for SandboxFeatureGate + Sandbox User Endpoints

Tests:
  - SandboxContext.require_flag_false (each of 3 flags + pass-through)
  - platform_admin bypass
  - _load_sandbox_context DB logic
  - GET /sandbox/me (found, not-found, 404-for-non-sandbox)
  - GET /sandbox/onboarding (steps, progress)
  - POST /sandbox/onboarding/{step_id}/complete (valid, invalid step)
  - POST /sandbox/extension-request (records event)
  - Cross-tenant: sandbox gate does NOT activate for non-sandbox tenants
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
from app.api.v1.endpoints.sandbox_user import router as sandbox_router
from app.dependencies.sandbox_gate import (
    ONBOARDING_STEPS,
    SandboxContext,
    _load_sandbox_context,
    get_sandbox_context,
)
from app.models.database import get_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

ACTOR_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SANDBOX_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TENANT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

_ALL_FLAGS_ON = {
    "platform_admin_hidden": True,
    "destructive_operations_disabled": True,
    "external_integrations_disabled": True,
}

_EXPIRES_FUTURE = datetime.now(UTC) + timedelta(days=7)
_EXPIRES_PAST = datetime.now(UTC) - timedelta(days=1)


def _sandbox_ctx(flags=None, status="active", expires_at=None):
    return SandboxContext(
        is_sandbox=True,
        sandbox_id=SANDBOX_ID,
        tenant_id=TENANT_ID,
        workspace_id=WORKSPACE_ID,
        sandbox_status=status,
        expires_at=expires_at or _EXPIRES_FUTURE,
        flags=flags or {},
    )


def _non_sandbox_ctx():
    return SandboxContext(is_sandbox=False)


def _admin_actor():
    return ActorContext(actor_id=ACTOR_ID, actor_role="platform_admin")


def _sandbox_actor():
    return ActorContext(actor_id=ACTOR_ID, actor_role="sandbox_admin")


def _viewer_actor():
    return ActorContext(
        actor_id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        actor_role="platform_viewer",
    )


# ── SandboxContext unit tests ─────────────────────────────────────────────────


class TestSandboxContextFlags:
    def test_flag_false_passes_when_flag_off(self):
        ctx = _sandbox_ctx(flags={"destructive_operations_disabled": False})
        # Should not raise
        ctx.require_flag_false("destructive_operations_disabled")

    def test_flag_false_raises_when_flag_on(self):
        ctx = _sandbox_ctx(flags={"destructive_operations_disabled": True})
        with pytest.raises(TenantAPIError) as exc_info:
            ctx.require_flag_false("destructive_operations_disabled")
        err = exc_info.value
        assert err.status_code == 403
        assert err.code == "sandbox_forbidden"
        assert err.fields[0]["reason"] == "destructive_operations_disabled"

    def test_platform_admin_hidden_flag_raises(self):
        ctx = _sandbox_ctx(flags={"platform_admin_hidden": True})
        with pytest.raises(TenantAPIError) as exc_info:
            ctx.require_flag_false("platform_admin_hidden")
        assert exc_info.value.fields[0]["reason"] == "platform_admin_hidden"

    def test_external_integrations_disabled_flag_raises(self):
        ctx = _sandbox_ctx(flags={"external_integrations_disabled": True})
        with pytest.raises(TenantAPIError) as exc_info:
            ctx.require_flag_false("external_integrations_disabled")
        assert exc_info.value.fields[0]["reason"] == "external_integrations_disabled"

    def test_non_sandbox_never_raises_flags(self):
        ctx = _non_sandbox_ctx()
        # Even if we somehow pass flag names, non-sandbox never raises
        ctx.require_flag_false("destructive_operations_disabled")
        ctx.require_flag_false("platform_admin_hidden")
        ctx.require_flag_false("external_integrations_disabled")

    def test_remaining_days_positive(self):
        ctx = _sandbox_ctx(expires_at=datetime.now(UTC) + timedelta(days=5))
        assert ctx.remaining_days == 5

    def test_remaining_days_zero_when_expired(self):
        ctx = _sandbox_ctx(expires_at=_EXPIRES_PAST)
        assert ctx.remaining_days == 0

    def test_is_expired_true_for_suspended(self):
        ctx = _sandbox_ctx(status="suspended")
        assert ctx.is_expired is True

    def test_is_expired_false_for_active(self):
        ctx = _sandbox_ctx(status="active")
        assert ctx.is_expired is False

    def test_all_flags_on_raises_for_any(self):
        ctx = _sandbox_ctx(flags=_ALL_FLAGS_ON)
        for flag in _ALL_FLAGS_ON:
            with pytest.raises(TenantAPIError):
                ctx.require_flag_false(flag)


# ── _load_sandbox_context DB tests ───────────────────────────────────────────


class TestLoadSandboxContext:
    def test_returns_non_sandbox_when_no_row(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        ctx = _load_sandbox_context(db, ACTOR_ID)
        assert ctx.is_sandbox is False

    def test_returns_sandbox_when_row_found(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock(
            _mapping={
                "sandbox_id": str(SANDBOX_ID),
                "sandbox_status": "active",
                "expires_at": _EXPIRES_FUTURE,
                "tenant_id": str(TENANT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "flags": {"destructive_operations_disabled": True},
            }
        )
        ctx = _load_sandbox_context(db, ACTOR_ID)
        assert ctx.is_sandbox is True
        assert ctx.sandbox_id == SANDBOX_ID
        assert ctx.flags == {"destructive_operations_disabled": True}

    def test_parses_string_flags_json(self):
        """flags can arrive as JSON string from older psycopg2 drivers."""
        import json

        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock(
            _mapping={
                "sandbox_id": str(SANDBOX_ID),
                "sandbox_status": "active",
                "expires_at": _EXPIRES_FUTURE,
                "tenant_id": str(TENANT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "flags": json.dumps({"platform_admin_hidden": True}),
            }
        )
        ctx = _load_sandbox_context(db, ACTOR_ID)
        assert ctx.flags == {"platform_admin_hidden": True}

    def test_handles_null_flags(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock(
            _mapping={
                "sandbox_id": str(SANDBOX_ID),
                "sandbox_status": "active",
                "expires_at": None,
                "tenant_id": str(TENANT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "flags": None,
            }
        )
        ctx = _load_sandbox_context(db, ACTOR_ID)
        assert ctx.flags == {}


# ── Test client helpers ───────────────────────────────────────────────────────


def _make_client(mock_db, actor_factory, sandbox_ctx_factory=None):
    _app = FastAPI()
    _app.include_router(sandbox_router, prefix="/api/v1")
    _app.dependency_overrides[get_db] = lambda: mock_db
    _app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    _app.dependency_overrides[get_actor_context] = lambda: actor_factory()
    if sandbox_ctx_factory is not None:
        _app.dependency_overrides[get_sandbox_context] = lambda: sandbox_ctx_factory()
    return TestClient(_app, raise_server_exceptions=False)


# ── GET /sandbox/me tests ─────────────────────────────────────────────────────


class TestGetSandboxMe:
    def test_returns_200_for_sandbox_user(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, lambda: _sandbox_ctx(flags=_ALL_FLAGS_ON))
        resp = client.get("/api/v1/sandbox/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sandbox_id"] == str(SANDBOX_ID)
        assert body["remaining_days"] >= 0
        assert "flags" in body

    def test_returns_404_for_non_sandbox_user(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _non_sandbox_ctx)
        resp = client.get("/api/v1/sandbox/me")
        assert resp.status_code == 404

    def test_platform_admin_gets_404(self):
        """platform_admin has no sandbox env → 404."""
        db = MagicMock()
        client = _make_client(db, _admin_actor, _non_sandbox_ctx)
        resp = client.get("/api/v1/sandbox/me")
        assert resp.status_code == 404

    def test_is_expired_field_present(self):
        db = MagicMock()
        expired_ctx = lambda: _sandbox_ctx(status="expired")
        client = _make_client(db, _sandbox_actor, expired_ctx)
        resp = client.get("/api/v1/sandbox/me")
        assert resp.status_code == 200
        assert resp.json()["is_expired"] is True


# ── GET /sandbox/onboarding tests ────────────────────────────────────────────


class TestGetOnboarding:
    def test_returns_six_steps(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        resp = client.get("/api/v1/sandbox/onboarding")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["steps"]) == len(ONBOARDING_STEPS)
        assert body["progress"]["total"] == len(ONBOARDING_STEPS)

    def test_correct_step_ids(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        resp = client.get("/api/v1/sandbox/onboarding")
        step_ids = [s["step_id"] for s in resp.json()["steps"]]
        assert step_ids == list(ONBOARDING_STEPS)

    def test_completed_steps_reflected(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [
            MagicMock(_mapping={"step_id": "view_dataset"}),
            MagicMock(_mapping={"step_id": "view_rule"}),
        ]
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        resp = client.get("/api/v1/sandbox/onboarding")
        body = resp.json()
        step_map = {s["step_id"]: s["completed"] for s in body["steps"]}
        assert step_map["view_dataset"] is True
        assert step_map["view_rule"] is True
        assert step_map["run_check"] is False
        assert body["progress"]["completed"] == 2

    def test_403_for_non_sandbox(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _non_sandbox_ctx)
        resp = client.get("/api/v1/sandbox/onboarding")
        assert resp.status_code == 403


# ── POST /sandbox/onboarding/{step_id}/complete tests ────────────────────────


class TestCompleteOnboardingStep:
    def test_returns_200_for_valid_step(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        with patch(
            "app.services.sandbox.sandbox_usage_event_repository.SandboxUsageEventRepository.insert"
        ):
            resp = client.post("/api/v1/sandbox/onboarding/view_dataset/complete")
        assert resp.status_code == 200
        body = resp.json()
        assert body["step_id"] == "view_dataset"
        assert body["completed"] is True

    def test_returns_422_for_unknown_step(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        resp = client.post("/api/v1/sandbox/onboarding/not_a_real_step/complete")
        assert resp.status_code == 422

    def test_403_for_non_sandbox(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _non_sandbox_ctx)
        resp = client.post("/api/v1/sandbox/onboarding/view_dataset/complete")
        assert resp.status_code == 403


# ── POST /sandbox/extension-request tests ────────────────────────────────────


class TestExtensionRequest:
    def test_returns_202_for_sandbox_user(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        with patch(
            "app.services.sandbox.sandbox_usage_event_repository.SandboxUsageEventRepository.insert"
        ):
            resp = client.post(
                "/api/v1/sandbox/extension-request",
                json={"message": "Please extend my sandbox for another week."},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "received"

    def test_records_extension_event(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        with patch(
            "app.services.sandbox.sandbox_usage_event_repository.SandboxUsageEventRepository.insert"
        ) as mock_insert:
            client.post(
                "/api/v1/sandbox/extension-request",
                json={"message": "Extend please"},
            )
        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args.kwargs
        assert call_kwargs["event_type"] == "extension_requested"
        assert call_kwargs["event_payload"]["message"] == "Extend please"

    def test_works_without_message(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        with patch(
            "app.services.sandbox.sandbox_usage_event_repository.SandboxUsageEventRepository.insert"
        ):
            resp = client.post("/api/v1/sandbox/extension-request")
        assert resp.status_code == 202

    def test_403_for_non_sandbox(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _non_sandbox_ctx)
        resp = client.post("/api/v1/sandbox/extension-request")
        assert resp.status_code == 403

    def test_emits_admin_notification_stub(self):
        db = MagicMock()
        client = _make_client(db, _sandbox_actor, _sandbox_ctx)
        with (
            patch(
                "app.services.sandbox.sandbox_usage_event_repository.SandboxUsageEventRepository.insert"
            ),
            patch(
                "app.api.v1.endpoints.sandbox_user._emit_admin_extension_notification"
            ) as mock_notify,
        ):
            client.post(
                "/api/v1/sandbox/extension-request",
                json={"message": "Need more time"},
            )
        mock_notify.assert_called_once()


# ── Cross-tenant isolation tests ──────────────────────────────────────────────


class TestCrossTenantIsolation:
    """
    Verify that the gate DB query never returns rows from a different tenant.
    The query filters by wra.user_id, so an actor in a non-sandbox tenant
    gets SandboxContext(is_sandbox=False) and all endpoints work normally.
    """

    def test_non_sandbox_actor_gets_non_sandbox_context(self):
        db = MagicMock()
        # DB returns no row (actor is in a regular tenant)
        db.execute.return_value.fetchone.return_value = None
        ctx = _load_sandbox_context(db, ACTOR_ID)
        assert ctx.is_sandbox is False
        # No flags → no 403
        ctx.require_flag_false("destructive_operations_disabled")

    def test_sandbox_gate_query_uses_actor_id(self):
        """
        The DB query must be parameterised by the actor's own user_id —
        not a caller-supplied value — ensuring cross-tenant isolation.
        """
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        _load_sandbox_context(db, ACTOR_ID)
        # Verify the execute was called with user_id = actor's UUID
        call_args = db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert str(ACTOR_ID) in str(params)
