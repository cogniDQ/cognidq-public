"""
Packet 8 — API contract + integration tests:
  GET /api/v1/workspaces/{workspace_id}/audit-logs
  (List Workspace Audit Logs with filtering, pagination, auth)
==============================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database.  JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test uses workspaces with slugs prefixed ``p8test-`` so that the
module-level cleanup fixture can delete those rows without affecting other data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f002_p8_audit_log_api.py -v

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
    """Create a test tenant for P8 and return its UUID."""
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
                %s, 'P8 Test Tenant', 'p8test-tenant',
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
                %s, 'P8 Other Tenant', 'p8test-other-tenant',
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
def wa_actor_id() -> uuid.UUID:
    """Fixed actor UUID shared across WA tests (for actor_id filter tests)."""
    return uuid.uuid4()


@pytest.fixture(scope="module")
def workspace_admin_token(test_tenant_id: uuid.UUID, wa_actor_id: uuid.UUID) -> str:
    """Valid workspace_administrator JWT for the test tenant."""
    s = _get_settings()
    payload = {
        "actor_id": str(wa_actor_id),
        "actor_role": "workspace_administrator",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def platform_admin_token(test_tenant_id: uuid.UUID) -> str:
    """Valid platform_admin JWT."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def platform_viewer_token(test_tenant_id: uuid.UUID) -> str:
    """Valid platform_viewer JWT."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_viewer",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def data_engineer_token(test_tenant_id: uuid.UUID) -> str:
    """data_engineer role JWT — should be denied (403) on audit log endpoint."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "data_engineer",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_workspaces():
    """Delete all p8test- workspace rows and tenants after the module finishes."""
    yield  # all tests run first

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM control.workspace_audit_logs
            WHERE workspace_id IN (
                SELECT workspace_id FROM control.workspaces
                WHERE workspace_slug LIKE 'p8test-%'
            )
            """
        )
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p8test-%'")
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p8test-%'")
    conn.close()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _db_conn():
    return psycopg2.connect(DATABASE_URL)


def create_workspace_direct(
    tenant_id: uuid.UUID,
    slug: str,
    actor_id: uuid.UUID,
    status: str = "active",
    status_reason: str = None,
) -> uuid.UUID:
    """Insert a workspace row directly and return workspace_id."""
    conn = _db_conn()
    conn.autocommit = True
    workspace_id = uuid.uuid4()
    name = f"P8 Test {slug}"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone,
                status, status_reason, created_at, updated_at,
                created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s, 'P8 test workspace', 'UTC',
                %s::control.workspace_status_enum, %s,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (
                workspace_id,
                tenant_id,
                name,
                name.lower(),
                slug,
                status,
                status_reason,
                actor_id,
                actor_id,
            ),
        )
    conn.close()
    return workspace_id


def insert_audit_log(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    action_type: str,
    actor_id: uuid.UUID,
    actor_role: str = "workspace_administrator",
    previous_data=None,
    new_data: dict = None,
    occurred_at: datetime = None,
    request_id: uuid.UUID = None,
    source_ip: str = None,
) -> uuid.UUID:
    """Insert an audit log entry directly into the DB."""
    import json

    conn = _db_conn()
    conn.autocommit = True
    log_id = uuid.uuid4()
    if occurred_at is None:
        occurred_at = datetime.now(UTC)
    if new_data is None:
        new_data = {"action": action_type}

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspace_audit_logs (
                log_id, tenant_id, workspace_id, action_type,
                actor_id, actor_role, previous_data, new_data,
                occurred_at, request_id, source_ip
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb,
                %s,
                %s, %s
            )
            """,
            (
                log_id,
                tenant_id,
                workspace_id,
                action_type,
                actor_id,
                actor_role,
                json.dumps(previous_data) if previous_data is not None else None,
                json.dumps(new_data),
                occurred_at,
                request_id,
                source_ip,
            ),
        )
    conn.close()
    return log_id


def _audit_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/audit-logs"


# ===========================================================================
# TestAuditLogHappyPath
# ===========================================================================


class TestAuditLogHappyPath:
    """TC01–TC04: Happy-path listing and filtering."""

    def test_full_lifecycle_three_entries_reverse_order(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """
        TC01: After create → archive → restore, 3 audit entries exist in
        reverse occurred_at order.  Correct action_types on each entry.
        """
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-lifecycle-01", wa_actor_id)
        now = datetime.now(UTC)

        # Insert 3 audit entries with distinct timestamps
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            occurred_at=now - timedelta(seconds=30),
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            wa_actor_id,
            previous_data={"status": "active"},
            new_data={"status": "archived", "status_reason": "Decommissioned"},
            occurred_at=now - timedelta(seconds=20),
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_restored",
            wa_actor_id,
            previous_data={"status": "archived"},
            new_data={"status": "active"},
            occurred_at=now - timedelta(seconds=10),
        )

        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert len(data) == 3
        assert body["meta"]["total"] == 3

        # Reverse occurred_at order: restored first, archived second, created last
        action_types = [e["action_type"] for e in data]
        assert action_types == [
            "workspace_restored",
            "workspace_archived",
            "workspace_created",
        ], f"Expected reverse order, got: {action_types}"

    def test_filter_by_action_type_archived(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC02: Filter by action_type=workspace_archived returns only archived entries."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-filter-action-02", wa_actor_id
        )
        now = datetime.now(UTC)
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            occurred_at=now - timedelta(seconds=20),
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            wa_actor_id,
            new_data={"status": "archived"},
            occurred_at=now - timedelta(seconds=10),
        )

        resp = client.get(
            _audit_url(workspace_id),
            params={"action_type": "workspace_archived"},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["action_type"] == "workspace_archived"

    def test_filter_by_actor_id(self, client, test_tenant_id, workspace_admin_token, wa_actor_id):
        """TC03: Filter by actor_id returns only entries from that actor."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-filter-actor-03", wa_actor_id
        )
        other_actor = uuid.uuid4()
        now = datetime.now(UTC)
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            occurred_at=now - timedelta(seconds=20),
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            other_actor,
            new_data={"status": "archived"},
            occurred_at=now - timedelta(seconds=10),
        )

        resp = client.get(
            _audit_url(workspace_id),
            params={"actor_id": str(wa_actor_id)},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert all(e["actor_id"] == str(wa_actor_id) for e in data)
        assert len(data) == 1

    def test_from_date_to_date_range_filter(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC04: from_date / to_date filter — entries outside range excluded."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-daterange-04", wa_actor_id)
        now = datetime.now(UTC)
        inside_dt = now - timedelta(seconds=50)
        outside_dt = now - timedelta(seconds=200)

        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            occurred_at=outside_dt,  # outside range
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            wa_actor_id,
            new_data={"status": "archived"},
            occurred_at=inside_dt,  # inside range
        )

        from_str = (now - timedelta(seconds=100)).isoformat()
        to_str = now.isoformat()

        resp = client.get(
            _audit_url(workspace_id),
            params={"from_date": from_str, "to_date": to_str},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["action_type"] == "workspace_archived"

    def test_from_date_only_half_open_range(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """
        TC05 (EC-9): from_date without to_date is a valid half-open range.
        Only entries at or after from_date are returned; no upper bound applied.
        """
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-halfopen-05", wa_actor_id)
        now = datetime.now(UTC)
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            occurred_at=now - timedelta(seconds=200),  # below from_date
        )
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            wa_actor_id,
            new_data={"status": "archived"},
            occurred_at=now - timedelta(seconds=50),  # above from_date
        )

        from_str = (now - timedelta(seconds=100)).isoformat()

        resp = client.get(
            _audit_url(workspace_id),
            params={"from_date": from_str},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["action_type"] == "workspace_archived"

    def test_response_shape_all_fields_present(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC06: Each audit log entry exposes all expected fields."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-shape-06", wa_actor_id)
        test_request_id = uuid.uuid4()
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
            request_id=test_request_id,
            source_ip="192.168.1.1",
        )

        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        entry = resp.json()["data"][0]

        required_keys = {
            "log_id",
            "workspace_id",
            "tenant_id",
            "action_type",
            "actor_id",
            "actor_role",
            "previous_data",
            "new_data",
            "occurred_at",
            "request_id",
            "source_ip",
        }
        assert required_keys.issubset(set(entry.keys())), (
            f"Missing keys: {required_keys - set(entry.keys())}"
        )
        assert entry["request_id"] == str(test_request_id)
        assert entry["source_ip"] == "192.168.1.1"

    def test_source_ip_from_x_forwarded_for(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """
        TC07 (TG-11): source_ip captured from X-Forwarded-For header on creation
        is correctly stored and returned in the audit log response.

        We use the HTTP API (POST /workspaces) to create a workspace so that
        the source_ip is extracted from the request header.
        """
        s = _get_settings()
        payload = {
            "actor_id": str(wa_actor_id),
            "actor_role": "workspace_administrator",
            "tenant_id": str(test_tenant_id),
            "exp": datetime.now(tz=UTC) + timedelta(hours=1),
        }
        token = jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)

        resp = client.post(
            "/api/v1/workspaces",
            json={
                "workspace_name": "P8 ForwardedFor Test",
                "workspace_slug": "p8test-fwd-07",
                "default_timezone": "UTC",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "203.0.113.1, 10.0.0.1",
            },
        )
        assert resp.status_code == 201, resp.text
        workspace_id = resp.json()["data"]["workspace_id"]

        audit_resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert audit_resp.status_code == 200
        entries = audit_resp.json()["data"]
        assert len(entries) >= 1
        # First IP from X-Forwarded-For should be stored
        assert entries[0]["source_ip"] == "203.0.113.1", (
            f"Expected source_ip='203.0.113.1', got: {entries[0]['source_ip']}"
        )

    def test_pagination_meta_correct(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC08: Pagination meta (total, page, page_size, has_next) is correct."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-pagination-08", wa_actor_id)
        # Insert 3 entries
        for i in range(3):
            insert_audit_log(
                test_tenant_id,
                workspace_id,
                "workspace_created",
                wa_actor_id,
                new_data={"idx": i},
                occurred_at=datetime.now(UTC) - timedelta(seconds=i * 10),
            )

        # Request page 1 with page_size=2
        resp = client.get(
            _audit_url(workspace_id),
            params={"page": 1, "page_size": 2},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["total"] == 3
        assert meta["page"] == 1
        assert meta["page_size"] == 2
        assert meta["has_next"] is True

        # Request page 2
        resp2 = client.get(
            _audit_url(workspace_id),
            params={"page": 2, "page_size": 2},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp2.status_code == 200
        meta2 = resp2.json()["meta"]
        assert meta2["has_next"] is False
        assert len(resp2.json()["data"]) == 1


# ===========================================================================
# TestAuditLogValidation
# ===========================================================================


class TestAuditLogValidation:
    """TC09–TC14: Query parameter validation."""

    def test_invalid_action_type_returns_422(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC09: Unrecognized action_type → 422 invalid_filter_value (not empty list)."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-val-actiontype-09", wa_actor_id
        )
        resp = client.get(
            _audit_url(workspace_id),
            params={"action_type": "workspace_unknown"},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "invalid_filter_value"

    def test_from_date_gt_to_date_returns_422(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC10 (EC-9): from_date > to_date → 422 invalid_date_range."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-val-daterange-10", wa_actor_id
        )
        now = datetime.now(UTC)
        resp = client.get(
            _audit_url(workspace_id),
            params={
                "from_date": now.isoformat(),
                "to_date": (now - timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "invalid_date_range"

    def test_invalid_actor_id_returns_400(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC11: actor_id=not-a-uuid → 400 invalid_parameter."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-val-actorid-11", wa_actor_id)
        resp = client.get(
            _audit_url(workspace_id),
            params={"actor_id": "not-a-uuid"},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 400
        err = resp.json()["error"]
        assert err["code"] == "invalid_parameter"

    def test_page_below_minimum_returns_422(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC12: page=0 → 422 validation_error."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-val-page-12", wa_actor_id)
        resp = client.get(
            _audit_url(workspace_id),
            params={"page": 0},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "validation_error"

    def test_page_size_boundaries(self, client, test_tenant_id, workspace_admin_token, wa_actor_id):
        """TC13: page_size=0 and page_size=101 → 422; page_size=1 and 100 → 200."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-val-pagesize-13", wa_actor_id
        )
        headers = {"Authorization": f"Bearer {workspace_admin_token}"}

        assert (
            client.get(
                _audit_url(workspace_id), params={"page_size": 0}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.get(
                _audit_url(workspace_id), params={"page_size": 101}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.get(
                _audit_url(workspace_id), params={"page_size": 1}, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.get(
                _audit_url(workspace_id), params={"page_size": 100}, headers=headers
            ).status_code
            == 200
        )

    def test_invalid_date_format_returns_422(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC14: Non-ISO from_date → 422 invalid_parameter."""
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-val-dateformat-14", wa_actor_id
        )
        resp = client.get(
            _audit_url(workspace_id),
            params={"from_date": "not-a-date"},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 422


# ===========================================================================
# TestAuditLogAuth
# ===========================================================================


class TestAuditLogAuth:
    """TC15–TC18: Authorization rules per TDD §5.4."""

    def test_workspace_admin_gets_200(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC15: WA role → 200."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-auth-wa-15", wa_actor_id)
        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 200

    def test_data_engineer_gets_403(self, client, test_tenant_id, data_engineer_token, wa_actor_id):
        """TC16: data_engineer role → 403."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-auth-de-16", wa_actor_id)
        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {data_engineer_token}"},
        )
        assert resp.status_code == 403

    def test_platform_viewer_gets_200(
        self, client, test_tenant_id, platform_viewer_token, wa_actor_id
    ):
        """TC17: platform_viewer → 200 (Platform Operators can view all)."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-auth-pv-17", wa_actor_id)
        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {platform_viewer_token}"},
        )
        assert resp.status_code == 200

    def test_unauthenticated_gets_401(self, client, test_tenant_id, wa_actor_id):
        """TC18: No token → 401."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-auth-unauth-18", wa_actor_id)
        resp = client.get(_audit_url(workspace_id))
        assert resp.status_code == 401


# ===========================================================================
# TestAuditLogNotFound
# ===========================================================================


class TestAuditLogNotFound:
    """TC19–TC20: 404 cases."""

    def test_nonexistent_workspace_returns_404(self, client, workspace_admin_token):
        """TC19: workspace_id that does not exist → 404."""
        nonexistent_id = uuid.uuid4()
        resp = client.get(
            _audit_url(nonexistent_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 404

    def test_cross_tenant_returns_404(
        self, client, other_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """
        TC20: WA actor in test_tenant requests a workspace belonging to
        other_tenant → 404 (cross-tenant isolation by find_by_id tenant filter).
        """
        other_actor = uuid.uuid4()
        workspace_id = create_workspace_direct(other_tenant_id, "p8test-crosst-20", other_actor)
        # workspace_admin_token is scoped to test_tenant (not other_tenant)
        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 404


# ===========================================================================
# TestAuditLogPlatformOperator
# ===========================================================================


class TestAuditLogPlatformOperator:
    """TC21–TC22: Platform Operator cross-tenant access."""

    def test_platform_admin_accesses_other_tenant_workspace(
        self, client, other_tenant_id, platform_admin_token, wa_actor_id
    ):
        """
        TC21: platform_admin can access audit logs for a workspace in any Tenant.
        No cross-tenant 404 for Platform Operators.
        """
        other_actor = uuid.uuid4()
        workspace_id = create_workspace_direct(other_tenant_id, "p8test-plat-21", other_actor)
        insert_audit_log(
            other_tenant_id,
            workspace_id,
            "workspace_created",
            other_actor,
            new_data={"status": "active"},
        )

        resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {platform_admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    def test_platform_viewer_readonly_cannot_archive(
        self, client, test_tenant_id, platform_viewer_token, wa_actor_id
    ):
        """
        TC22 (MP-5): Platform Viewer cannot call archive endpoint (P6 mutation route).
        Archive requires workspace_administrator → 403 for platform_viewer.
        """
        workspace_id = create_workspace_direct(
            test_tenant_id, "p8test-plat-archive-22", wa_actor_id
        )
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json={"status_reason": "Test archival of exactly ten chars"},
            headers={"Authorization": f"Bearer {platform_viewer_token}"},
        )
        assert resp.status_code == 403


# ===========================================================================
# TestAuditLogSpecial
# ===========================================================================


class TestAuditLogSpecial:
    """TC23–TC25: Special protocol and lifecycle tests."""

    def test_post_to_audit_logs_returns_405(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """TC23 (MP-4): POST to /{workspace_id}/audit-logs → 405 Method Not Allowed."""
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-method-23", wa_actor_id)
        resp = client.post(
            _audit_url(workspace_id),
            json={},
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert resp.status_code == 405

    def test_revoked_wa_returns_403(self, client, test_tenant_id, wa_actor_id):
        """
        TC24 (MP-3 live RBAC): After 'revocation' (next JWT issued has non-WA role),
        further audit log requests with the non-WA token → 403.

        We simulate revocation by using a second token with a non-permitted role.
        The first request (WA token) succeeds; the second (DE token) fails.
        """
        workspace_id = create_workspace_direct(test_tenant_id, "p8test-revoke-24", wa_actor_id)
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_created",
            wa_actor_id,
            new_data={"status": "active"},
        )

        s = _get_settings()
        # Token 1: WA role — should succeed
        wa_token = jwt.encode(
            {
                "actor_id": str(wa_actor_id),
                "actor_role": "workspace_administrator",
                "tenant_id": str(test_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )
        resp1 = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {wa_token}"},
        )
        assert resp1.status_code == 200

        # Token 2: role revoked to data_engineer — should fail (MP-3)
        revoked_token = jwt.encode(
            {
                "actor_id": str(wa_actor_id),
                "actor_role": "data_engineer",
                "tenant_id": str(test_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )
        resp2 = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {revoked_token}"},
        )
        assert resp2.status_code == 403, (
            f"Expected 403 after WA role revoked. Got: {resp2.status_code}"
        )

    def test_no_audit_entry_for_rejected_transition(
        self, client, test_tenant_id, workspace_admin_token, wa_actor_id
    ):
        """
        TC25 (TG-12): Attempt to archive an already-archived workspace.
        The rejected transition should NOT create a new audit entry.
        """
        workspace_id = create_workspace_direct(
            test_tenant_id,
            "p8test-tg12-25",
            wa_actor_id,
            status="archived",
            status_reason="Already archived workspace for TG-12 test",
        )
        # Pre-condition: insert only the initial 'archived' audit entry
        insert_audit_log(
            test_tenant_id,
            workspace_id,
            "workspace_archived",
            wa_actor_id,
            previous_data={"status": "active"},
            new_data={
                "status": "archived",
                "status_reason": "Already archived workspace for TG-12 test",
            },
        )

        # Attempt to archive again — should fail with 422 forbidden_transition
        s = _get_settings()
        wa_token = jwt.encode(
            {
                "actor_id": str(wa_actor_id),
                "actor_role": "workspace_administrator",
                "tenant_id": str(test_tenant_id),
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )
        archive_resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/archive",
            json={"status_reason": "Attempt double archive test run"},
            headers={"Authorization": f"Bearer {wa_token}"},
        )
        assert archive_resp.status_code == 422

        # Verify audit log count unchanged
        audit_resp = client.get(
            _audit_url(workspace_id),
            headers={"Authorization": f"Bearer {workspace_admin_token}"},
        )
        assert audit_resp.status_code == 200
        # Only the 1 archived entry we inserted directly; no new entry
        assert audit_resp.json()["meta"]["total"] == 1, (
            f"Expected 1 audit entry after rejected transition, got "
            f"{audit_resp.json()['meta']['total']}"
        )
