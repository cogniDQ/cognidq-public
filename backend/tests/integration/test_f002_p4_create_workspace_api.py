"""
Packet 4 — API contract + integration tests: POST /api/v1/workspaces
=====================================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database. JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test that writes a row uses a slug prefixed ``p4test-`` so that the
module-level cleanup fixture can delete those rows without touching other
data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f002_p4_create_workspace_api.py -v

Environment variable required:
    DATABASE_URL  (set automatically in the Docker service environment)
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


# Import settings lazily to avoid executing this at collection time
def _get_settings():
    from app.core.config import settings

    return settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — starts/stops the app once per module."""
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def test_tenant_id() -> uuid.UUID:
    """
    Create a test tenant for workspace tests.
    Returns the tenant_id UUID.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()

    with conn.cursor() as cur:
        # Insert test tenant (omit generated tenant_name_lower column)
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, 'P4 Test Tenant', 'p4test-tenant',
                'active', 'us-east', 'enterprise',
                NOW(), NOW(), %s, %s, 0
            ) ON CONFLICT (tenant_slug) DO UPDATE
            SET status = 'active'
            RETURNING tenant_id
            """,
            (tenant_id, uuid.uuid4(), uuid.uuid4()),
        )
        result = cur.fetchone()
        if result:
            tenant_id = result[0]

    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def workspace_admin_token(test_tenant_id: uuid.UUID) -> str:
    """Valid workspace_administrator JWT for the test tenant."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "workspace_administrator",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def platform_admin_token() -> str:
    """Valid platform_admin JWT — wrong role for workspace operations."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "tenant_id": str(uuid.uuid4()),  # Include tenant_id to pass JWT validation
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_workspaces():
    """Delete all test-created workspace rows after the module finishes."""
    yield  # all tests run first

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Delete audit logs for test workspaces
        cur.execute(
            """
            DELETE FROM control.workspace_audit_logs
            WHERE workspace_id IN (
                SELECT workspace_id FROM control.workspaces
                WHERE workspace_slug LIKE 'p4test-%'
            )
            """
        )
        # Delete role assignments for test workspaces (if table exists)
        # Note: role_assignments table is created in F007, may not exist yet
        cur.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'control' 
                    AND table_name = 'role_assignments'
                ) THEN
                    DELETE FROM control.role_assignments
                    WHERE workspace_id IN (
                        SELECT workspace_id FROM control.workspaces
                        WHERE workspace_slug LIKE 'p4test-%'
                    );
                END IF;
            END $$;
            """
        )
        # Delete test workspaces
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p4test-%'")
        # Delete test tenant
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug = 'p4test-tenant'")
    conn.close()


def _slug(suffix: str) -> str:
    """Build a test-scoped slug guaranteed to start with 'p4test-'."""
    return f"p4test-{suffix}"


def _min_body(**overrides) -> dict:
    """Return the minimum valid request body."""
    slug = overrides.get("workspace_slug", _slug("default"))
    suffix = slug.replace("p4test-", "").replace("-", " ").title()
    base = {
        "workspace_name": f"P4 {suffix} Workspace",
        "workspace_slug": slug,
    }
    base.update(overrides)
    return base


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Happy Path Tests
# ===========================================================================


class TestHappyPath:
    """Test successful workspace creation scenarios."""

    def test_minimal_payload_returns_201(self, client, workspace_admin_token):
        """Minimal valid payload (name + slug only) returns HTTP 201."""
        body = _min_body(workspace_slug=_slug("minimal"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 201
        data = resp.json()["data"]

        # Verify all fields present
        assert data["workspace_id"] is not None
        assert data["tenant_id"] is not None
        assert data["workspace_name"] == body["workspace_name"]
        assert data["workspace_slug"] == body["workspace_slug"]
        assert data["description"] is None
        assert data["default_timezone"] == "UTC"  # Default
        assert data["status"] == "active"
        assert data["status_reason"] is None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
        assert data["created_by"] is not None
        assert data["updated_by"] is not None

    def test_full_payload_with_optional_fields(self, client, workspace_admin_token):
        """Full payload with description and timezone returns HTTP 201."""
        body = _min_body(
            workspace_slug=_slug("full"),
            description="This is a test workspace with all fields",
            default_timezone="America/New_York",
        )
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 201
        data = resp.json()["data"]

        assert data["workspace_name"] == body["workspace_name"]
        assert data["workspace_slug"] == body["workspace_slug"]
        assert data["description"] == body["description"]
        assert data["default_timezone"] == "America/New_York"

    def test_null_description_accepted(self, client, workspace_admin_token):
        """Explicit null description is accepted."""
        body = _min_body(workspace_slug=_slug("nulldesc"), description=None)
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["description"] is None

    def test_audit_log_written(self, client, workspace_admin_token):
        """Verify audit log entry is created for workspace_created event."""
        body = _min_body(workspace_slug=_slug("audit"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 201
        workspace_id = resp.json()["data"]["workspace_id"]

        # Query audit log
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT action_type, new_data, previous_data
                FROM control.workspace_audit_logs
                WHERE workspace_id = %s
                ORDER BY occurred_at DESC
                LIMIT 1
                """,
                (uuid.UUID(workspace_id),),
            )
            log = cur.fetchone()
        conn.close()

        assert log is not None
        assert log["action_type"] == "workspace_created"
        assert log["previous_data"] is None
        assert log["new_data"]["workspace_name"] == body["workspace_name"]
        # Verify stripped keys not in new_data
        assert "workspace_name_lower" not in log["new_data"]
        assert "version" not in log["new_data"]


# ===========================================================================
# Authentication Tests
# ===========================================================================


class TestAuthentication:
    """Test JWT authentication requirements."""

    def test_missing_authorization_header_401(self, client):
        """Missing Authorization header returns HTTP 401."""
        body = _min_body(workspace_slug=_slug("noauth"))
        resp = client.post("/api/v1/workspaces", json=body)

        assert resp.status_code == 401
        error = resp.json()["error"]
        assert error["code"] == "unauthorized"

    def test_invalid_token_401(self, client):
        """Invalid JWT returns HTTP 401."""
        body = _min_body(workspace_slug=_slug("badtoken"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth("invalid.jwt.token"))

        assert resp.status_code == 401
        error = resp.json()["error"]
        assert error["code"] == "unauthorized"

    def test_expired_token_401(self, client, test_tenant_id):
        """Expired JWT returns HTTP 401."""
        s = _get_settings()
        payload = {
            "actor_id": str(uuid.uuid4()),
            "actor_role": "workspace_administrator",
            "tenant_id": str(test_tenant_id),
            "exp": datetime.now(tz=UTC) - timedelta(hours=1),  # Expired
        }
        expired_token = jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)

        body = _min_body(workspace_slug=_slug("expired"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(expired_token))

        assert resp.status_code == 401


# ===========================================================================
# Authorization Tests
# ===========================================================================


class TestAuthorization:
    """Test role-based authorization."""

    def test_platform_admin_role_403(self, client, platform_admin_token):
        """platform_admin role is not allowed (requires workspace_administrator)."""
        body = _min_body(workspace_slug=_slug("wrongrole"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(platform_admin_token))

        assert resp.status_code == 403
        error = resp.json()["error"]
        assert error["code"] == "insufficient_permissions"


# ===========================================================================
# Validation Tests
# ===========================================================================


class TestValidation:
    """Test request payload validation."""

    def test_missing_workspace_name_422(self, client, workspace_admin_token):
        """Missing required workspace_name returns HTTP 422."""
        body = {"workspace_slug": _slug("noname")}
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 422
        error = resp.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "workspace_name" for f in error["fields"])

    def test_missing_workspace_slug_422(self, client, workspace_admin_token):
        """Missing required workspace_slug returns HTTP 422."""
        body = {"workspace_name": "Test Workspace"}
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 422
        error = resp.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "workspace_slug" for f in error["fields"])

    def test_empty_workspace_name_422(self, client, workspace_admin_token):
        """Empty workspace_name returns HTTP 422."""
        body = _min_body(workspace_slug=_slug("emptyname"), workspace_name="")
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 422
        error = resp.json()["error"]
        assert any(f["field"] == "workspace_name" for f in error["fields"])

    def test_invalid_timezone_422(self, client, workspace_admin_token):
        """Invalid timezone returns HTTP 422."""
        body = _min_body(workspace_slug=_slug("badtz"), default_timezone="Invalid/Timezone")
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 422
        error = resp.json()["error"]
        assert any(f["field"] == "default_timezone" for f in error["fields"])


# ===========================================================================
# Forbidden/Unknown Field Tests
# ===========================================================================


class TestForbiddenFields:
    """Test forbidden field detection (HTTP 400)."""

    def test_forbidden_field_tenant_id_400(self, client, workspace_admin_token):
        """Including forbidden field tenant_id returns HTTP 400."""
        body = _min_body(workspace_slug=_slug("forbid-tenant"), tenant_id=str(uuid.uuid4()))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["code"] == "invalid_fields"
        assert any(f["field"] == "tenant_id" for f in error["fields"])

    def test_forbidden_field_workspace_id_400(self, client, workspace_admin_token):
        """Including forbidden field workspace_id returns HTTP 400."""
        body = _min_body(workspace_slug=_slug("forbid-wsid"), workspace_id=str(uuid.uuid4()))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert any(f["field"] == "workspace_id" for f in error["fields"])

    def test_unknown_field_400(self, client, workspace_admin_token):
        """Including unknown field returns HTTP 400."""
        body = _min_body(workspace_slug=_slug("unknown"), unknown_field="some value")
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert any(f["field"] == "unknown_field" for f in error["fields"])


# ===========================================================================
# Business Rule Tests
# ===========================================================================


class TestBusinessRules:
    """Test business rule enforcement."""

    def test_duplicate_name_422(self, client, workspace_admin_token):
        """Creating workspace with duplicate name (case-insensitive) returns HTTP 422."""
        body1 = _min_body(workspace_slug=_slug("dup1"))
        resp1 = client.post("/api/v1/workspaces", json=body1, headers=_auth(workspace_admin_token))
        assert resp1.status_code == 201

        # Try to create with same name but different slug
        body2 = _min_body(workspace_slug=_slug("dup2"), workspace_name=body1["workspace_name"])
        resp2 = client.post("/api/v1/workspaces", json=body2, headers=_auth(workspace_admin_token))

        assert resp2.status_code == 422
        error = resp2.json()["error"]
        assert error["code"] == "duplicate_name"

    def test_duplicate_slug_422(self, client, workspace_admin_token):
        """Creating workspace with duplicate slug returns HTTP 422."""
        body1 = _min_body(workspace_slug=_slug("dupslug"))
        resp1 = client.post("/api/v1/workspaces", json=body1, headers=_auth(workspace_admin_token))
        assert resp1.status_code == 201

        # Try to create with same slug but different name
        body2 = _min_body(workspace_slug=body1["workspace_slug"], workspace_name="Different Name")
        resp2 = client.post("/api/v1/workspaces", json=body2, headers=_auth(workspace_admin_token))

        assert resp2.status_code == 422
        error = resp2.json()["error"]
        assert error["code"] == "duplicate_slug"

    def test_tenant_not_active_422(self, client, workspace_admin_token):
        """Creating workspace when tenant is not active returns HTTP 422."""
        # First, suspend the tenant
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.tenants SET status = 'suspended', status_reason = 'Testing workspace creation rejection' "
                "WHERE tenant_slug = 'p4test-tenant'"
            )
        conn.close()

        body = _min_body(workspace_slug=_slug("suspended"))
        resp = client.post("/api/v1/workspaces", json=body, headers=_auth(workspace_admin_token))

        # Restore tenant to active
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.tenants SET status = 'active', status_reason = NULL "
                "WHERE tenant_slug = 'p4test-tenant'"
            )
        conn.close()

        assert resp.status_code == 422
        error = resp.json()["error"]
        assert error["code"] == "tenant_not_active"


# ===========================================================================
# Transaction Tests
# ===========================================================================


class TestTransactionIntegrity:
    """Test transaction atomicity."""

    def test_rollback_on_duplicate_name(self, client, workspace_admin_token):
        """Verify entire transaction rolls back on duplicate name error."""
        body1 = _min_body(workspace_slug=_slug("txn1"))
        resp1 = client.post("/api/v1/workspaces", json=body1, headers=_auth(workspace_admin_token))
        assert resp1.status_code == 201
        workspace_id1 = resp1.json()["data"]["workspace_id"]

        # Count audit logs for first workspace
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM control.workspace_audit_logs WHERE workspace_id = %s",
                (uuid.UUID(workspace_id1),),
            )
            count_before = cur.fetchone()[0]

        # Try to create with duplicate name (should fail)
        body2 = _min_body(workspace_slug=_slug("txn2"), workspace_name=body1["workspace_name"])
        resp2 = client.post("/api/v1/workspaces", json=body2, headers=_auth(workspace_admin_token))
        assert resp2.status_code == 422

        # Verify no workspace created
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM control.workspaces WHERE workspace_slug = %s",
                (body2["workspace_slug"],),
            )
            workspace_count = cur.fetchone()[0]

        # Verify no audit log written for failed workspace
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM control.workspace_audit_logs WHERE workspace_id = %s",
                (uuid.UUID(workspace_id1),),
            )
            count_after = cur.fetchone()[0]

        conn.close()

        assert workspace_count == 0
        assert count_after == count_before  # No new audit logs
