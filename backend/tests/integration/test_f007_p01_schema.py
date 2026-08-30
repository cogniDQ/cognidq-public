"""
Integration tests — F007 Packet 1: DB Migration — workspace_role_assignments

Verifies that migration 012_f007_workspace_role_assignments.sql has been
applied correctly. Checks table structure, constraints, indexes, and
the check constraint on role_name.

Run after applying the migration:
    pytest backend/tests/integration/test_f007_p01_schema.py -v

Environment variable:
    DATABASE_URL  (e.g. postgresql://postgres:postgres@localhost:5432/dataquality_db)
    Defaults to the local Docker Compose default if not set.
"""

import os
import uuid
from datetime import UTC, datetime, timezone

import psycopg2
import psycopg2.errors
import psycopg2.extras
import pytest

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

SCHEMA = "control"
TABLE = "workspace_role_assignments"
FULL_TABLE = f"{SCHEMA}.{TABLE}"

FIXED_ROLES = [
    "workspace_administrator",
    "data_engineer",
    "data_steward",
    "business_analyst",
    "governance_viewer",
]

NOW = datetime.now(UTC)


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
    """Per-test cursor with savepoint rollback — no committed side-effects."""
    mgmt = conn.cursor()
    mgmt.execute("SAVEPOINT sp_f007_p01")
    mgmt.close()
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    cleanup = conn.cursor()
    cleanup.execute("ROLLBACK TO SAVEPOINT sp_f007_p01")
    cleanup.execute("RELEASE SAVEPOINT sp_f007_p01")
    cleanup.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _columns(cur):
    cur.execute(
        """
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (SCHEMA, TABLE),
    )
    return {row[0]: {"nullable": row[1], "default": row[2]} for row in cur.fetchall()}


def _indexes(cur):
    cur.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = %s",
        (SCHEMA, TABLE),
    )
    return {row[0] for row in cur.fetchall()}


def _constraints(cur):
    cur.execute(
        """
        SELECT conname, contype
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = %s AND t.relname = %s
        """,
        (SCHEMA, TABLE),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def _new_tenant(cur):
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, region, plan,
            created_by, updated_by, version,
            created_at, updated_at
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


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Table Existence
# ─────────────────────────────────────────────────────────────────────────────


class TestTableExists:
    def test_table_exists_in_control_schema(self, cur):
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            (SCHEMA, TABLE),
        )
        assert cur.fetchone()[0] == 1, f"{FULL_TABLE} does not exist"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Column Definitions
# ─────────────────────────────────────────────────────────────────────────────


class TestColumns:
    def test_id_column_not_nullable(self, cur):
        cols = _columns(cur)
        assert "id" in cols
        assert cols["id"]["nullable"] == "NO"

    def test_workspace_id_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["workspace_id"]["nullable"] == "NO"

    def test_user_id_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["user_id"]["nullable"] == "NO"

    def test_role_name_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["role_name"]["nullable"] == "NO"

    def test_granted_by_is_nullable(self, cur):
        cols = _columns(cur)
        assert cols["granted_by"]["nullable"] == "YES"

    def test_granted_at_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["granted_at"]["nullable"] == "NO"

    def test_granted_at_has_default(self, cur):
        cols = _columns(cur)
        assert cols["granted_at"]["default"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexes:
    def test_primary_key_index_exists(self, cur):
        idxs = _indexes(cur)
        assert any("pk" in i or "pkey" in i for i in idxs), f"No PK index found in {idxs}"

    def test_workspace_index_exists(self, cur):
        idxs = _indexes(cur)
        assert "idx_wra_workspace" in idxs, f"idx_wra_workspace not found in {idxs}"

    def test_user_index_exists(self, cur):
        idxs = _indexes(cur)
        assert "idx_wra_user" in idxs, f"idx_wra_user not found in {idxs}"

    def test_unique_index_on_workspace_user(self, cur):
        """The UNIQUE constraint creates an implicit index."""
        idxs = _indexes(cur)
        assert any("uq" in i or "unique" in i or "user_workspace" in i for i in idxs), (
            f"No unique index on (workspace_id, user_id) found in {idxs}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests — CHECK Constraint (valid roles accepted, invalid rejected)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckConstraint:
    @pytest.mark.parametrize("role_name", FIXED_ROLES)
    def test_valid_role_inserted_successfully(self, cur, role_name):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        # Should not raise
        _insert_role(cur, ws_id, uid, role_name)

    def test_invalid_role_rejected(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_role(cur, ws_id, uid, "super_admin")

    def test_empty_string_role_rejected(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_role(cur, ws_id, uid, "")


# ─────────────────────────────────────────────────────────────────────────────
# Tests — UNIQUE Constraint
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueConstraint:
    def test_duplicate_user_workspace_rejected(self, cur):
        """A user can only hold one role per workspace."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        _insert_role(cur, ws_id, uid, "data_engineer")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert_role(cur, ws_id, uid, "business_analyst")

    def test_same_user_different_workspaces_allowed(self, cur):
        """Same user can have roles in different workspaces."""
        tid = _new_tenant(cur)
        ws1 = _new_workspace(cur, tid)
        ws2 = _new_workspace(cur, tid)
        uid = _new_user(cur)
        _insert_role(cur, ws1, uid, "data_engineer")
        _insert_role(cur, ws2, uid, "business_analyst")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Tests — CASCADE Behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestCascades:
    def test_workspace_deletion_cascades_to_role_assignments(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        ra_id = _insert_role(cur, ws_id, uid, "workspace_administrator")

        # Delete the workspace
        cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (ws_id,))

        # Role assignment must be gone
        cur.execute(
            "SELECT COUNT(*) FROM control.workspace_role_assignments WHERE id = %s",
            (ra_id,),
        )
        assert cur.fetchone()[0] == 0, "Role assignment was not cascaded when workspace deleted"

    def test_user_deletion_cascades_to_role_assignments(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        ra_id = _insert_role(cur, ws_id, uid, "data_steward")

        # Delete the user
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))

        # Role assignment must be gone
        cur.execute(
            "SELECT COUNT(*) FROM control.workspace_role_assignments WHERE id = %s",
            (ra_id,),
        )
        assert cur.fetchone()[0] == 0, "Role assignment was not cascaded when user deleted"

    def test_granted_by_deletion_sets_null(self, cur):
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        granter_id = _new_user(cur)
        ra_id = _insert_role(cur, ws_id, uid, "data_engineer", granted_by=granter_id)

        # Delete the granting user
        cur.execute("DELETE FROM users WHERE id = %s", (granter_id,))

        # granted_by should be NULL, not cascaded
        cur.execute(
            "SELECT granted_by FROM control.workspace_role_assignments WHERE id = %s",
            (ra_id,),
        )
        row = cur.fetchone()
        assert row is not None, "Role assignment was unexpectedly deleted"
        assert row[0] is None, "granted_by was not set to NULL on granter deletion"


# ─────────────────────────────────────────────────────────────────────────────
# Tests — Idempotency (re-running migration)
# ─────────────────────────────────────────────────────────────────────────────


class TestIdempotency:
    def test_table_create_if_not_exists_is_idempotent(self, cur):
        """Re-running the CREATE TABLE IF NOT EXISTS must not error."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS control.workspace_role_assignments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid()
            )
            """
        )
        # If we get here, no error was raised — test passes


# ─────────────────────────────────────────────────────────────────────────────
# Tests — granted_by nullable (null for auto-assignments)
# ─────────────────────────────────────────────────────────────────────────────


class TestGrantedByNullable:
    def test_granted_by_null_allowed(self, cur):
        """granted_by is None for workspace-creation auto-assignments."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        uid = _new_user(cur)
        ra_id = _insert_role(cur, ws_id, uid, "workspace_administrator", granted_by=None)
        cur.execute(
            "SELECT granted_by FROM control.workspace_role_assignments WHERE id = %s",
            (ra_id,),
        )
        assert cur.fetchone()[0] is None
