"""
Integration tests — F002 Packet 1: Database Schema and Migration

These tests verify that migration 007_f002_workspace_schema.sql has been
applied correctly. They connect directly to the PostgreSQL database using
psycopg2 and validate every structural and constraint guarantee required by
the packet plan acceptance criteria (TDD §3.1.1, §3.1.2, §3.3, §11.2).

Run after applying the migration:
    pytest backend/tests/integration/test_f002_p1_schema.py -v

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
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

NOW = datetime.now(UTC)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def conn():
    connection = psycopg2.connect(DATABASE_URL)
    connection.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture()
def cur(conn):
    """Per-test cursor with savepoint rollback — no committed side-effects."""
    mgmt = conn.cursor()
    mgmt.execute("SAVEPOINT sp_test")
    mgmt.close()
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    cleanup = conn.cursor()
    cleanup.execute("ROLLBACK TO SAVEPOINT sp_test")
    cleanup.execute("RELEASE SAVEPOINT sp_test")
    cleanup.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _columns(cur, schema, table):
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return {
        row[0]: {"data_type": row[1], "nullable": row[2], "default": row[3]}
        for row in cur.fetchall()
    }


def _indexes(cur, schema, table):
    cur.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s AND tablename = %s
        """,
        (schema, table),
    )
    return {row[0] for row in cur.fetchall()}


def _new_tenant(cur):
    """Insert a minimal valid tenant and return its tenant_id."""
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
        (tid, f"Tenant {tid}", f"tenant-{str(tid)[:8]}", actor, actor),
    )
    return tid


def _workspace_row(tenant_id, **overrides):
    """Build a minimal valid workspace row dict."""
    actor = uuid.uuid4()
    name = f"My Workspace {uuid.uuid4()}"
    base = dict(
        workspace_id=uuid.uuid4(),
        tenant_id=tenant_id,
        workspace_name=name,
        workspace_name_lower=name.lower(),
        workspace_slug=f"ws-{str(uuid.uuid4())[:8]}",
        description=None,
        default_timezone="UTC",
        status="active",
        status_reason=None,
        created_at=NOW,
        updated_at=NOW,
        created_by=actor,
        updated_by=actor,
        version=0,
    )
    base.update(overrides)
    return base


def _insert_workspace(cur, row):
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name, workspace_name_lower,
            workspace_slug, description, default_timezone, status, status_reason,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %(workspace_id)s, %(tenant_id)s, %(workspace_name)s, %(workspace_name_lower)s,
            %(workspace_slug)s, %(description)s, %(default_timezone)s, %(status)s,
            %(status_reason)s, %(created_at)s, %(updated_at)s, %(created_by)s,
            %(updated_by)s, %(version)s
        )
        """,
        row,
    )


def _audit_row(tenant_id, workspace_id, **overrides):
    """Build a minimal valid audit log row dict."""
    base = dict(
        log_id=uuid.uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        action_type="workspace_created",
        actor_id=uuid.uuid4(),
        actor_role="workspace_administrator",
        previous_data=None,
        new_data='{"workspace_id": "test"}',
        occurred_at=NOW,
        request_id=None,
        source_ip=None,
    )
    base.update(overrides)
    return base


def _insert_audit(cur, row):
    cur.execute(
        """
        INSERT INTO control.workspace_audit_logs (
            log_id, tenant_id, workspace_id, action_type, actor_id, actor_role,
            previous_data, new_data, occurred_at, request_id, source_ip
        ) VALUES (
            %(log_id)s, %(tenant_id)s, %(workspace_id)s, %(action_type)s,
            %(actor_id)s, %(actor_role)s, %(previous_data)s, %(new_data)s,
            %(occurred_at)s, %(request_id)s, %(source_ip)s
        )
        """,
        row,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prerequisites
# ─────────────────────────────────────────────────────────────────────────────


class TestPrerequisites:
    def test_pg_trgm_extension_active(self, cur):
        cur.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cur.fetchone()[0] == 1, "pg_trgm extension must be enabled"

    def test_control_tenants_exists(self, cur):
        """F001 migration must have run; workspaces FK depends on tenants."""
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='control' AND table_name='tenants'"
        )
        assert cur.fetchone()[0] == 1, "control.tenants must exist (F001 dependency)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Enum Type
# ─────────────────────────────────────────────────────────────────────────────


class TestEnumType:
    def _enum_values(self, cur, schema, typename):
        cur.execute(
            """
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = %s AND t.typname = %s
            """,
            (schema, typename),
        )
        return {row[0] for row in cur.fetchall()}

    def test_workspace_status_enum_exists(self, cur):
        vals = self._enum_values(cur, "control", "workspace_status_enum")
        assert vals, "workspace_status_enum must exist in control schema"

    def test_workspace_status_enum_values(self, cur):
        vals = self._enum_values(cur, "control", "workspace_status_enum")
        assert vals == {"active", "archived"}

    def test_workspace_status_enum_values_are_lowercase(self, cur):
        vals = self._enum_values(cur, "control", "workspace_status_enum")
        for v in vals:
            assert v == v.lower(), f"Enum value '{v}' must be lowercase"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Table Structure — workspaces
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspacesTable:
    def test_workspaces_table_exists(self, cur):
        cols = _columns(cur, "control", "workspaces")
        assert cols, "control.workspaces must exist"

    def test_workspaces_has_14_columns(self, cur):
        cols = _columns(cur, "control", "workspaces")
        assert len(cols) == 14, f"Expected 14 columns, got {len(cols)}: {list(cols.keys())}"

    def test_workspaces_not_null_columns(self, cur):
        cols = _columns(cur, "control", "workspaces")
        required_not_null = [
            "workspace_id",
            "tenant_id",
            "workspace_name",
            "workspace_name_lower",
            "workspace_slug",
            "default_timezone",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "version",
        ]
        for col in required_not_null:
            assert cols[col]["nullable"] == "NO", (
                f"Column '{col}' must be NOT NULL; got nullable='{cols[col]['nullable']}'"
            )

    def test_workspaces_nullable_columns(self, cur):
        cols = _columns(cur, "control", "workspaces")
        for col in ["description", "status_reason"]:
            assert cols[col]["nullable"] == "YES", f"Column '{col}' must be NULL-able"

    def test_workspaces_status_default_is_active(self, cur):
        cols = _columns(cur, "control", "workspaces")
        assert "active" in (cols["status"]["default"] or ""), (
            "status column default must be 'active'"
        )

    def test_workspaces_default_timezone_default_is_utc(self, cur):
        cols = _columns(cur, "control", "workspaces")
        assert "UTC" in (cols["default_timezone"]["default"] or ""), (
            "default_timezone column default must be 'UTC'"
        )

    def test_workspaces_version_default_is_zero(self, cur):
        cols = _columns(cur, "control", "workspaces")
        assert cols["version"]["default"] == "0", "version column default must be 0"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Table Structure — workspace_audit_logs
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceAuditLogsTable:
    def test_audit_logs_table_exists(self, cur):
        cols = _columns(cur, "control", "workspace_audit_logs")
        assert cols, "control.workspace_audit_logs must exist"

    def test_audit_logs_has_11_columns(self, cur):
        cols = _columns(cur, "control", "workspace_audit_logs")
        assert len(cols) == 11, f"Expected 11 columns, got {len(cols)}: {list(cols.keys())}"

    def test_audit_logs_not_null_columns(self, cur):
        cols = _columns(cur, "control", "workspace_audit_logs")
        required_not_null = [
            "log_id",
            "tenant_id",
            "workspace_id",
            "action_type",
            "actor_id",
            "actor_role",
            "new_data",
            "occurred_at",
        ]
        for col in required_not_null:
            assert cols[col]["nullable"] == "NO", f"Column '{col}' must be NOT NULL"

    def test_audit_logs_nullable_columns(self, cur):
        cols = _columns(cur, "control", "workspace_audit_logs")
        for col in ["previous_data", "request_id", "source_ip"]:
            assert cols[col]["nullable"] == "YES", f"Column '{col}' must be NULL-able"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexes:
    def test_workspaces_has_all_7_index_names(self, cur):
        indexes = _indexes(cur, "control", "workspaces")
        expected = {
            "pk_workspaces",
            "uq_workspaces_name_lower_per_tenant",
            "uq_workspaces_slug_per_tenant",
            "ix_workspaces_tenant_status_created_at",
            "ix_workspaces_tenant_status_updated_at",
            "ix_workspaces_name_trgm",
            "ix_workspaces_slug_trgm",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on workspaces: {missing}"

    def test_audit_logs_has_all_5_index_names(self, cur):
        indexes = _indexes(cur, "control", "workspace_audit_logs")
        expected = {
            "pk_workspace_audit_logs",
            "ix_audit_logs_workspace_occurred_at",
            # Renamed from TDD §11.2 (ix_audit_logs_tenant_occurred_at) to avoid
            # collision with F001's tenant_audit_logs index of the same name.
            "ix_ws_audit_logs_tenant_occurred_at",
            "ix_audit_logs_action_type",
            # Renamed from TDD §11.2 (ix_audit_logs_actor_id) for the same reason.
            "ix_ws_audit_logs_actor_id",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on workspace_audit_logs: {missing}"

    def test_total_index_count_workspaces(self, cur):
        indexes = _indexes(cur, "control", "workspaces")
        assert len(indexes) == 7, f"Expected 7 indexes on workspaces, got {len(indexes)}: {indexes}"

    def test_total_index_count_audit_logs(self, cur):
        indexes = _indexes(cur, "control", "workspace_audit_logs")
        assert len(indexes) == 5, (
            f"Expected 5 indexes on workspace_audit_logs, got {len(indexes)}: {indexes}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Constraints — ck_status_reason_on_archived (AC-2, AC-3)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckConstraintStatusReason:
    def test_archived_with_null_reason_rejected(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason=None)
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_workspace(cur, row)

    def test_archived_with_empty_string_reason_rejected(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason="")
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_workspace(cur, row)

    def test_archived_with_whitespace_only_reason_rejected(self, cur):
        """TRIM of all-space string is empty string; CHAR_LENGTH = 0 < 10."""
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason="         ")
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_workspace(cur, row)

    def test_archived_with_short_reason_rejected(self, cur):
        """9 chars after trim is less than the required 10."""
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason="tooshort!")
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_workspace(cur, row)

    def test_archived_with_exactly_10_char_reason_accepted(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason="0123456789")
        _insert_workspace(cur, row)  # must not raise

    def test_archived_with_valid_reason_accepted(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="archived", status_reason="Team has been decommissioned")
        _insert_workspace(cur, row)  # must not raise

    def test_active_with_null_reason_accepted(self, cur):
        """status_reason is optional for active workspaces."""
        tid = _new_tenant(cur)
        row = _workspace_row(tid, status="active", status_reason=None)
        _insert_workspace(cur, row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 7. Constraints — ck_version_non_negative (AC-6)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckConstraintVersion:
    def test_negative_version_rejected(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, version=-1)
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_workspace(cur, row)

    def test_zero_version_accepted(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, version=0)
        _insert_workspace(cur, row)  # must not raise

    def test_positive_version_accepted(self, cur):
        tid = _new_tenant(cur)
        row = _workspace_row(tid, version=5)
        _insert_workspace(cur, row)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 8. Unique Constraints (AC-4)
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueConstraints:
    def test_duplicate_workspace_name_lower_per_tenant_rejected(self, cur):
        tid = _new_tenant(cur)
        shared_name_lower = "shared workspace name"
        row1 = _workspace_row(
            tid,
            workspace_name="Shared Workspace Name",
            workspace_name_lower=shared_name_lower,
            workspace_slug="shared-slug-1",
        )
        row2 = _workspace_row(
            tid,
            workspace_name="shared workspace name",
            workspace_name_lower=shared_name_lower,
            workspace_slug="shared-slug-2",
        )
        _insert_workspace(cur, row1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert_workspace(cur, row2)

    def test_duplicate_slug_per_tenant_rejected(self, cur):
        tid = _new_tenant(cur)
        slug = "dup-slug"
        row1 = _workspace_row(tid, workspace_slug=slug)
        row2 = _workspace_row(tid, workspace_slug=slug)
        _insert_workspace(cur, row1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert_workspace(cur, row2)

    def test_same_name_lower_different_tenant_allowed(self, cur):
        tid1 = _new_tenant(cur)
        tid2 = _new_tenant(cur)
        shared = "shared workspace"
        row1 = _workspace_row(
            tid1, workspace_name=shared, workspace_name_lower=shared.lower(), workspace_slug="ws-t1"
        )
        row2 = _workspace_row(
            tid2, workspace_name=shared, workspace_name_lower=shared.lower(), workspace_slug="ws-t2"
        )
        _insert_workspace(cur, row1)
        _insert_workspace(cur, row2)  # must not raise — different tenant

    def test_same_slug_different_tenant_allowed(self, cur):
        tid1 = _new_tenant(cur)
        tid2 = _new_tenant(cur)
        slug = "same-slug"
        row1 = _workspace_row(tid1, workspace_slug=slug)
        row2 = _workspace_row(tid2, workspace_slug=slug)
        _insert_workspace(cur, row1)
        _insert_workspace(cur, row2)  # must not raise — different tenant


# ─────────────────────────────────────────────────────────────────────────────
# 9. Foreign Key Constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestForeignKeyConstraints:
    def test_workspace_with_nonexistent_tenant_rejected(self, cur):
        nonexistent_tenant = uuid.uuid4()
        row = _workspace_row(nonexistent_tenant)
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _insert_workspace(cur, row)

    def test_audit_log_with_nonexistent_workspace_rejected(self, cur):
        tid = _new_tenant(cur)
        row = _audit_row(tid, uuid.uuid4())  # workspace_id does not exist
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _insert_audit(cur, row)

    def test_audit_log_with_nonexistent_tenant_rejected(self, cur):
        # Insert a real tenant+workspace to get a valid workspace_id
        tid = _new_tenant(cur)
        ws_row = _workspace_row(tid)
        _insert_workspace(cur, ws_row)
        # Now try to insert an audit log with a fake tenant_id
        row = _audit_row(uuid.uuid4(), ws_row["workspace_id"])
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _insert_audit(cur, row)


# ─────────────────────────────────────────────────────────────────────────────
# 10. DB Role Grants
# ─────────────────────────────────────────────────────────────────────────────


class TestRoleGrants:
    def _has_privilege(self, cur, role, schema, table, privilege):
        cur.execute(
            "SELECT has_table_privilege(%s, %s, %s)",
            (role, f"{schema}.{table}", privilege),
        )
        return cur.fetchone()[0]

    @pytest.mark.skipif(
        not os.environ.get("CHECK_ROLE_GRANTS"),
        reason="Set CHECK_ROLE_GRANTS=1 to verify dq_app_role privileges",
    )
    def test_dq_app_role_has_insert_on_workspaces(self, cur):
        assert self._has_privilege(cur, "dq_app_role", "control", "workspaces", "INSERT")

    @pytest.mark.skipif(
        not os.environ.get("CHECK_ROLE_GRANTS"),
        reason="Set CHECK_ROLE_GRANTS=1 to verify dq_app_role privileges",
    )
    def test_dq_app_role_has_select_on_workspaces(self, cur):
        assert self._has_privilege(cur, "dq_app_role", "control", "workspaces", "SELECT")

    @pytest.mark.skipif(
        not os.environ.get("CHECK_ROLE_GRANTS"),
        reason="Set CHECK_ROLE_GRANTS=1 to verify dq_app_role privileges",
    )
    def test_dq_app_role_has_update_on_workspaces(self, cur):
        assert self._has_privilege(cur, "dq_app_role", "control", "workspaces", "UPDATE")

    @pytest.mark.skipif(
        not os.environ.get("CHECK_ROLE_GRANTS"),
        reason="Set CHECK_ROLE_GRANTS=1 to verify dq_app_role privileges",
    )
    def test_dq_app_role_has_insert_on_audit_logs(self, cur):
        assert self._has_privilege(cur, "dq_app_role", "control", "workspace_audit_logs", "INSERT")

    @pytest.mark.skipif(
        not os.environ.get("CHECK_ROLE_GRANTS"),
        reason="Set CHECK_ROLE_GRANTS=1 to verify dq_app_role privileges",
    )
    def test_dq_app_role_has_select_on_audit_logs(self, cur):
        assert self._has_privilege(cur, "dq_app_role", "control", "workspace_audit_logs", "SELECT")
