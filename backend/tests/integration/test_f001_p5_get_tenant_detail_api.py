"""
Packet 5 — API contract + integration tests: GET /api/v1/tenants/{tenant_id}
=============================================================================

Tests cover:
    • Happy path          — 200 OK, correct envelope, exactly 18 fields
    • Access control      — 401/403 enforcement
    • Not-found           — 404 for a valid UUID that has no matching row
    • Path-parameter      — 400 for malformed / non-UUID strings
    • Registry degradation— workspace / user registry failures degrade
                            gracefully (count=0, available=False);
                            OPEN circuit has the same effect
    • Field-value fidelity— DB values round-trip unchanged to the response

Test isolation
--------------
One tenant (slug ``p5test-detail-1``) is inserted at module scope and deleted
in teardown.  All tests read from that single row; no writes happen during
tests.  Registry calls are replaced with ``StubRegistryClient`` instances via
``app.dependency_overrides``.  Default stubs return workspace_count=5,
user_count=12 so every test that does not override them gets consistent values.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/integration/test_f001_p5_get_tenant_detail_api.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient
from jose import jwt

psycopg2.extras.register_uuid()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

_P5_SLUG_PREFIX = "p5test-"

# ---------------------------------------------------------------------------
# Lazy helpers
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import settings

    return settings


def _make_token(role: str) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": role,
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — starts/stops the app once per module."""
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _make_token("platform_admin")


@pytest.fixture(scope="module")
def viewer_token() -> str:
    return _make_token("platform_viewer")


@pytest.fixture(scope="module")
def customer_token() -> str:
    return _make_token("customer_actor")


@pytest.fixture(scope="module", autouse=True)
def p5_test_tenant():
    """Insert one tenant and register default stub registry overrides.

    Yields a dict with keys ``tenant_id``, ``tenant_name``, ``tenant_slug``,
    and ``actor_id`` for use in test assertions.

    Teardown removes dependency overrides and deletes all ``p5test-*`` rows.
    """
    from app.main import app
    from app.services.tenants.registry import (
        StubRegistryClient,
        get_user_registry_client,
        get_workspace_registry_client,
    )

    tid = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan,
                    created_by, updated_by, version
                ) VALUES (
                    %s, %s, %s,
                    %s::control.tenant_status_enum,
                    %s::control.tenant_region_enum,
                    %s::control.tenant_plan_enum,
                    %s, %s, %s
                )
                """,
                (
                    tid,
                    "P5 Detail Corp",
                    f"{_P5_SLUG_PREFIX}detail-1",
                    "active",
                    "eu-west",
                    "starter",
                    actor_id,
                    actor_id,
                    0,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    # Install default stubs so every non-degradation test gets predictable counts
    stub_ws = StubRegistryClient(fixed_count=5)
    stub_user = StubRegistryClient(fixed_count=12)
    app.dependency_overrides[get_workspace_registry_client] = lambda: stub_ws
    app.dependency_overrides[get_user_registry_client] = lambda: stub_user

    yield {
        "tenant_id": tid,
        "tenant_name": "P5 Detail Corp",
        "tenant_slug": f"{_P5_SLUG_PREFIX}detail-1",
        "actor_id": actor_id,
    }

    # Teardown — restore defaults + delete DB rows
    app.dependency_overrides.pop(get_workspace_registry_client, None)
    app.dependency_overrides.pop(get_user_registry_client, None)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM control.tenant_audit_logs WHERE tenant_id IN "
                "(SELECT tenant_id FROM control.tenants WHERE tenant_slug LIKE %s)",
                (f"{_P5_SLUG_PREFIX}%",),
            )
            cur.execute(
                "DELETE FROM control.tenants WHERE tenant_slug LIKE %s",
                (f"{_P5_SLUG_PREFIX}%",),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


_BASE = "/api/v1/tenants"


def _url(tenant_id: str) -> str:
    return f"{_BASE}/{tenant_id}"


# ===========================================================================
# AC-1 — Happy path: 200 OK with correct envelope and field shapes
# ===========================================================================


class TestHappyPath:
    def test_200_with_admin_token(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        assert resp.status_code == 200, resp.text

    def test_response_has_data_key(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        assert "data" in resp.json()

    def test_data_has_exactly_18_fields(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert len(data) == 18

    def test_all_field_names_correct(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        expected_keys = {
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "status",
            "status_reason",
            "region",
            "plan",
            "service_start_date",
            "tenant_notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "workspace_count",
            "workspace_count_available",
            "user_count",
            "user_count_available",
            "audit_summary_link",
        }
        assert set(data.keys()) == expected_keys

    def test_workspace_count_is_integer(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert isinstance(data["workspace_count"], int)

    def test_workspace_count_available_is_bool(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert isinstance(data["workspace_count_available"], bool)

    def test_audit_summary_link_correct_format(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        tid = p5_test_tenant["tenant_id"]
        assert data["audit_summary_link"] == f"/api/v1/tenants/{tid}/audit-logs"

    def test_timestamps_are_iso8601_strings(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        for field in ("created_at", "updated_at"):
            assert isinstance(data[field], str), f"{field} must be a string"
            datetime.fromisoformat(data[field])  # raises ValueError if malformed


# ===========================================================================
# AC-2 — Access control: 401 / 403 enforcement
# ===========================================================================


class TestAccessControl:
    def test_missing_token_returns_401(self, client, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]))
        assert resp.status_code == 401, resp.text

    def test_invalid_token_returns_401(self, client, p5_test_tenant):
        resp = client.get(
            _url(p5_test_tenant["tenant_id"]),
            headers={"Authorization": "Bearer not.a.valid.token"},
        )
        assert resp.status_code == 401, resp.text

    def test_customer_actor_returns_403(self, client, customer_token, p5_test_tenant):
        resp = client.get(
            _url(p5_test_tenant["tenant_id"]),
            headers=_auth(customer_token),
        )
        assert resp.status_code == 403, resp.text

    def test_platform_viewer_is_allowed(self, client, viewer_token, p5_test_tenant):
        resp = client.get(
            _url(p5_test_tenant["tenant_id"]),
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 200, resp.text

    def test_platform_admin_is_allowed(self, client, admin_token, p5_test_tenant):
        resp = client.get(
            _url(p5_test_tenant["tenant_id"]),
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text


# ===========================================================================
# AC-3 — Not-found: valid UUID with no matching row returns 404
# ===========================================================================


class TestNotFound:
    def test_nonexistent_uuid_returns_404(self, client, admin_token):
        unknown = str(uuid.uuid4())
        resp = client.get(_url(unknown), headers=_auth(admin_token))
        assert resp.status_code == 404, resp.text

    def test_404_error_envelope_shape(self, client, admin_token):
        unknown = str(uuid.uuid4())
        resp = client.get(_url(unknown), headers=_auth(admin_token))
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert body["error"]["code"] == "not_found"


# ===========================================================================
# AC-4 — Path-parameter validation: 400 for malformed inputs
# ===========================================================================


class TestPathParam:
    def test_plain_string_returns_400(self, client, admin_token):
        resp = client.get(_url("not-a-uuid"), headers=_auth(admin_token))
        assert resp.status_code == 400, resp.text

    def test_non_uuid_string_returns_400(self, client, admin_token):
        resp = client.get(_url("12345678-0000-0000-0000"), headers=_auth(admin_token))
        assert resp.status_code == 400, resp.text

    def test_invalid_path_parameter_error_code(self, client, admin_token):
        resp = client.get(_url("not-a-uuid"), headers=_auth(admin_token))
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "invalid_path_parameter"


# ===========================================================================
# AC-5 — Registry degradation: graceful fallback (count=0, available=False)
# ===========================================================================


class TestRegistryDegradation:
    """Each test temporarily overrides one or both registry deps, asserts the
    response is still 200, verifies count=0 / available=False for the
    affected registry, then restores the default stub so later tests are not
    polluted."""

    def test_workspace_registry_fails_returns_200_available_false(
        self, client, admin_token, p5_test_tenant
    ):
        from app.main import app
        from app.services.tenants.registry import (
            StubRegistryClient,
            get_workspace_registry_client,
        )

        failing_ws = StubRegistryClient(raise_exc=RuntimeError("ws down"))
        app.dependency_overrides[get_workspace_registry_client] = lambda: failing_ws
        try:
            resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
            assert resp.status_code == 200, resp.text
            data = resp.json()["data"]
            assert data["workspace_count"] == 0
            assert data["workspace_count_available"] is False
        finally:
            stub_ws = StubRegistryClient(fixed_count=5)
            app.dependency_overrides[get_workspace_registry_client] = lambda: stub_ws

    def test_user_registry_timeout_returns_200_count_zero(
        self, client, admin_token, p5_test_tenant
    ):
        from app.main import app
        from app.services.tenants.registry import (
            CircuitBreaker,
            CircuitBreakerWrappedClient,
            StubRegistryClient,
            get_user_registry_client,
        )

        # A 2-second delay far exceeds the 500 ms timeout enforced by the wrapper
        slow_inner = StubRegistryClient(delay=2.0)
        timeout_cb = CircuitBreaker()
        timeout_client = CircuitBreakerWrappedClient(slow_inner, timeout_cb, timeout=0.5)
        app.dependency_overrides[get_user_registry_client] = lambda: timeout_client
        try:
            resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
            assert resp.status_code == 200, resp.text
            data = resp.json()["data"]
            assert data["user_count"] == 0
            assert data["user_count_available"] is False
        finally:
            stub_user = StubRegistryClient(fixed_count=12)
            app.dependency_overrides[get_user_registry_client] = lambda: stub_user

    def test_circuit_open_returns_200_available_false(self, client, admin_token, p5_test_tenant):
        from app.main import app
        from app.services.tenants.registry import (
            CircuitBreaker,
            CircuitBreakerWrappedClient,
            StubRegistryClient,
            get_workspace_registry_client,
        )

        inner = StubRegistryClient(raise_exc=RuntimeError("down"))
        cb = CircuitBreaker(threshold=1)
        cb.record_failure()  # threshold=1 so one failure opens the circuit immediately
        open_client = CircuitBreakerWrappedClient(inner, cb)
        app.dependency_overrides[get_workspace_registry_client] = lambda: open_client
        try:
            resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
            assert resp.status_code == 200, resp.text
            data = resp.json()["data"]
            assert data["workspace_count"] == 0
            assert data["workspace_count_available"] is False
        finally:
            stub_ws = StubRegistryClient(fixed_count=5)
            app.dependency_overrides[get_workspace_registry_client] = lambda: stub_ws

    def test_both_registries_available_returns_true_flags(
        self, client, admin_token, p5_test_tenant
    ):
        # Default stubs (ws=5, user=12) are still active — no override needed
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["workspace_count_available"] is True
        assert data["user_count_available"] is True


# ===========================================================================
# AC-6 — Field-value fidelity: DB values round-trip correctly
# ===========================================================================


class TestFieldValues:
    def test_all_db_fields_match_inserted_values(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert data["tenant_id"] == p5_test_tenant["tenant_id"]
        assert data["tenant_name"] == "P5 Detail Corp"
        assert data["tenant_slug"] == f"{_P5_SLUG_PREFIX}detail-1"
        assert data["status"] == "active"
        assert data["region"] == "eu-west"
        assert data["plan"] == "starter"

    def test_status_reason_null_for_active_tenant(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert data["status_reason"] is None

    def test_service_start_date_null_when_not_set(self, client, admin_token, p5_test_tenant):
        resp = client.get(_url(p5_test_tenant["tenant_id"]), headers=_auth(admin_token))
        data = resp.json()["data"]
        assert data["service_start_date"] is None
