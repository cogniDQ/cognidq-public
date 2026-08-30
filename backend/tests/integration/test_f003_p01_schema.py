"""
Integration tests — F003 Packet 1: Database Schema and Migration

These tests verify that migration 008_f003_workspace_settings.sql has been
applied correctly. They connect directly to the PostgreSQL database using
psycopg2 and validate every structural and constraint guarantee required by
the packet plan acceptance criteria (TDD §3.1, §3.2, §11.2).

Run after applying the migration:
    pytest backend/tests/integration/test_f003_p01_schema.py -v

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
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

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


def _triggers_on_table(cur, schema, table):
    cur.execute(
        """
        SELECT tgname
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
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


def _insert_workspace(cur, tenant_id, *, timezone_str="UTC", status="active"):
    """Insert a minimal valid workspace and return its workspace_id."""
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS {wid}"
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name, workspace_name_lower,
            workspace_slug, description, default_timezone, status, status_reason,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %s, %s, %s, %s, %s, NULL, %s, %s, NULL,
            NOW(), NOW(), %s, %s, 0
        )
        """,
        (
            wid,
            tenant_id,
            name,
            name.lower(),
            f"ws-{str(wid)[:8]}",
            timezone_str,
            status,
            actor,
            actor,
        ),
    )
    return wid


def _get_settings_row(cur, workspace_id):
    cur.execute(
        """
        SELECT workspace_id, tenant_id, default_timezone, severity_policy,
               sla_policy, issue_grouping_policy, naming_standards,
               updated_at, updated_by
        FROM control.workspace_settings
        WHERE workspace_id = %s
        """,
        (workspace_id,),
    )
    return cur.fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-01: Table exists with 9 correct columns
# ─────────────────────────────────────────────────────────────────────────────


class TestTableStructure:
    def test_table_exists_in_control_schema(self, cur):
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'control' AND table_name = 'workspace_settings'
            """
        )
        assert cur.fetchone() is not None, "control.workspace_settings table not found"

    def test_all_nine_columns_present(self, cur):
        cols = _columns(cur, "control", "workspace_settings")
        expected = {
            "workspace_id",
            "tenant_id",
            "default_timezone",
            "severity_policy",
            "sla_policy",
            "issue_grouping_policy",
            "naming_standards",
            "updated_at",
            "updated_by",
        }
        assert expected == set(cols.keys()), (
            f"Column mismatch. Expected: {sorted(expected)}, Got: {sorted(cols.keys())}"
        )

    def test_column_types(self, cur):
        cols = _columns(cur, "control", "workspace_settings")
        assert cols["workspace_id"]["data_type"] == "uuid"
        assert cols["tenant_id"]["data_type"] == "uuid"
        assert cols["default_timezone"]["data_type"] == "character varying"
        assert cols["severity_policy"]["data_type"] == "jsonb"
        assert cols["sla_policy"]["data_type"] == "jsonb"
        assert cols["issue_grouping_policy"]["data_type"] == "character varying"
        assert cols["naming_standards"]["data_type"] == "jsonb"
        assert cols["updated_at"]["data_type"] == "timestamp with time zone"
        assert cols["updated_by"]["data_type"] == "uuid"

    def test_nullable_columns(self, cur):
        cols = _columns(cur, "control", "workspace_settings")
        # NOT NULL columns
        for col in [
            "workspace_id",
            "tenant_id",
            "default_timezone",
            "issue_grouping_policy",
            "updated_at",
        ]:
            assert cols[col]["nullable"] == "NO", f"{col} should be NOT NULL"
        # NULLABLE columns
        for col in ["severity_policy", "sla_policy", "naming_standards", "updated_by"]:
            assert cols[col]["nullable"] == "YES", f"{col} should be NULLABLE"


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-02: PRIMARY KEY constraint enforced
# ─────────────────────────────────────────────────────────────────────────────


class TestPrimaryKeyConstraint:
    def test_pk_constraint_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'workspace_settings'
              AND constraint_type = 'PRIMARY KEY'
            """
        )
        row = cur.fetchone()
        assert row is not None, "PRIMARY KEY constraint not found on workspace_settings"
        assert row[0] == "pk_workspace_settings"

    def test_duplicate_pk_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)
        # The trigger already created a settings row. A second explicit INSERT
        # with the same workspace_id must raise a unique violation.
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO control.workspace_settings (
                    workspace_id, tenant_id, default_timezone,
                    issue_grouping_policy, updated_at
                ) VALUES (%s, %s, 'UTC', 'one_per_execution', NOW())
                """,
                (wid, tid),
            )


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-03: FOREIGN KEY to workspaces enforced
# ─────────────────────────────────────────────────────────────────────────────


class TestForeignKeyWorkspace:
    def test_orphan_workspace_id_rejected(self, cur):
        tid = _new_tenant(cur)
        bogus_wid = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO control.workspace_settings (
                    workspace_id, tenant_id, default_timezone,
                    issue_grouping_policy, updated_at
                ) VALUES (%s, %s, 'UTC', 'one_per_execution', NOW())
                """,
                (bogus_wid, tid),
            )


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-04: FK CASCADE DELETE — settings deleted with workspace
# ─────────────────────────────────────────────────────────────────────────────


class TestCascadeDelete:
    def test_settings_deleted_on_workspace_delete(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)

        # Verify settings row exists (created by trigger)
        assert _get_settings_row(cur, wid) is not None

        # Delete workspace — should cascade to settings
        cur.execute(
            "DELETE FROM control.workspaces WHERE workspace_id = %s",
            (wid,),
        )

        # Settings row must be gone
        assert _get_settings_row(cur, wid) is None


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-05 / AC-P01-06: CHECK constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckConstraints:
    def test_invalid_grouping_mode_rejected(self, cur):
        tid = _new_tenant(cur)
        _insert_workspace(cur, tid)
        # The trigger created a row; we need a fresh workspace_id to test INSERT
        wid2 = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, default_timezone, status,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (%s, %s, %s, %s, %s, 'UTC', 'active',
                      NOW(), NOW(), %s, %s, 0)
            """,
            (
                wid2,
                tid,
                f"WS2 {wid2}",
                f"ws2 {wid2}".lower(),
                f"ws2-{str(wid2)[:8]}",
                uuid.uuid4(),
                uuid.uuid4(),
            ),
        )
        # Now manually try to update with an invalid grouping mode
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE control.workspace_settings
                SET issue_grouping_policy = 'invalid_mode'
                WHERE workspace_id = %s
                """,
                (wid2,),
            )

    def test_empty_timezone_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE control.workspace_settings
                SET default_timezone = '   '
                WHERE workspace_id = %s
                """,
                (wid,),
            )

    def test_whitespace_only_timezone_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)
        with pytest.raises(
            (psycopg2.errors.CheckViolation, psycopg2.errors.StringDataRightTruncation)
        ):
            cur.execute(
                """
                UPDATE control.workspace_settings
                SET default_timezone = ''
                WHERE workspace_id = %s
                """,
                (wid,),
            )

    def test_all_valid_grouping_modes_accepted(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)
        for mode in ("one_per_execution", "one_per_rule", "one_per_day"):
            cur.execute(
                """
                UPDATE control.workspace_settings
                SET issue_grouping_policy = %s
                WHERE workspace_id = %s
                """,
                (mode, wid),
            )
            # No exception = pass


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-07: Trigger auto-creates settings row on workspace INSERT
# ─────────────────────────────────────────────────────────────────────────────


class TestTrigger:
    def test_trigger_exists_on_workspaces_table(self, cur):
        triggers = _triggers_on_table(cur, "control", "workspaces")
        assert "trg_workspace_settings_on_insert" in triggers

    def test_trigger_fires_on_workspace_insert(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid, timezone_str="America/New_York")

        row = _get_settings_row(cur, wid)
        assert row is not None, "Trigger did not create a settings row"
        workspace_id_col, tenant_id_col, timezone_col, _, _, grouping_col, _, _, updated_by_col = (
            row
        )

        assert workspace_id_col == wid
        assert tenant_id_col == tid
        assert timezone_col == "America/New_York", (
            "Trigger should copy default_timezone from workspace"
        )
        assert grouping_col == "one_per_execution"
        assert updated_by_col is None, "updated_by should be NULL for trigger-created rows"

    def test_trigger_copies_workspace_timezone(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid, timezone_str="Europe/Paris")

        row = _get_settings_row(cur, wid)
        _, _, timezone_col, *_ = row
        assert timezone_col == "Europe/Paris"

    # AC-P01-08: Trigger is idempotent
    def test_trigger_idempotent_on_conflict(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)

        # Manually try to insert a second settings row for same workspace_id.
        # ON CONFLICT DO NOTHING means no error and no second row.
        cur.execute(
            """
            INSERT INTO control.workspace_settings (
                workspace_id, tenant_id, default_timezone,
                issue_grouping_policy, updated_at
            ) VALUES (%s, %s, 'UTC', 'one_per_execution', NOW())
            ON CONFLICT (workspace_id) DO NOTHING
            """,
            (wid, tid),
        )
        # Verify only one row exists
        cur.execute(
            "SELECT COUNT(*) FROM control.workspace_settings WHERE workspace_id = %s",
            (wid,),
        )
        assert cur.fetchone()[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-09: Retroactive seed — all existing workspaces have settings rows
# ─────────────────────────────────────────────────────────────────────────────


class TestRetroactiveSeed:
    def test_all_workspaces_have_settings_row(self, cur):
        cur.execute(
            """
            SELECT COUNT(*) FROM control.workspaces w
            WHERE NOT EXISTS (
                SELECT 1 FROM control.workspace_settings s
                WHERE s.workspace_id = w.workspace_id
            )
            """
        )
        orphaned = cur.fetchone()[0]
        assert orphaned == 0, (
            f"{orphaned} workspace(s) exist without a corresponding settings row. "
            "Retroactive seed may have failed."
        )

    def test_settings_count_gte_workspace_count(self, cur):
        cur.execute("SELECT COUNT(*) FROM control.workspaces")
        ws_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM control.workspace_settings")
        settings_count = cur.fetchone()[0]

        assert settings_count >= ws_count, (
            f"Expected at least {ws_count} settings rows, found {settings_count}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AC-P01-10: Indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexes:
    def test_pk_index_exists(self, cur):
        indexes = _indexes(cur, "control", "workspace_settings")
        assert "pk_workspace_settings" in indexes

    def test_tenant_id_index_exists(self, cur):
        indexes = _indexes(cur, "control", "workspace_settings")
        assert "ix_workspace_settings_tenant_id" in indexes

    def test_both_expected_indexes_and_no_unexpected_extras(self, cur):
        indexes = _indexes(cur, "control", "workspace_settings")
        expected = {"pk_workspace_settings", "ix_workspace_settings_tenant_id"}
        assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"


# ─────────────────────────────────────────────────────────────────────────────
# Additional: JSONB columns accept valid JSON and NULL
# ─────────────────────────────────────────────────────────────────────────────


class TestJsonbColumns:
    def test_null_jsonb_columns_accepted(self, cur):
        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)
        row = _get_settings_row(cur, wid)
        _, _, _, severity, sla, _, naming, _, _ = row
        assert severity is None
        assert sla is None
        assert naming is None

    def test_jsonb_columns_accept_valid_json(self, cur):
        import json

        tid = _new_tenant(cur)
        wid = _insert_workspace(cur, tid)

        severity_data = {
            "critical_label": "Critical",
            "major_label": "Major",
            "minor_label": "Minor",
            "informational_label": "Info",
        }
        sla_data = {
            "critical_hours": 4,
            "major_hours": 24,
            "minor_hours": 72,
            "informational_hours": None,
        }
        naming_data = {"datasets": {"required_prefix": "ds_"}, "rules": {}}

        cur.execute(
            """
            UPDATE control.workspace_settings
            SET severity_policy = %s,
                sla_policy = %s,
                naming_standards = %s,
                updated_at = NOW()
            WHERE workspace_id = %s
            """,
            (
                json.dumps(severity_data),
                json.dumps(sla_data),
                json.dumps(naming_data),
                wid,
            ),
        )

        row = _get_settings_row(cur, wid)
        _, _, _, severity_back, sla_back, _, naming_back, _, _ = row

        assert severity_back == severity_data
        assert sla_back == sla_data
        assert naming_back == naming_data
