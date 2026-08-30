"""
Packet 5 — API contract + integration tests: PATCH /api/v1/workspaces/{workspace_id}
====================================================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database. JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test uses workspaces created with slug prefixed ``p5test-`` so that the
module-level cleanup fixture can delete those rows without touching other data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f002_p5_update_workspace_api.py -v

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
                %s, 'P5 Test Tenant', 'p5test-tenant',
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
                WHERE workspace_slug LIKE 'p5test-%'
            )
            """
        )
        # Delete test workspaces
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p5test-%'")

    conn.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def create_test_workspace(tenant_id: uuid.UUID, slug: str, **kwargs) -> uuid.UUID:
    """
    Create a test workspace directly in the database.

    Returns workspace_id.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    workspace_id = uuid.uuid4()
    created_by = uuid.uuid4()

    # Default values
    name = kwargs.get("workspace_name", f"Test Workspace {slug}")
    description = kwargs.get("description", "Test description")
    default_timezone = kwargs.get("default_timezone", "UTC")
    status = kwargs.get("status", "active")
    status_reason = kwargs.get("status_reason", "Test archived" if status == "archived" else None)

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


def get_workspace_from_db(workspace_id: uuid.UUID) -> dict:
    """Fetch workspace row from database."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM control.workspaces WHERE workspace_id = %s", (workspace_id,))
        result = cur.fetchone()

    conn.close()
    return dict(result) if result else None


def get_audit_logs_for_workspace(workspace_id: uuid.UUID) -> list[dict]:
    """Fetch all audit logs for a workspace."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM control.workspace_audit_logs
            WHERE workspace_id = %s
            ORDER BY occurred_at DESC
            """,
            (workspace_id,),
        )
        results = cur.fetchall()

    conn.close()
    return [dict(r) for r in results]


# ---------------------------------------------------------------------------
# Test Class: Happy Path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Tests for successful update operations."""

    def test_update_workspace_name(self, client, test_tenant_id, workspace_admin_token):
        """
        TC01: Update workspace_name only.
        Expected: HTTP 200, workspace_name updated, version incremented, audit log created.
        """
        # Arrange
        workspace_id = create_test_workspace(test_tenant_id, "p5test-name-001")
        original = get_workspace_from_db(workspace_id)

        payload = {"workspace_name": "Updated Name"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["workspace_name"] == "Updated Name"
        assert data["workspace_id"] == str(workspace_id)
        assert data["description"] == original["description"]
        assert data["default_timezone"] == original["default_timezone"]

        # Check database
        updated = get_workspace_from_db(workspace_id)
        assert updated["workspace_name"] == "Updated Name"
        assert updated["workspace_name_lower"] == "updated name"
        assert updated["version"] == original["version"] + 1
        assert updated["updated_at"] > original["updated_at"]

        # Check audit log
        audit_logs = get_audit_logs_for_workspace(workspace_id)
        assert len(audit_logs) > 0
        last_audit = audit_logs[0]
        assert last_audit["action_type"] == "workspace_updated"
        assert last_audit["new_data"] == {"workspace_name": "Updated Name"}
        assert last_audit["previous_data"] == {"workspace_name": original["workspace_name"]}

    def test_update_description(self, client, test_tenant_id, workspace_admin_token):
        """
        TC02: Update description only.
        Expected: HTTP 200, description updated, version incremented.
        """
        # Arrange
        workspace_id = create_test_workspace(test_tenant_id, "p5test-desc-002")
        original = get_workspace_from_db(workspace_id)

        payload = {"description": "New detailed description"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] == "New detailed description"
        assert data["workspace_name"] == original["workspace_name"]

        # Check database
        updated = get_workspace_from_db(workspace_id)
        assert updated["description"] == "New detailed description"
        assert updated["version"] == original["version"] + 1

    def test_update_all_fields(self, client, test_tenant_id, workspace_admin_token):
        """
        TC03: Update workspace_name, description, and default_timezone together.
        Expected: HTTP 200, all fields updated, version incremented, audit log contains all changes.
        """
        # Arrange
        workspace_id = create_test_workspace(test_tenant_id, "p5test-all-003")
        original = get_workspace_from_db(workspace_id)

        payload = {
            "workspace_name": "All Fields Updated",
            "description": "Updated description",
            "default_timezone": "America/New_York",
        }
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["workspace_name"] == "All Fields Updated"
        assert data["description"] == "Updated description"
        assert data["default_timezone"] == "America/New_York"

        # Check database
        updated = get_workspace_from_db(workspace_id)
        assert updated["workspace_name"] == "All Fields Updated"
        assert updated["description"] == "Updated description"
        assert updated["default_timezone"] == "America/New_York"
        assert updated["version"] == original["version"] + 1

        # Check audit log contains all 3 fields
        audit_logs = get_audit_logs_for_workspace(workspace_id)
        last_audit = audit_logs[0]
        assert len(last_audit["new_data"]) == 3
        assert "workspace_name" in last_audit["new_data"]
        assert "description" in last_audit["new_data"]
        assert "default_timezone" in last_audit["new_data"]


# ---------------------------------------------------------------------------
# Test Class: No-Op Detection
# ---------------------------------------------------------------------------


class TestNoOp:
    """Tests for no-op detection (TDD §5.2 Step 6)."""

    def test_empty_payload(self, client, test_tenant_id, workspace_admin_token):
        """
        TC04: Submit empty payload {}.
        Expected: HTTP 200 with {"data": null}, no version increment, no audit log.
        """
        # Arrange
        workspace_id = create_test_workspace(test_tenant_id, "p5test-noop-004")
        original = get_workspace_from_db(workspace_id)
        original_audit_count = len(get_audit_logs_for_workspace(workspace_id))

        payload = {}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data is None

        # Check database - no changes
        updated = get_workspace_from_db(workspace_id)
        assert updated["version"] == original["version"]
        assert updated["updated_at"] == original["updated_at"]

        # Check audit log - no new entries
        new_audit_count = len(get_audit_logs_for_workspace(workspace_id))
        assert new_audit_count == original_audit_count

    def test_all_values_identical(self, client, test_tenant_id, workspace_admin_token):
        """
        TC05: Submit payload with all values identical to current state.
        Expected: HTTP 200 with {"data": null}, no version increment, no audit log.
        """
        # Arrange
        workspace_id = create_test_workspace(
            test_tenant_id,
            "p5test-noop-005",
            workspace_name="Identical Test",
            description="Same description",
            default_timezone="Europe/London",
        )
        original = get_workspace_from_db(workspace_id)
        original_audit_count = len(get_audit_logs_for_workspace(workspace_id))

        # Submit identical values
        payload = {
            "workspace_name": "Identical Test",
            "description": "Same description",
            "default_timezone": "Europe/London",
        }
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data is None

        # Check database - no changes
        updated = get_workspace_from_db(workspace_id)
        assert updated["version"] == original["version"]
        assert updated["updated_at"] == original["updated_at"]

        # Check audit log - no new entries
        new_audit_count = len(get_audit_logs_for_workspace(workspace_id))
        assert new_audit_count == original_audit_count


# ---------------------------------------------------------------------------
# Test Class: Workspace Status Checks
# ---------------------------------------------------------------------------


class TestWorkspaceStatus:
    """Tests for workspace status validation."""

    def test_archived_workspace_rejected(self, client, test_tenant_id, workspace_admin_token):
        """
        TC06: Attempt to update archived workspace.
        Expected: HTTP 422 workspace_archived.
        """
        # Arrange
        workspace_id = create_test_workspace(
            test_tenant_id, "p5test-archived-006", status="archived"
        )

        payload = {"workspace_name": "New Name"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "workspace_archived"
        assert "archived" in error["message"].lower()


# ---------------------------------------------------------------------------
# Test Class: Tenant Status Checks
# ---------------------------------------------------------------------------


class TestTenantStatus:
    """Tests for tenant status validation."""

    def test_inactive_tenant_rejected(self, client, workspace_admin_token):
        """
        TC07: Attempt to update workspace when tenant is suspended.
        Expected: HTTP 422 tenant_not_active.
        """
        # Arrange - Create tenant with suspended status
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        suspended_tenant_id = uuid.uuid4()

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, status_reason, region, plan, created_at, updated_at, created_by, updated_by, version
                ) VALUES (
                    %s, 'Suspended Tenant', 'p5test-suspended',
                    'suspended', 'Test suspension', 'us-east', 'enterprise',
                    NOW(), NOW(), %s, %s, 0
                ) ON CONFLICT (tenant_slug) DO UPDATE
                SET status = 'suspended', status_reason = 'Test suspension'
                """,
                (suspended_tenant_id, uuid.uuid4(), uuid.uuid4()),
            )
        conn.close()

        # Create workspace in suspended tenant
        workspace_id = create_test_workspace(suspended_tenant_id, "p5test-suspended-007")

        # Create JWT for suspended tenant
        s = _get_settings()
        suspended_token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(suspended_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        payload = {"workspace_name": "New Name"}
        headers = {"Authorization": f"Bearer {suspended_token}"}

        # Act
        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        # Assert
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "tenant_not_active"


# ---------------------------------------------------------------------------
# Test Class: Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for field validation rules."""

    def test_workspace_name_empty_rejected(self, client, test_tenant_id, workspace_admin_token):
        """
        TC08: Submit empty workspace_name.
        Expected: HTTP 422 with field_required error.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-empty-name-008")

        payload = {"workspace_name": ""}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "workspace_name" for f in error.get("fields", []))

    def test_workspace_name_too_long(self, client, test_tenant_id, workspace_admin_token):
        """
        TC09: Submit workspace_name exceeding 200 characters.
        Expected: HTTP 422 with max_length error.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-long-name-009")

        payload = {"workspace_name": "A" * 201}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "workspace_name" for f in error.get("fields", []))

    def test_description_too_long(self, client, test_tenant_id, workspace_admin_token):
        """
        TC10: Submit description exceeding 2000 characters.
        Expected: HTTP 422 with max_length error.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-long-desc-010")

        payload = {"description": "B" * 2001}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "description" for f in error.get("fields", []))

    def test_invalid_timezone(self, client, test_tenant_id, workspace_admin_token):
        """
        TC11: Submit invalid IANA timezone.
        Expected: HTTP 422 with invalid_timezone error.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-bad-tz-011")

        payload = {"default_timezone": "Invalid/Timezone"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert any(f["field"] == "default_timezone" for f in error.get("fields", []))


# ---------------------------------------------------------------------------
# Test Class: Immutable and Forbidden Fields
# ---------------------------------------------------------------------------


class TestImmutableForbidden:
    """Tests for immutable and forbidden field rejection."""

    def test_workspace_slug_immutable(self, client, test_tenant_id, workspace_admin_token):
        """
        TC12: Attempt to update workspace_slug.
        Expected: HTTP 422 immutable_field.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-immutable-012")

        payload = {"workspace_slug": "new-slug"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "immutable_field"
        assert any(f["field"] == "workspace_slug" for f in error.get("fields", []))

    def test_forbidden_fields_rejected(self, client, test_tenant_id, workspace_admin_token):
        """
        TC13: Attempt to submit workspace_id or tenant_id fields.
        Expected: HTTP 400 forbidden_field.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-forbidden-013")

        payload = {
            "workspace_name": "Valid Name",
            "workspace_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
        }
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid_fields"
        fields = error.get("fields", [])
        assert any(
            f["field"] == "workspace_id" and f["error_code"] == "forbidden_field" for f in fields
        )
        assert any(
            f["field"] == "tenant_id" and f["error_code"] == "forbidden_field" for f in fields
        )


# ---------------------------------------------------------------------------
# Test Class: Business Rules
# ---------------------------------------------------------------------------


class TestBusinessRules:
    """Tests for business logic validation."""

    def test_duplicate_name_rejected(self, client, test_tenant_id, workspace_admin_token):
        """
        TC14: Attempt to rename workspace to an existing name in same tenant.
        Expected: HTTP 422 duplicate_name.
        """
        # Arrange - Create two workspaces
        create_test_workspace(
            test_tenant_id, "p5test-dup-014a", workspace_name="Existing Workspace"
        )
        workspace_id_b = create_test_workspace(
            test_tenant_id, "p5test-dup-014b", workspace_name="Another Workspace"
        )

        # Try to rename workspace B to match workspace A
        payload = {"workspace_name": "Existing Workspace"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(
            f"/api/v1/workspaces/{workspace_id_b}", json=payload, headers=headers
        )

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "duplicate_name"

    def test_workspace_not_found(self, client, test_tenant_id, workspace_admin_token):
        """
        TC15: Attempt to update non-existent workspace.
        Expected: HTTP 404 workspace_not_found.
        """
        non_existent_id = uuid.uuid4()

        payload = {"workspace_name": "New Name"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(
            f"/api/v1/workspaces/{non_existent_id}", json=payload, headers=headers
        )

        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "workspace_not_found"


# ---------------------------------------------------------------------------
# Test Class: Concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Tests for optimistic locking via version column."""

    def test_version_increment(self, client, test_tenant_id, workspace_admin_token):
        """
        TC16: Verify version increments on successful update.
        Expected: version = original + 1.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-version-016")
        original = get_workspace_from_db(workspace_id)

        payload = {"workspace_name": "Version Test"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 200

        updated = get_workspace_from_db(workspace_id)
        assert updated["version"] == original["version"] + 1


# ---------------------------------------------------------------------------
# Test Class: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_description_null_accepted(self, client, test_tenant_id, workspace_admin_token):
        """
        TC17: Set description to null.
        Expected: HTTP 200, description cleared.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-null-017")

        payload = {"description": None}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] is None

        updated = get_workspace_from_db(workspace_id)
        assert updated["description"] is None

    def test_workspace_name_normalization(self, client, test_tenant_id, workspace_admin_token):
        """
        TC18: Submit workspace_name with extra whitespace.
        Expected: HTTP 200, whitespace normalized, workspace_name_lower updated.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-norm-018")

        payload = {"workspace_name": "  Spaced   Name  "}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 200
        data = response.json()["data"]
        # Assuming normalization collapses whitespace
        assert "Spaced" in data["workspace_name"]
        assert "Name" in data["workspace_name"]

        updated = get_workspace_from_db(workspace_id)
        assert updated["workspace_name_lower"] == updated["workspace_name"].lower()

    def test_unknown_field_rejected(self, client, test_tenant_id, workspace_admin_token):
        """
        TC19: Submit unknown field in payload.
        Expected: HTTP 400 unknown_field.
        """
        workspace_id = create_test_workspace(test_tenant_id, "p5test-unknown-019")

        payload = {"workspace_name": "Valid Name", "unknown_field": "invalid"}
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        response = client.patch(f"/api/v1/workspaces/{workspace_id}", json=payload, headers=headers)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid_fields"
        assert any(
            f["field"] == "unknown_field" and f["error_code"] == "unknown_field"
            for f in error.get("fields", [])
        )
