"""
Packet 6 — API contract + integration tests:
  POST /api/v1/workspaces/{workspace_id}/archive
  POST /api/v1/workspaces/{workspace_id}/restore
===========================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database.  JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test uses workspaces with slugs prefixed ``p6test-`` so that the
module-level cleanup fixture can delete those rows without affecting other data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f002_p6_archive_restore_api.py -v

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
    """Create a test tenant and return its UUID."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, 'P6 Test Tenant', 'p6test-tenant',
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


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_workspaces():
    """Delete all test-created workspace rows after the module finishes."""
    yield  # tests run first

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM control.workspace_audit_logs
            WHERE workspace_id IN (
                SELECT workspace_id FROM control.workspaces
                WHERE workspace_slug LIKE 'p6test-%'
            )
            """
        )
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p6test-%'")
        # Clean up the suspended test tenant inserted in TestRestoreValidation
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p6test-%'")
    conn.close()


@pytest.fixture(scope="module", autouse=True)
def anchor_workspace(test_tenant_id: uuid.UUID):
    """
    Create one always-active workspace in the shared test tenant.

    This ensures that individual archive tests never accidentally hit the
    last-workspace guard (which would turn a simple archive test into a 409).
    The anchor workspace is never archived by any test.
    """
    create_test_workspace(test_tenant_id, "p6test-anchor-ws")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def create_test_workspace(tenant_id: uuid.UUID, slug: str, **kwargs) -> uuid.UUID:
    """Insert a workspace directly into the DB.  Returns the workspace_id."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    workspace_id = uuid.uuid4()
    created_by = uuid.uuid4()

    name = kwargs.get("workspace_name", f"Test Workspace {slug}")
    description = kwargs.get("description", "Test description")
    default_timezone = kwargs.get("default_timezone", "UTC")
    status = kwargs.get("status", "active")
    # CHECK constraint requires non-null status_reason when archived
    if status == "archived":
        status_reason = kwargs.get("status_reason", "Test archival reason")
    else:
        status_reason = kwargs.get("status_reason", None)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone,
                status, status_reason, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (
                workspace_id,
                tenant_id,
                name,
                name.lower(),
                slug,
                description,
                default_timezone,
                status,
                status_reason,
                created_by,
                created_by,
            ),
        )
    conn.close()
    return workspace_id


def get_workspace_from_db(workspace_id: uuid.UUID) -> dict | None:
    """Fetch a workspace row from the database."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM control.workspaces WHERE workspace_id = %s",
            (workspace_id,),
        )
        result = cur.fetchone()
    conn.close()
    return dict(result) if result else None


def get_audit_logs_for_workspace(workspace_id: uuid.UUID) -> list[dict]:
    """Fetch all audit log rows for a workspace, newest first."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM control.workspace_audit_logs
            WHERE workspace_id = %s
            ORDER BY occurred_at ASC
            """,
            (workspace_id,),
        )
        results = cur.fetchall()
    conn.close()
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------


class TestArchiveHappyPath:
    """Archive endpoint — successful cases."""

    def test_archive_active_workspace(self, client, test_tenant_id, workspace_admin_token):
        """
        TC01: Archive an active workspace with a valid status_reason.
        Expected: HTTP 200, status = archived, version incremented, audit log created.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc01")
        original = get_workspace_from_db(workspace_id)

        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "Decommissioned for testing purposes"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "archived"
        assert data["status_reason"] == "Decommissioned for testing purposes"
        assert data["workspace_id"] == str(workspace_id)

        # Database check
        updated = get_workspace_from_db(workspace_id)
        assert updated["status"] == "archived"
        assert updated["status_reason"] == "Decommissioned for testing purposes"
        assert updated["version"] == original["version"] + 1
        assert updated["updated_at"] > original["updated_at"]

        # Audit log check
        logs = get_audit_logs_for_workspace(workspace_id)
        assert len(logs) == 1
        log = logs[0]
        assert log["action_type"] == "workspace_archived"
        assert log["previous_data"] == {"status": "active", "status_reason": None}
        assert log["new_data"] == {
            "status": "archived",
            "status_reason": "Decommissioned for testing purposes",
        }

    def test_archive_with_status_reason_trimmed(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC02: status_reason is trimmed; leading/trailing whitespace is stripped.
        Expected: HTTP 200, stored reason is trimmed.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc02")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "   Trimmed reason for archival   "}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status_reason"] == "Trimmed reason for archival"

    def test_archive_last_workspace_with_confirm_flag(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC03: Archive last active workspace with confirm_last_workspace: true.
        Expected: HTTP 200, workspace archived successfully.
        """
        # Create a fresh tenant with a single workspace to guarantee last-workspace scenario
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        solo_tenant_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan, created_at, updated_at, created_by, updated_by, version
                ) VALUES (%s, 'P6 Solo Tenant', 'p6test-solo-tenant',
                          'active', 'us-east', 'enterprise',
                          NOW(), NOW(), %s, %s, 0)
                """,
                (solo_tenant_id, uuid.uuid4(), uuid.uuid4()),
            )
        conn.close()

        workspace_id = create_test_workspace(solo_tenant_id, "p6test-arch-solo-tc03")

        # Issue archive JWT scoped to the solo tenant
        s = _get_settings()
        token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(solo_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "status_reason": "Last workspace archival with explicit confirmation",
            "confirm_last_workspace": True,
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "archived"


class TestRestoreHappyPath:
    """Restore endpoint — successful cases."""

    def test_restore_archived_workspace(self, client, test_tenant_id, workspace_admin_token):
        """
        TC04: Restore an archived workspace.
        Expected: HTTP 200, status = active, status_reason = null, version incremented.
        """
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p6test-rest-tc04",
            status="archived",
            status_reason="Archived for restoration test",
        )
        original = get_workspace_from_db(workspace_id)

        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/restore",
            headers=headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "active"
        assert data["status_reason"] is None
        assert data["workspace_id"] == str(workspace_id)

        # Database check
        updated = get_workspace_from_db(workspace_id)
        assert updated["status"] == "active"
        assert updated["status_reason"] is None  # cleared to NULL, never ""
        assert updated["version"] == original["version"] + 1

        # Audit log check
        logs = get_audit_logs_for_workspace(workspace_id)
        assert len(logs) == 1
        log = logs[0]
        assert log["action_type"] == "workspace_restored"
        assert log["previous_data"] == {
            "status": "archived",
            "status_reason": "Archived for restoration test",
        }
        assert log["new_data"] == {"status": "active", "status_reason": None}

    def test_restore_accepts_empty_body(self, client, test_tenant_id, workspace_admin_token):
        """
        TC05: Restore accepts empty body (no body required per TDD §4.5).
        Expected: HTTP 200.
        """
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p6test-rest-tc05",
            status="archived",
            status_reason="Test reason for restore empty body",
        )
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Send request with no JSON body at all
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/restore",
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "active"


class TestArchiveValidation:
    """Archive endpoint — validation rejection cases."""

    def test_already_archived_returns_forbidden_transition(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC06: Archive an already-archived workspace → 422 forbidden_transition.
        Status check happens BEFORE status_reason validation (A-8 ordering rule).
        """
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p6test-arch-tc06",
            status="archived",
            status_reason="Already archived workspace reason",
        )
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "Trying to archive again"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "forbidden_transition"

    def test_already_archived_bad_reason_returns_forbidden_not_validation_error(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC07: Archive an already-archived workspace with MISSING status_reason.
        Per A-8: must return forbidden_transition, NOT a reason validation error.
        """
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p6test-arch-tc07",
            status="archived",
            status_reason="Already archived for ordering test",
        )
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        # Intentionally missing status_reason
        payload = {}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        # Must return forbidden_transition (not missing_reason), per ordering rule
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "forbidden_transition"

    def test_missing_status_reason_returns_422(self, client, test_tenant_id, workspace_admin_token):
        """
        TC08: Archive active workspace without status_reason → 422 missing_reason.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc08")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {}  # no status_reason

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        fields = {f["field"]: f["reason"] for f in error["fields"]}
        assert fields.get("status_reason") == "missing_reason"

    def test_too_short_status_reason_returns_422(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC09: status_reason less than 10 chars after trim → 422 reason_too_short.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc09")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "Short"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422, response.text
        error = response.json()["error"]
        fields = {f["field"]: f["reason"] for f in error["fields"]}
        assert fields.get("status_reason") == "reason_too_short"

    def test_confirm_last_workspace_as_string_returns_400(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC10: confirm_last_workspace: "true" (string) → HTTP 400 invalid_field_type.
        Must be rejected at controller level before service is called.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc10")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {
            "status_reason": "Valid reason for archival here",
            "confirm_last_workspace": "true",  # string, not boolean
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "invalid_field_type"

    def test_unknown_field_in_archive_payload_returns_400(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC11: Unknown field in archive body → HTTP 400 unknown_field.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-arch-tc11")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {
            "status_reason": "Valid archival reason here",
            "extra_field": "unexpected",
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "unknown_field"


class TestArchiveLastWorkspace:
    """Archive endpoint — last-active-workspace guard."""

    def test_last_workspace_without_confirm_flag_returns_409(
        self, client, workspace_admin_token, test_tenant_id
    ):
        """
        TC12: Last active workspace archived without confirm_last_workspace → 409.
        Uses a dedicated tenant so we know there is exactly one active workspace.
        """
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        solo_tenant_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan, created_at, updated_at, created_by, updated_by, version
                ) VALUES (%s, 'P6 Last WS Tenant', 'p6test-last-ws-tenant',
                          'active', 'us-east', 'enterprise',
                          NOW(), NOW(), %s, %s, 0)
                """,
                (solo_tenant_id, uuid.uuid4(), uuid.uuid4()),
            )
        conn.close()

        workspace_id = create_test_workspace(solo_tenant_id, "p6test-arch-last-tc12")

        s = _get_settings()
        token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(solo_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        headers = {"Authorization": f"Bearer {token}"}
        payload = {"status_reason": "Trying to archive last workspace"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "last_active_workspace"

        # Verify no state change occurred
        db_workspace = get_workspace_from_db(workspace_id)
        assert db_workspace["status"] == "active"
        assert len(get_audit_logs_for_workspace(workspace_id)) == 0

    def test_last_workspace_with_explicit_false_returns_409(self, client, workspace_admin_token):
        """
        TC13: confirm_last_workspace: false (explicit boolean) → 409 (same as absent).
        Per A-9: false is treated identically to absent.
        """
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        solo_tenant_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan, created_at, updated_at, created_by, updated_by, version
                ) VALUES (%s, 'P6 False Flag Tenant', 'p6test-false-flag-tenant',
                          'active', 'us-east', 'enterprise',
                          NOW(), NOW(), %s, %s, 0)
                """,
                (solo_tenant_id, uuid.uuid4(), uuid.uuid4()),
            )
        conn.close()

        workspace_id = create_test_workspace(solo_tenant_id, "p6test-arch-false-tc13")

        s = _get_settings()
        token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(solo_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "status_reason": "Trying with explicit false flag",
            "confirm_last_workspace": False,  # explicit False — must still 409
        }

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "last_active_workspace"


class TestRestoreValidation:
    """Restore endpoint — validation rejection cases."""

    def test_restore_active_workspace_returns_forbidden_transition(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC14: Restore an active workspace → 422 forbidden_transition.
        Only archived workspaces can be restored.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p6test-rest-tc14")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/restore",
            headers=headers,
        )

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "forbidden_transition"

        # No audit log written for rejected transition
        assert len(get_audit_logs_for_workspace(workspace_id)) == 0

    def test_restore_when_tenant_suspended_returns_422(self, client, workspace_admin_token):
        """
        TC15: Restore workspace whose Tenant is suspended → 422 tenant_not_active.
        """
        # Create a suspended tenant
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        susp_tenant_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, status_reason, region, plan,
                    created_at, updated_at, created_by, updated_by, version
                ) VALUES (%s, 'P6 Suspended Tenant', 'p6test-susp-tenant',
                          'suspended', 'Non-payment', 'us-east', 'enterprise',
                          NOW(), NOW(), %s, %s, 0)
                """,
                (susp_tenant_id, uuid.uuid4(), uuid.uuid4()),
            )
        conn.close()

        workspace_id = create_test_workspace(
            susp_tenant_id,
            "p6test-rest-tc15",
            status="archived",
            status_reason="Archived before tenant suspension",
        )

        s = _get_settings()
        token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(susp_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/restore",
            headers=headers,
        )

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "tenant_not_active"

        # No audit log written for rejected transition
        assert len(get_audit_logs_for_workspace(workspace_id)) == 0


class TestNotFound:
    """Archive and restore on non-existent / cross-tenant workspace → 404."""

    def test_archive_nonexistent_workspace_returns_404(self, client, workspace_admin_token):
        """TC16: Archive a workspace_id that does not exist → HTTP 404."""
        nonexistent_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "Archiving nonexistent workspace attempt"}

        response = client.post(
            f"/api/v1/workspaces/{nonexistent_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 404, response.text

    def test_restore_nonexistent_workspace_returns_404(self, client, workspace_admin_token):
        """TC17: Restore a workspace_id that does not exist → HTTP 404."""
        nonexistent_id = uuid.uuid4()
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.post(
            f"/api/v1/workspaces/{nonexistent_id}/restore",
            headers=headers,
        )

        assert response.status_code == 404, response.text


class TestFullLifecycle:
    """End-to-end lifecycle and audit trail tests."""

    def test_full_lifecycle_create_archive_restore_archive(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC18: Full lifecycle: create → archive → restore → archive (EC-8, TG-10).
        Verifies: 2 audit entries (archive + restore + archive = 3 after the
        implicit create), status_reason cleared after restore, new reason on
        second archive.
        """
        # Create workspace via DB helper (stands in for the Create endpoint)
        workspace_id = create_test_workspace(test_tenant_id, "p6test-lifecycle-tc18")
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # --- Archive #1 ---
        r1 = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json={"status_reason": "First archival — initial reason"},
            headers=headers,
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["data"]["status"] == "archived"

        # --- Restore ---
        r2 = client.post(
            f"/api/v1/workspaces/{workspace_id}/restore",
            headers=headers,
        )
        assert r2.status_code == 200, r2.text
        data2 = r2.json()["data"]
        assert data2["status"] == "active"
        assert data2["status_reason"] is None  # cleared after restore

        # --- Archive #2 ---
        r3 = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json={"status_reason": "Second archival — different reason"},
            headers=headers,
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["data"]["status"] == "archived"
        assert r3.json()["data"]["status_reason"] == "Second archival — different reason"

        # Audit log: 3 entries in chronological order
        logs = get_audit_logs_for_workspace(workspace_id)
        assert len(logs) == 3
        action_types = [l["action_type"] for l in logs]
        assert action_types == ["workspace_archived", "workspace_restored", "workspace_archived"]

        # First archived entry: previous_data.status_reason was None (never set before)
        assert logs[0]["previous_data"] == {"status": "active", "status_reason": None}
        assert logs[0]["new_data"]["status_reason"] == "First archival — initial reason"

        # Restored entry: previous_data reflects the first reason
        assert logs[1]["previous_data"]["status_reason"] == "First archival — initial reason"
        assert logs[1]["new_data"] == {"status": "active", "status_reason": None}

        # Second archive: previous_data.status_reason is now None (restored state)
        assert logs[2]["previous_data"] == {"status": "active", "status_reason": None}
        assert logs[2]["new_data"]["status_reason"] == "Second archival — different reason"

        # Version should be 3 (incremented each time)
        final = get_workspace_from_db(workspace_id)
        assert final["version"] == 3

    def test_no_audit_entry_on_rejected_archive(
        self, client, test_tenant_id, workspace_admin_token
    ):
        """
        TC19: Reject archive (already archived) → no new audit log entry (TG-12).
        """
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p6test-noaudit-tc19",
            status="archived",
            status_reason="Pre-archived for no-audit test",
        )
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}
        payload = {"status_reason": "Attempting to archive again"}

        logs_before = get_audit_logs_for_workspace(workspace_id)
        assert len(logs_before) == 0  # no prior audit entries from DB insert

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json=payload,
            headers=headers,
        )

        assert response.status_code == 422
        assert len(get_audit_logs_for_workspace(workspace_id)) == 0  # unchanged
