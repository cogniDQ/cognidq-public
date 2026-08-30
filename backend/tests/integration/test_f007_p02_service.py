"""
Integration tests — F007 Packet 2: WorkspaceRBACService

Verifies that WorkspaceRBACService correctly reads/writes to
``control.workspace_role_assignments`` against a live database.

Run after applying migration 012:
    pytest backend/tests/integration/test_f007_p02_service.py -v

Environment variable:
    DATABASE_URL  (e.g. postgresql://postgres:postgres@localhost:5432/dataquality_db)
    Defaults to the local Docker Compose default if not set.

All tests use SAVEPOINT rollback so they leave the database clean regardless
of pass/fail.
"""

import os
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import pytest

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def conn():
    connection = psycopg2.connect(DATABASE_URL)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture()
def cur(conn):
    """Per-test cursor with SAVEPOINT rollback."""
    mgmt = conn.cursor()
    mgmt.execute("SAVEPOINT sp_f007_p02")
    mgmt.close()
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    cleanup = conn.cursor()
    cleanup.execute("ROLLBACK TO SAVEPOINT sp_f007_p02")
    cleanup.execute("RELEASE SAVEPOINT sp_f007_p02")
    cleanup.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — seed data
# ─────────────────────────────────────────────────────────────────────────────


def _new_tenant(cur):
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


def _new_workspace(cur, tenant_id):
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


def _new_user(cur):
    uid = uuid.uuid4()
    cur.execute(
        "INSERT INTO users (id, email, status) VALUES (%s, %s, 'active')",
        (uid, f"user-{uid}@test.example"),
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
    return ra_id


def _get_role_row(cur, workspace_id, user_id):
    cur.execute(
        """
        SELECT id, workspace_id, user_id, role_name, granted_by, granted_at
        FROM control.workspace_role_assignments
        WHERE workspace_id = %s AND user_id = %s
        """,
        (workspace_id, user_id),
    )
    return cur.fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# SQLAlchemy Session shim — wraps a psycopg2 cursor
# ─────────────────────────────────────────────────────────────────────────────
#
# WorkspaceRBACService uses sqlalchemy.text() + session.execute(text, params).
# We provide a minimal shim so we don't have to spin up a SQLAlchemy engine
# for these integration tests.
#
# The shim wraps the psycopg2 cursor to look like a Session.
# It converts sqlalchemy.text() objects to plain strings for psycopg2.


class _SessionShim:
    """Minimal SQLAlchemy Session shim over a psycopg2 cursor for integration tests."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._last_result = None

    def execute(self, stmt, params=None):
        # Extract SQL string from sqlalchemy.text() object
        sql = stmt.text if hasattr(stmt, "text") else str(stmt)
        # Convert :name params to %(name)s for psycopg2
        import re

        pg_sql = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", sql)
        self._cursor.execute(pg_sql, params or {})
        self._last_result = _ResultShim(self._cursor)
        return self._last_result

    def flush(self):
        pass  # psycopg2 auto-flushes


class _ResultShim:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# Import service under test
# ─────────────────────────────────────────────────────────────────────────────

from app.services.workspaces.exceptions import (  # noqa: E402
    LastWorkspaceAdministratorError,
    RoleAssignmentNotFoundError,
    RoleGrantFailedError,
)
from app.services.workspaces.rbac import WorkspaceRBACService  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Tests — grant_workspace_admin
# ─────────────────────────────────────────────────────────────────────────────


class TestGrantWorkspaceAdmin:
    """WorkspaceRBACService.grant_workspace_admin writes a real row to the DB."""

    def test_inserts_workspace_administrator_row(self, cur, conn):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        conn.flush() if hasattr(conn, "flush") else None

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        svc.grant_workspace_admin(ws_id, uid, shim)

        row = _get_role_row(cur, ws_id, uid)
        assert row is not None, "Role assignment row was not inserted"
        assert row[3] == "workspace_administrator"

    def test_idempotent_second_call_does_not_raise(self, cur, conn):
        """ON CONFLICT DO NOTHING — calling twice must not raise."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        svc.grant_workspace_admin(ws_id, uid, shim)
        # Second call — should be a no-op
        svc.grant_workspace_admin(ws_id, uid, shim)

        cur.execute(
            "SELECT COUNT(*) FROM control.workspace_role_assignments "
            "WHERE workspace_id = %s AND user_id = %s",
            (ws_id, uid),
        )
        assert cur.fetchone()[0] == 1, "Duplicate row should not have been inserted"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — assign_role
# ─────────────────────────────────────────────────────────────────────────────


class TestAssignRole:
    def test_assigns_new_role(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        result = svc.assign_role(ws_id, uid, "data_engineer", actor, shim)

        assert result is not None
        assert result["role_name"] == "data_engineer"
        row = _get_role_row(cur, ws_id, uid)
        assert row is not None
        assert row[3] == "data_engineer"

    def test_upsert_replaces_existing_role(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)
        # Seed with data_steward
        _insert_role(cur, ws_id, uid, "data_steward")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        result = svc.assign_role(ws_id, uid, "data_engineer", actor, shim)

        assert result["role_name"] == "data_engineer"
        row = _get_role_row(cur, ws_id, uid)
        assert row[3] == "data_engineer"

    def test_idempotent_same_role_no_db_write(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, uid, "data_steward")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        result = svc.assign_role(ws_id, uid, "data_steward", actor, shim)

        assert result["role_name"] == "data_steward"

    def test_last_admin_guard_prevents_role_change(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, admin, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)

        with pytest.raises(LastWorkspaceAdministratorError):
            svc.assign_role(ws_id, admin, "data_engineer", actor, shim)

    def test_last_admin_guard_allows_second_admin(self, cur):
        """If there are 2 admins, downgrade one of them is allowed."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin1 = _new_user(cur)
        admin2 = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, admin1, "workspace_administrator")
        _insert_role(cur, ws_id, admin2, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        # Should not raise — 2 admins present
        result = svc.assign_role(ws_id, admin1, "data_engineer", actor, shim)
        assert result["role_name"] == "data_engineer"

    def test_invalid_role_raises_value_error(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)

        with pytest.raises(ValueError, match="Invalid role_name"):
            svc.assign_role(ws_id, uid, "super_user", actor, shim)


# ─────────────────────────────────────────────────────────────────────────────
# Tests — revoke_role
# ─────────────────────────────────────────────────────────────────────────────


class TestRevokeRole:
    def test_revokes_existing_role(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, uid, "data_steward")
        # Ensure an admin exists so the workspace is not left empty
        admin = _new_user(cur)
        _insert_role(cur, ws_id, admin, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        svc.revoke_role(ws_id, uid, actor, shim)

        row = _get_role_row(cur, ws_id, uid)
        assert row is None, "Role row should have been deleted"

    def test_revoke_not_found_raises(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)

        with pytest.raises(RoleAssignmentNotFoundError):
            svc.revoke_role(ws_id, uid, actor, shim)

    def test_last_admin_guard_prevents_revoke(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, admin, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)

        with pytest.raises(LastWorkspaceAdministratorError):
            svc.revoke_role(ws_id, admin, actor, shim)

    def test_can_revoke_admin_when_two_exist(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        admin1 = _new_user(cur)
        admin2 = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, admin1, "workspace_administrator")
        _insert_role(cur, ws_id, admin2, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        svc.revoke_role(ws_id, admin1, actor, shim)

        row = _get_role_row(cur, ws_id, admin1)
        assert row is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests — get_member_role
# ─────────────────────────────────────────────────────────────────────────────


class TestGetMemberRole:
    def test_returns_none_when_no_assignment(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        result = svc.get_member_role(ws_id, uid, shim)

        assert result is None

    def test_returns_dict_with_role_name(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        actor = _new_user(cur)
        _insert_role(cur, ws_id, uid, "governance_viewer", actor)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        result = svc.get_member_role(ws_id, uid, shim)

        assert result is not None
        assert result["role_name"] == "governance_viewer"
        assert result["user_id"] == uid
        assert result["workspace_id"] == ws_id


# ─────────────────────────────────────────────────────────────────────────────
# Tests — check_permission
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckPermission:
    def test_data_engineer_can_write_datasources(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        _insert_role(cur, ws_id, uid, "data_engineer")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.check_permission(ws_id, uid, "datasources:write", shim) is True

    def test_governance_viewer_cannot_delete_rules(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        _insert_role(cur, ws_id, uid, "governance_viewer")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.check_permission(ws_id, uid, "rules:delete", shim) is False

    def test_no_role_returns_false(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.check_permission(ws_id, uid, "workspaces:read", shim) is False

    def test_workspace_administrator_can_assign_roles(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        _insert_role(cur, ws_id, uid, "workspace_administrator")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.check_permission(ws_id, uid, "roles:assign", shim) is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests — get_admin_count
# ─────────────────────────────────────────────────────────────────────────────


class TestGetAdminCount:
    def test_returns_zero_when_no_admins(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.get_admin_count(ws_id, shim) == 0

    def test_returns_correct_count(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        for _ in range(3):
            uid = _new_user(cur)
            _insert_role(cur, ws_id, uid, "workspace_administrator")
        # Add a non-admin — should not be counted
        other = _new_user(cur)
        _insert_role(cur, ws_id, other, "data_engineer")

        svc = WorkspaceRBACService()
        shim = _SessionShim(cur)
        assert svc.get_admin_count(ws_id, shim) == 3
