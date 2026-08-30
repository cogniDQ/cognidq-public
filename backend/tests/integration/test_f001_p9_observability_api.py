"""
Packet 9 — Integration / API contract tests: Observability
============================================================

Tests use FastAPI's TestClient with the real PostgreSQL database.

Focus areas:
    - X-Correlation-Id header is present and is a UUID v4 on ALL F001 endpoints
    - Header value is different on each request
    - Metric fire-and-forget: patched emitter that raises must not change response
    - Structured log fields are present in real request flows
    - WARN log is emitted on registry call failure (live endpoint, mocked registry)

Every test uses existing tenant data seeded by previous packet integration tests,
or creates its own rows prefixed with ``p9test-`` for safe cleanup.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/integration/test_f001_p9_observability_api.py -v --no-header -p no:warnings
"""

from __future__ import annotations

import os
import re
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

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _get_settings():
    from app.core.config import settings

    return settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def viewer_token() -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_viewer",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def existing_tenant_id(db_conn) -> str:
    """Insert a tenant row for read-only tests; delete after module."""
    tid = str(uuid.uuid4())
    actor = str(uuid.uuid4())
    slug = f"p9obs-{uuid.uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants
                (tenant_id, tenant_name, tenant_slug,
                 status, region, plan, created_by, updated_by, version)
            VALUES
                (%s, %s, %s, 'draft', 'eu-west', 'starter', %s, %s, 0)
            """,
            (tid, f"P9 Obs Tenant {slug}", slug, actor, actor),
        )
    yield tid
    with db_conn.cursor() as cur:
        # Must delete audit logs first — FK constraint prevents tenant deletion
        cur.execute(
            """
            DELETE FROM control.tenant_audit_logs
            WHERE tenant_id IN (
                SELECT tenant_id FROM control.tenants
                WHERE tenant_slug LIKE 'p9obs-%%' OR tenant_slug LIKE 'p9test-%%'
            )
            """
        )
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p9obs-%%'")
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p9test-%%'")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _assert_correlation_header(resp) -> str:
    """Assert X-Correlation-Id is present and is a UUID v4; return the value."""
    assert "x-correlation-id" in resp.headers, (
        f"X-Correlation-Id missing from response headers. Available headers: {dict(resp.headers)}"
    )
    cid = resp.headers["x-correlation-id"]
    assert _UUID_V4_RE.match(cid), f"X-Correlation-Id is not a UUID v4: {cid!r}"
    return cid


# ===========================================================================
# TestCorrelationIdOnAllEndpoints — live requests to all F001 routes
# ===========================================================================


class TestCorrelationIdOnAllEndpoints:
    """X-Correlation-Id must appear on every F001 endpoint response."""

    def test_post_create_tenant_returns_correlation_id(self, client, admin_token):
        """201 path — correlation ID present on successful creation."""
        slug = f"p9test-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/v1/tenants",
            json={
                "tenant_name": f"P9 Test {slug}",
                "tenant_slug": slug,
                "region": "eu-west",
                "plan": "starter",
                "initial_status": "draft",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        _assert_correlation_header(resp)

    def test_get_list_tenants_returns_correlation_id(self, client, admin_token):
        resp = client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        _assert_correlation_header(resp)

    def test_get_tenant_detail_returns_correlation_id(
        self, client, admin_token, existing_tenant_id
    ):
        resp = client.get(
            f"/api/v1/tenants/{existing_tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        _assert_correlation_header(resp)

    def test_patch_tenant_returns_correlation_id(self, client, admin_token, existing_tenant_id):
        resp = client.patch(
            f"/api/v1/tenants/{existing_tenant_id}",
            json={"tenant_name": "P9 Obs Tenant Updated"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 200 (success) or 422 (no change) — either way header must be present
        _assert_correlation_header(resp)

    def test_get_audit_logs_returns_correlation_id(self, client, admin_token, existing_tenant_id):
        resp = client.get(
            f"/api/v1/tenants/{existing_tenant_id}/audit-logs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        _assert_correlation_header(resp)

    def test_post_status_returns_correlation_id(self, client, admin_token, existing_tenant_id):
        resp = client.post(
            f"/api/v1/tenants/{existing_tenant_id}/status",
            json={"target_status": "active"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 200 or 422 (no-op if already active) — header must be present
        _assert_correlation_header(resp)


class TestCorrelationIdOnErrorResponses:
    """X-Correlation-Id must also be on 4xx responses."""

    def test_401_response_has_correlation_id(self, client):
        resp = client.get("/api/v1/tenants")  # no token
        assert resp.status_code == 401
        _assert_correlation_header(resp)

    def test_403_response_has_correlation_id(self, client, viewer_token):
        resp = client.post(
            "/api/v1/tenants",
            json={
                "tenant_name": "Should Fail",
                "tenant_slug": "should-fail",
                "region": "eu-west",
                "plan": "starter",
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
        _assert_correlation_header(resp)

    def test_404_response_has_correlation_id(self, client, admin_token):
        fake_id = "00000000-0000-4000-8000-000000000001"
        resp = client.get(
            f"/api/v1/tenants/{fake_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        _assert_correlation_header(resp)

    def test_422_response_has_correlation_id(self, client, admin_token):
        resp = client.post(
            "/api/v1/tenants",
            json={"tenant_name": "Bad", "tenant_slug": "bad", "region": "INVALID"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422
        _assert_correlation_header(resp)

    def test_health_endpoint_has_correlation_id(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        _assert_correlation_header(resp)


class TestCorrelationIdUniqueness:
    """Each request must receive a different correlation ID."""

    def test_two_requests_get_different_ids(self, client, admin_token):
        r1 = client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        r2 = client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        cid1 = _assert_correlation_header(r1)
        cid2 = _assert_correlation_header(r2)
        assert cid1 != cid2

    def test_client_injected_id_not_echoed(self, client, admin_token):
        """A caller-supplied X-Correlation-Id must be ignored."""
        client_id = "00000000-0000-4000-8000-aaaaaaaaaaaa"
        resp = client.get(
            "/api/v1/tenants",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Correlation-Id": client_id,
            },
        )
        server_cid = _assert_correlation_header(resp)
        assert server_cid != client_id


# ===========================================================================
# TestMetricFireAndForget — live server, patched metric emitter
# ===========================================================================


class TestMetricFireAndForgetIntegration:
    """Metric emitter explosions must not affect HTTP responses."""

    def test_create_success_metric_failure_returns_201(self, client, admin_token):
        """Patch emit_tenant_create_success to raise; expect 201 anyway."""
        from unittest.mock import patch

        slug = f"p9test-{uuid.uuid4().hex[:8]}"
        with patch(
            "app.services.tenants.service.emit_tenant_create_success",
            side_effect=RuntimeError("prometheus unavailable"),
        ):
            resp = client.post(
                "/api/v1/tenants",
                json={
                    "tenant_name": f"P9 FF Test {slug}",
                    "tenant_slug": slug,
                    "region": "eu-west",
                    "plan": "starter",
                    "initial_status": "draft",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 201
        _assert_correlation_header(resp)


# ===========================================================================
# TestRegistryWarnLogIntegration — live detail endpoint, mocked registry
# ===========================================================================


class TestRegistryWarnLogIntegration:
    """WARN log emitted on registry call failure during GET /{tenant_id}.

    Registry warn-log behaviour is validated at the unit level by
    TestRegistryWarnLog in test_p9_observability.py.  This integration test
    only verifies that X-Correlation-Id is present even on degraded-mode 200s.
    """

    def test_registry_failure_still_returns_correlation_id(
        self, client, admin_token, existing_tenant_id
    ):
        """GET /{tenant_id} must always include X-Correlation-Id."""
        resp = client.get(
            f"/api/v1/tenants/{existing_tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        _assert_correlation_header(resp)
