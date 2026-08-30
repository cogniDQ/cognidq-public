"""
F008 P02 — Integration tests: GET /workspaces/{workspace_id}/audit/permissions
===============================================================================

Tests the permission audit list endpoint via FastAPI TestClient + real
PostgreSQL database.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/f008/test_f008_list_endpoint.py -v

Tests cover ACs:
  AC-P02-001  200 with valid JWT + view_audit_logs permission
  AC-P02-002  403 without view_audit_logs permission
  AC-P02-003  Forbidden fields (source_ip, previous_data, new_data) absent from response
  AC-P02-004  actor_id filter returns only matching entries
  AC-P02-005  action_type filter returns only entries with that type
  AC-P02-006  Out-of-set action_type returns 400 INVALID_PARAM
  AC-P02-007  Non-UUID actor_id returns 400
  AC-P02-008  to_date < from_date returns 400
  AC-P02-012  actor_display_name resolved from users table
  AC-P02-013  Tenant/workspace isolation — cross-workspace entries never returned
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient

psycopg2.extras.register_uuid()

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import settings

    return settings


def _make_token(actor_id: uuid.UUID, role: str, tenant_id: uuid.UUID) -> str:
    from jose import jwt

    s = _get_settings()
    payload = {
        "actor_id": str(actor_id),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _new_tenant(cur) -> uuid.UUID:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, region, plan,
            created_by, updated_by, version, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', 'eu-west', 'starter',
            %s, %s, 0, NOW(), NOW()
        )
        """,
        (tid, f"T-{tid}", f"t-{str(tid)[:8]}", actor, actor),
    )
    return tid


def _new_workspace(cur, tenant_id: uuid.UUID) -> uuid.UUID:
    ws_id = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS-{ws_id}"
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name, workspace_name_lower,
            workspace_slug, status, default_timezone,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %s, %s, %s, %s, %s, 'active', 'UTC',
            NOW(), NOW(), %s, %s, 0
        )
        """,
        (ws_id, tenant_id, name, name.lower(), f"ws-{str(ws_id)[:8]}", actor, actor),
    )
    return ws_id


def _new_user(cur, full_name: str | None = None, email: str | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    email = email or f"user-{uid}@test.example"
    cur.execute(
        "INSERT INTO users (id, email, full_name, status) VALUES (%s, %s, %s, 'active')",
        (uid, email, full_name),
    )
    return uid


def _insert_role(cur, workspace_id, user_id, role_name, granted_by=None):
    ra_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.workspace_role_assignments
            (id, workspace_id, user_id, role_name, granted_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (ra_id, workspace_id, user_id, role_name, granted_by),
    )


def _insert_audit_log(
    cur,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    action_type: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str = "workspace_administrator",
    actor_type: str = "user",
    target_entity_type: str | None = None,
    target_entity_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> uuid.UUID:
    log_id = uuid.uuid4()
    ts = occurred_at or datetime.now(tz=UTC)
    cur.execute(
        """
        INSERT INTO control.workspace_audit_logs (
            log_id, tenant_id, workspace_id,
            action_type, actor_id, actor_role, actor_type,
            target_entity_type, target_entity_id,
            new_data, occurred_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s)
        """,
        (
            log_id,
            tenant_id,
            workspace_id,
            action_type,
            actor_id,
            actor_role,
            actor_type,
            target_entity_type,
            target_entity_id,
            ts,
        ),
    )
    return log_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture()
def cur(db_conn):
    """Autocommit cursor — inserts are committed immediately so the HTTP
    handler's separate DB connection can see the test data."""
    cursor = db_conn.cursor()
    yield cursor
    cursor.close()


# ---------------------------------------------------------------------------
# AC-P02-001 / AC-P02-003: 200 + forbidden fields absent
# ---------------------------------------------------------------------------


class TestListPermissionAudit200:
    def test_returns_200_with_valid_permission(self, client, cur):
        """workspace_administrator (who has view_audit_logs) gets 200."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "has_next" in data
        assert isinstance(data["items"], list)

    def test_forbidden_fields_absent_from_response(self, client, cur):
        """source_ip, previous_data, and new_data must never appear in items."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["items"]) >= 1
        for item in data["items"]:
            assert "source_ip" not in item
            assert "previous_data" not in item
            assert "new_data" not in item

    def test_total_reflects_count_of_matching_entries(self, client, cur):
        """total field equals the actual number of matching records."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        for _ in range(3):
            _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 3

    def test_has_next_true_when_more_pages_exist(self, client, cur):
        """has_next=True when total > page * page_size."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        for _ in range(3):
            _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions?page=1&page_size=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["has_next"] is True

    def test_empty_result_returns_200_with_zero_total(self, client, cur):
        """Empty workspace yields 200 with items=[] total=0 has_next=False."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["has_next"] is False


# ---------------------------------------------------------------------------
# AC-P02-002: 403 without view_audit_logs
# ---------------------------------------------------------------------------


class TestListPermissionAudit403:
    def test_returns_403_for_data_engineer(self, client, cur):
        """data_engineer lacks view_audit_logs → 403."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "data_engineer")

        token = _make_token(actor_id, "data_engineer", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

    def test_returns_401_without_token(self, client):
        """No JWT → 401."""
        ws_id = uuid.uuid4()
        resp = client.get(f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions")
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# AC-P02-004: actor_id filter
# ---------------------------------------------------------------------------


class TestListActorIdFilter:
    def test_actor_id_filter_returns_only_matching_entries(self, client, cur):
        """Filter by actor_id returns only entries for that actor."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin = _new_user(cur)
        user_a = _new_user(cur)
        user_b = _new_user(cur)
        _insert_role(cur, ws_id, admin, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=user_a)
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=user_b)

        token = _make_token(admin, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions?actor_id={user_a}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["actor_id"] == str(user_a)


# ---------------------------------------------------------------------------
# AC-P02-005: action_type filter
# ---------------------------------------------------------------------------


class TestListActionTypeFilter:
    def test_action_type_filter_returns_only_matching_type(self, client, cur):
        """Filter action_type=role_assigned returns only role_assigned entries."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)
        _insert_audit_log(cur, tid, ws_id, "team_created", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions?action_type=role_assigned",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action_type"] == "role_assigned"

    def test_excludes_non_access_control_action_types(self, client, cur):
        """Entries with non-access-control action types are never returned."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        # Insert an audit log with a non-access-control type (e.g., workspace_created)
        _insert_audit_log(cur, tid, ws_id, "workspace_created", actor_id=actor_id)
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Only role_assigned should appear; workspace_created is not in the AC set
        returned_types = {item["action_type"] for item in data["items"]}
        assert "workspace_created" not in returned_types
        assert "role_assigned" in returned_types


# ---------------------------------------------------------------------------
# AC-P02-006 / AC-P02-007 / AC-P02-008: 400 cases
# ---------------------------------------------------------------------------


class TestListValidation400:
    def test_invalid_action_type_returns_400(self, client, cur):
        """Out-of-set action_type returns 400 with INVALID_PARAM code."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions?action_type=rule_executed",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "INVALID_PARAM"

    def test_invalid_uuid_actor_id_returns_400(self, client, cur):
        """Non-UUID actor_id triggers 400."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions?actor_id=not-a-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, resp.text

    def test_to_date_before_from_date_returns_400(self, client, cur):
        """to_date earlier than from_date returns 400."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            (
                f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions"
                "?from_date=2026-01-10T00:00:00Z&to_date=2026-01-05T00:00:00Z"
            ),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# AC-P02-012 / AC-P02-013: display name + isolation
# ---------------------------------------------------------------------------


class TestListDisplayNameAndIsolation:
    def test_actor_display_name_resolved_from_users_table(self, client, cur):
        """actor_display_name reflects full_name from the users table."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin = _new_user(cur)
        actor_id = _new_user(cur, full_name="Jane Doe")
        _insert_role(cur, ws_id, admin, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(admin, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        entry = next(i for i in items if i["actor_id"] == str(actor_id))
        assert entry["actor_display_name"] == "Jane Doe"

    def test_system_actor_display_name_is_null(self, client, cur):
        """actor_type=system with null actor_id → actor_display_name=None."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin = _new_user(cur)
        _insert_role(cur, ws_id, admin, "workspace_administrator")
        _insert_audit_log(
            cur,
            tid,
            ws_id,
            "role_assigned",
            actor_id=None,
            actor_type="system",
        )

        token = _make_token(admin, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        system_entry = next(i for i in items if i["actor_type"] == "system")
        assert system_entry["actor_display_name"] is None

    def test_cross_workspace_isolation(self, client, cur):
        """Entries from workspace B never appear in workspace A response."""
        tid = _new_tenant(cur)
        ws_a = _new_workspace(cur, tid)
        ws_b = _new_workspace(cur, tid)
        admin = _new_user(cur)
        _insert_role(cur, ws_a, admin, "workspace_administrator")
        # Insert entry only in ws_b
        _insert_audit_log(cur, tid, ws_b, "role_assigned")
        # Insert entry in ws_a
        _insert_audit_log(cur, tid, ws_a, "team_created", actor_id=admin)

        token = _make_token(admin, "workspace_administrator", tid)
        resp = client.get(
            f"{API_PREFIX}/workspaces/{ws_a}/audit/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Only ws_a entries should be returned
        assert data["total"] == 1
        assert data["items"][0]["workspace_id"] == str(ws_a)
