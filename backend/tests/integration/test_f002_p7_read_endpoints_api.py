"""
Packet 7 — API contract + integration tests:
  GET /api/v1/workspaces              (list with filtering, sorting, pagination)
  GET /api/v1/workspaces/{workspace_id} (detail with aggregate counts)
===========================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database.  JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test uses workspaces with slugs prefixed ``p7test-`` so that the
module-level cleanup fixture can delete those rows without affecting other data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f002_p7_read_endpoints_api.py -v

Environment variable required:
    DATABASE_URL  (set automatically in the Docker service environment)
"""

from __future__ import annotations

import os
import time
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
                %s, 'P7 Test Tenant', 'p7test-tenant',
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
def other_tenant_id() -> uuid.UUID:
    """Create a second test tenant for cross-tenant isolation tests."""
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
                %s, 'P7 Other Tenant', 'p7test-other-tenant',
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
def platform_admin_token(test_tenant_id: uuid.UUID) -> str:
    """Valid platform_admin JWT for the test tenant."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
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
                WHERE workspace_slug LIKE 'p7test-%'
            )
            """
        )
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p7test-%'")
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p7test-%'")
    conn.close()


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
    status_reason = kwargs.get(
        "status_reason", "Archived for testing" if status == "archived" else None
    )

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


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# TestListHappyPath
# ===========================================================================


class TestListHappyPath:
    """GET /api/v1/workspaces — basic happy-path scenarios."""

    def test_default_list_returns_only_active(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC01: Default list excludes archived workspaces; meta.total correct."""
        create_test_workspace(test_tenant_id, "p7test-list-active-01")
        create_test_workspace(test_tenant_id, "p7test-list-archived-01", status="archived")

        resp = client.get("/api/v1/workspaces", headers=auth_headers(workspace_admin_token))

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-list-active-01" in slugs
        assert "p7test-list-archived-01" not in slugs

        # meta.total must reflect only active count for this tenant's visible data
        assert body["meta"]["total"] >= 1

    def test_include_archived_returns_both(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC02: include_archived=true returns both active and archived workspaces."""
        create_test_workspace(test_tenant_id, "p7test-list-active-02")
        create_test_workspace(test_tenant_id, "p7test-list-archived-02", status="archived")

        resp = client.get(
            "/api/v1/workspaces?include_archived=true",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-list-active-02" in slugs
        assert "p7test-list-archived-02" in slugs

    def test_list_response_shape(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC03: List response items have correct shape per TDD §4.6.
        workspace_name_lower must never appear in list response items."""
        create_test_workspace(test_tenant_id, "p7test-list-shape-01")

        resp = client.get("/api/v1/workspaces", headers=auth_headers(workspace_admin_token))

        assert resp.status_code == 200
        body = resp.json()
        item = next(ws for ws in body["data"] if ws["workspace_slug"] == "p7test-list-shape-01")

        # Required fields
        assert "workspace_id" in item
        assert "workspace_name" in item
        assert "workspace_slug" in item
        assert "status" in item
        assert "default_timezone" in item
        assert "created_at" in item
        assert "updated_at" in item

        # Internal field must never appear
        assert "workspace_name_lower" not in item
        assert "version" not in item

    def test_pagination_meta(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC04: Pagination meta (total, page, page_size, has_next) is correct."""
        for i in range(3):
            create_test_workspace(test_tenant_id, f"p7test-page-{i:02d}")

        resp = client.get(
            "/api/v1/workspaces?page=1&page_size=2&include_archived=true",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        meta = body["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 2
        assert len(body["data"]) <= 2
        # When there are more than 2 workspaces, has_next should be True
        if meta["total"] > 2:
            assert meta["has_next"] is True


# ===========================================================================
# TestListSearch
# ===========================================================================


class TestListSearch:
    """GET /api/v1/workspaces — q search scenarios."""

    def test_q_search_on_name(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC05: q search matches workspace_name (case-insensitive ILIKE)."""
        create_test_workspace(
            test_tenant_id,
            "p7test-search-name-01",
            workspace_name="Unique Searchable Alpha Seven",
        )
        create_test_workspace(test_tenant_id, "p7test-search-name-02")

        resp = client.get(
            "/api/v1/workspaces?q=Searchable+Alpha",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-search-name-01" in slugs
        assert "p7test-search-name-02" not in slugs

    def test_q_search_on_slug(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC06: q search also matches workspace_slug."""
        create_test_workspace(test_tenant_id, "p7test-unique-slug-xyz")
        create_test_workspace(test_tenant_id, "p7test-normal-slug-abc")

        resp = client.get(
            "/api/v1/workspaces?q=unique-slug-xyz",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-unique-slug-xyz" in slugs
        assert "p7test-normal-slug-abc" not in slugs

    def test_q_whitespace_treated_as_absent(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC07: q containing only whitespace is treated as absent (EC-2).
        Full unfiltered list is returned."""
        create_test_workspace(test_tenant_id, "p7test-ws-no-filter-01")

        # Request with q containing only spaces
        resp = client.get(
            "/api/v1/workspaces?q=++++",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        # Should return workspaces including the one we just created
        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-ws-no-filter-01" in slugs


# ===========================================================================
# TestListValidation
# ===========================================================================


class TestListValidation:
    """GET /api/v1/workspaces — query parameter validation."""

    def test_invalid_sort_by(self, client: TestClient, workspace_admin_token: str):
        """TC08: sort_by with unrecognized value → 422 invalid_sort_field."""
        resp = client.get(
            "/api/v1/workspaces?sort_by=invalid_column",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_sort_field"

    def test_invalid_sort_dir(self, client: TestClient, workspace_admin_token: str):
        """TC09: sort_dir with unrecognized value → 422 invalid_sort_direction."""
        resp = client.get(
            "/api/v1/workspaces?sort_dir=sideways",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_sort_direction"

    def test_page_below_minimum(self, client: TestClient, workspace_admin_token: str):
        """TC10: page=0 → 422 validation_error."""
        resp = client.get(
            "/api/v1/workspaces?page=0",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_page_size_boundaries(self, client: TestClient, workspace_admin_token: str):
        """TC11: page_size=0 → 422; page_size=101 → 422;
        page_size=1 → 200; page_size=100 → 200 (MV-8 boundary values)."""
        # Below minimum → 422
        resp = client.get(
            "/api/v1/workspaces?page_size=0",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

        # Above maximum → 422
        resp = client.get(
            "/api/v1/workspaces?page_size=101",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

        # Minimum boundary → 200
        resp = client.get(
            "/api/v1/workspaces?page_size=1",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 200

        # Maximum boundary → 200
        resp = client.get(
            "/api/v1/workspaces?page_size=100",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 200

    def test_tenant_id_param_by_non_platform_operator(
        self, client: TestClient, workspace_admin_token: str
    ):
        """TC12: workspace_administrator supplying tenant_id → 422 forbidden_parameter."""
        resp = client.get(
            f"/api/v1/workspaces?tenant_id={uuid.uuid4()}",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "forbidden_parameter"

    def test_unauthenticated_request(self, client: TestClient):
        """TC13: List without a token → 401."""
        resp = client.get("/api/v1/workspaces")
        assert resp.status_code == 401


# ===========================================================================
# TestDetailHappyPath
# ===========================================================================


class TestDetailHappyPath:
    """GET /api/v1/workspaces/{workspace_id} — happy-path scenarios."""

    def test_active_workspace_detail_fields(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC14: Active workspace returns all required fields per TDD §4.7."""
        ws_id = create_test_workspace(test_tenant_id, "p7test-detail-active-01")

        resp = client.get(
            f"/api/v1/workspaces/{ws_id}",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]

        # All core fields
        assert data["workspace_id"] == str(ws_id)
        assert data["tenant_id"] == str(test_tenant_id)
        assert "workspace_name" in data
        assert "workspace_slug" in data
        assert "description" in data
        assert "default_timezone" in data
        assert data["status"] == "active"
        assert "status_reason" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "created_by" in data
        assert "updated_by" in data

        # Enriched fields
        assert "audit_log_link" in data
        assert "dataset_count" in data
        assert "member_count" in data
        # warnings is null when all counts succeed
        assert data["warnings"] is None

        # Internal field must never appear
        assert "workspace_name_lower" not in data
        assert "version" not in data

    def test_archived_workspace_accessible_by_member(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC15: Archived workspace is accessible by a member (same tenant)."""
        ws_id = create_test_workspace(
            test_tenant_id, "p7test-detail-archived-01", status="archived"
        )

        resp = client.get(
            f"/api/v1/workspaces/{ws_id}",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "archived"
        assert data["status_reason"] is not None

    def test_audit_log_link_format(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC16: audit_log_link is a relative path with the correct workspace UUID."""
        ws_id = create_test_workspace(test_tenant_id, "p7test-detail-link-01")

        resp = client.get(
            f"/api/v1/workspaces/{ws_id}",
            headers=auth_headers(workspace_admin_token),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        expected_link = f"/api/v1/workspaces/{ws_id}/audit-logs"
        assert data["audit_log_link"] == expected_link
        # Must be a relative path, not an absolute URL with domain
        assert not data["audit_log_link"].startswith("http")


# ===========================================================================
# TestDetailValidation
# ===========================================================================


class TestDetailValidation:
    """GET /api/v1/workspaces/{workspace_id} — error cases."""

    def test_not_found_returns_404(self, client: TestClient, workspace_admin_token: str):
        """TC17: Non-existent workspace_id returns 404."""
        resp = client.get(
            f"/api/v1/workspaces/{uuid.uuid4()}",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 404

    def test_cross_tenant_returns_404(
        self,
        client: TestClient,
        workspace_admin_token: str,
        other_tenant_id: uuid.UUID,
    ):
        """TC18: Workspace belonging to another tenant returns 404 (not 403)
        — prevents information disclosure (TDD §5.4 cross-tenant isolation)."""
        # Create workspace in the other_tenant_id
        other_ws_id = create_test_workspace(other_tenant_id, "p7test-other-tenant-ws")

        # Request using workspace_admin_token which is scoped to test_tenant_id
        resp = client.get(
            f"/api/v1/workspaces/{other_ws_id}",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp.status_code == 404


# ===========================================================================
# TestDetailCountFallback
# ===========================================================================


class TestDetailCountFallback:
    """GET /api/v1/workspaces/{workspace_id} — registry failure fallback (TDD §11.3)."""

    def test_both_registries_fail_returns_200_with_warnings(
        self, client: TestClient, test_tenant_id: uuid.UUID
    ):
        """TC19: When both dataset and member registries raise, the detail endpoint
        still returns HTTP 200 with dataset_count=null, member_count=null,
        and a warnings array containing two entries (EC-10)."""
        from app.api.v1.endpoints.workspaces import get_workspace_service
        from app.main import app
        from app.services.workspaces.rbac import RBACServiceStub
        from app.services.workspaces.registry import DatasetRegistryStub, MemberRegistryStub
        from app.services.workspaces.repository import (
            AuditLogWriter,
            TenantRepository,
            WorkspaceRepository,
        )
        from app.services.workspaces.service import WorkspaceService

        ws_id = create_test_workspace(test_tenant_id, "p7test-count-fallback-01")

        failing_service = WorkspaceService(
            workspace_repo=WorkspaceRepository(),
            tenant_repo=TenantRepository(),
            audit_writer=AuditLogWriter(),
            rbac_service=RBACServiceStub(),
            dataset_registry=DatasetRegistryStub(raise_error=True),
            member_registry=MemberRegistryStub(raise_error=True),
        )

        s = _get_settings()
        token = jwt.encode(
            {
                "actor_id": str(uuid.uuid4()),
                "actor_role": "workspace_administrator",
                "tenant_id": str(test_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )

        app.dependency_overrides[get_workspace_service] = lambda: failing_service
        try:
            resp = client.get(
                f"/api/v1/workspaces/{ws_id}",
                headers=auth_headers(token),
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dataset_count"] is None
        assert data["member_count"] is None
        assert isinstance(data["warnings"], list)
        assert len(data["warnings"]) == 2
        warning_fields = {w["field"] for w in data["warnings"]}
        assert "dataset_count" in warning_fields
        assert "member_count" in warning_fields


# ===========================================================================
# TestPlatformOperator
# ===========================================================================


class TestPlatformOperator:
    """Platform Admin / Platform Viewer read access (TDD §5.4 / HA-8)."""

    def test_platform_admin_uses_tenant_id_param(
        self,
        client: TestClient,
        platform_admin_token: str,
        other_tenant_id: uuid.UUID,
    ):
        """TC20: Platform Admin can list workspaces in a specific tenant via
        the tenant_id query param."""
        # Create workspace in other_tenant_id
        create_test_workspace(other_tenant_id, "p7test-platform-list-01")

        # platform_admin_token is scoped to test_tenant_id in its JWT but
        # uses tenant_id param to query other_tenant_id
        resp = client.get(
            f"/api/v1/workspaces?tenant_id={other_tenant_id}",
            headers=auth_headers(platform_admin_token),
        )

        assert resp.status_code == 200
        body = resp.json()
        slugs = [ws["workspace_slug"] for ws in body["data"]]
        assert "p7test-platform-list-01" in slugs


# ===========================================================================
# TestFullLifecycle
# ===========================================================================


class TestFullLifecycle:
    """End-to-end read after mutations."""

    def test_list_reflects_archive_status(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC21: After archiving, workspace disappears from default list
        but appears with include_archived=true."""
        # Create two workspaces: one active, one archived
        create_test_workspace(test_tenant_id, "p7test-lifecycle-active")
        create_test_workspace(test_tenant_id, "p7test-lifecycle-archived", status="archived")

        # Default list: only active
        resp_default = client.get(
            "/api/v1/workspaces",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp_default.status_code == 200
        default_slugs = [ws["workspace_slug"] for ws in resp_default.json()["data"]]
        assert "p7test-lifecycle-active" in default_slugs
        assert "p7test-lifecycle-archived" not in default_slugs

        # With include_archived: both present
        resp_all = client.get(
            "/api/v1/workspaces?include_archived=true",
            headers=auth_headers(workspace_admin_token),
        )
        assert resp_all.status_code == 200
        all_slugs = [ws["workspace_slug"] for ws in resp_all.json()["data"]]
        assert "p7test-lifecycle-active" in all_slugs
        assert "p7test-lifecycle-archived" in all_slugs

    def test_sla_smoke_test(
        self, client: TestClient, workspace_admin_token: str, test_tenant_id: uuid.UUID
    ):
        """TC22: List and detail requests complete within 2 000 ms under
        single-connection load (TG-5 SLA smoke test)."""
        ws_id = create_test_workspace(test_tenant_id, "p7test-sla-smoke-01")

        # List SLA
        start = time.time()
        resp = client.get(
            "/api/v1/workspaces",
            headers=auth_headers(workspace_admin_token),
        )
        elapsed_list = time.time() - start
        assert resp.status_code == 200
        assert elapsed_list < 2.0, f"List endpoint took {elapsed_list:.3f}s — exceeds 2 000 ms SLA"

        # Detail SLA
        start = time.time()
        resp = client.get(
            f"/api/v1/workspaces/{ws_id}",
            headers=auth_headers(workspace_admin_token),
        )
        elapsed_detail = time.time() - start
        assert resp.status_code == 200
        assert elapsed_detail < 2.0, (
            f"Detail endpoint took {elapsed_detail:.3f}s — exceeds 2 000 ms SLA"
        )
