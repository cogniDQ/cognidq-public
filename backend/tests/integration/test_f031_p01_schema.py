"""
Integration tests — F031 Packet 1: DB Migration 013 — public.issues

Verifies that migration 013_f031_issues.sql has been applied correctly.
Checks table structure, column types, CHECK constraints, FK constraints,
indexes, and the updated_at trigger.

Run after applying the migration:
    pytest backend/tests/integration/test_f031_p01_schema.py -v

Environment variable:
    DATABASE_URL  (e.g. postgresql://postgres:postgres@localhost:5432/dataquality_db)
    Defaults to the local Docker Compose default if not set.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.errors
import psycopg2.extras
import pytest

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

SCHEMA = "public"
TABLE = "issues"
FULL_TABLE = f"{SCHEMA}.{TABLE}"

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
    mgmt.execute("SAVEPOINT sp_f031_p01")
    mgmt.close()
    cursor = conn.cursor()
    yield cursor
    cursor.close()
    cleanup = conn.cursor()
    cleanup.execute("ROLLBACK TO SAVEPOINT sp_f031_p01")
    cleanup.execute("RELEASE SAVEPOINT sp_f031_p01")
    cleanup.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _columns(cur):
    """Return a dict of {column_name: data_type} for public.issues."""
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (SCHEMA, TABLE),
    )
    return {
        row[0]: {"data_type": row[1], "nullable": row[2], "default": row[3]}
        for row in cur.fetchall()
    }


def _constraints(cur):
    """Return a dict of {constraint_name: constraint_type} for public.issues."""
    cur.execute(
        """
        SELECT c.conname, c.contype
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = %s AND t.relname = %s
        """,
        (SCHEMA, TABLE),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def _indexes(cur):
    """Return a list of index names on public.issues."""
    cur.execute(
        """
        SELECT i.relname
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = %s AND t.relname = %s
        """,
        (SCHEMA, TABLE),
    )
    return [row[0] for row in cur.fetchall()]


def _table_exists(cur):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (SCHEMA, TABLE),
    )
    return cur.fetchone() is not None


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-001: Table existence and expected columns
# ─────────────────────────────────────────────────────────────────────────────


class TestTableStructure:
    """P01-AC-001: public.issues exists with expected columns."""

    def test_table_exists(self, cur):
        assert _table_exists(cur), f"Table {FULL_TABLE} does not exist"

    def test_required_columns_present(self, cur):
        columns = _columns(cur)
        required = [
            "id",
            "workspace_id",
            "tenant_id",
            "flow_execution_id",
            "flow_node_result_id",
            "rule_id",
            "dataset_id",
            "assignee_id",
            "issue_type",
            "severity",
            "status",
            "title",
            "impact_summary",
            "failure_count",
            "rows_scanned",
            "pass_rate",
            "due_at",
            "opened_at",
            "resolved_at",
            "closed_at",
            "updated_at",
            "created_at",
        ]
        missing = [c for c in required if c not in columns]
        assert not missing, f"Missing columns: {missing}"

    def test_id_column_is_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["id"]["nullable"] == "NO"

    def test_workspace_id_is_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["workspace_id"]["nullable"] == "NO"

    def test_flow_execution_id_is_not_nullable(self, cur):
        cols = _columns(cur)
        assert cols["flow_execution_id"]["nullable"] == "NO"

    def test_nullable_optional_columns(self, cur):
        """These columns should allow NULL."""
        cols = _columns(cur)
        for col in (
            "flow_node_result_id",
            "rule_id",
            "dataset_id",
            "assignee_id",
            "impact_summary",
            "failure_count",
            "rows_scanned",
            "pass_rate",
            "due_at",
            "resolved_at",
            "closed_at",
        ):
            assert cols[col]["nullable"] == "YES", f"Expected {col} to be nullable"

    def test_status_default_is_open(self, cur):
        cols = _columns(cur)
        assert cols["status"]["default"] is not None
        assert "open" in cols["status"]["default"]


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-002: CHECK constraint on issue_type
# ─────────────────────────────────────────────────────────────────────────────


class TestIssueTypeCheckConstraint:
    """P01-AC-002: issue_type CHECK rejects values outside the allowed enum."""

    def _seed_workspace_tenant(self, cur):
        """Return (workspace_id, tenant_id) from any existing row or raise skip."""
        cur.execute("SELECT workspace_id, tenant_id FROM control.workspaces LIMIT 1")
        row = cur.fetchone()
        if not row:
            pytest.skip("No workspace rows available for FK seed")
        return row

    def _seed_execution(self, cur, workspace_id):
        """Return a flow_execution id for FK use."""
        cur.execute("SELECT id FROM public.flow_executions LIMIT 1")
        row = cur.fetchone()
        if not row:
            pytest.skip("No flow_executions rows available for FK seed")
        return row[0]

    def _minimal_insert(self, cur, issue_type):
        ws_id, t_id = self._seed_workspace_tenant(cur)
        exec_id = self._seed_execution(cur, ws_id)
        cur.execute(
            """
            INSERT INTO public.issues
                (workspace_id, tenant_id, flow_execution_id,
                 issue_type, severity, title)
            VALUES (%s, %s, %s, %s, 'critical', 'Test issue')
            """,
            (ws_id, t_id, exec_id, issue_type),
        )

    def test_valid_threshold_breach_accepted(self, cur):
        """Valid issue_type='threshold_breach' must not raise."""
        try:
            self._minimal_insert(cur, "threshold_breach")
        except psycopg2.errors.ForeignKeyViolation:
            pytest.skip("FK seed not available")

    def test_valid_execution_error_accepted(self, cur):
        """Valid issue_type='execution_error' must not raise."""
        try:
            self._minimal_insert(cur, "execution_error")
        except psycopg2.errors.ForeignKeyViolation:
            pytest.skip("FK seed not available")

    def test_invalid_issue_type_rejected(self, cur):
        """Invalid issue_type must raise CheckViolation."""
        with pytest.raises(psycopg2.errors.CheckViolation):
            self._minimal_insert(cur, "unknown_type")


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-003: CHECK constraint on severity
# ─────────────────────────────────────────────────────────────────────────────


class TestSeverityCheckConstraint:
    """P01-AC-003: severity CHECK rejects values outside the allowed enum."""

    def test_check_constraint_exists(self, cur):
        constraints = _constraints(cur)
        assert "ck_issues_severity" in constraints, "ck_issues_severity CHECK constraint not found"

    def test_valid_severities_in_schema(self, cur):
        """Verify the CHECK constraint references all 4 valid severities."""
        cur.execute(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND t.relname = 'issues'
              AND c.conname = 'ck_issues_severity'
            """
        )
        row = cur.fetchone()
        assert row is not None
        definition = row[0]
        for sev in ("critical", "major", "minor", "informational"):
            assert sev in definition, f"Severity '{sev}' not found in constraint definition"


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-004: CHECK constraint on status
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusCheckConstraint:
    """P01-AC-004: status CHECK rejects values outside the allowed enum."""

    def test_check_constraint_exists(self, cur):
        constraints = _constraints(cur)
        assert "ck_issues_status" in constraints, "ck_issues_status CHECK constraint not found"

    def test_valid_statuses_in_schema(self, cur):
        cur.execute(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND t.relname = 'issues'
              AND c.conname = 'ck_issues_status'
            """
        )
        row = cur.fetchone()
        assert row is not None
        definition = row[0]
        for status in ("open", "in_progress", "resolved", "closed", "reopened"):
            assert status in definition, f"Status '{status}' not found in constraint definition"


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-005: FK workspace_id → control.workspaces(workspace_id) CASCADE
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceForeignKey:
    """P01-AC-005: FK constraint on workspace_id references control.workspaces."""

    def test_fk_constraint_exists(self, cur):
        constraints = _constraints(cur)
        assert "fk_issues_workspace" in constraints, "fk_issues_workspace FK constraint not found"

    def test_invalid_workspace_id_rejected(self, cur):
        """Inserting a non-existent workspace_id must raise ForeignKeyViolation."""
        cur.execute("SELECT id FROM public.flow_executions LIMIT 1")
        row = cur.fetchone()
        if not row:
            pytest.skip("No flow_executions available for FK test")
        exec_id = row[0]
        fake_workspace = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO public.issues
                    (workspace_id, tenant_id, flow_execution_id,
                     issue_type, severity, title)
                VALUES (%s, %s, %s, 'threshold_breach', 'critical', 'test')
                """,
                (fake_workspace, uuid.uuid4(), exec_id),
            )


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-006: FK flow_execution_id → flow_executions(id) CASCADE
# ─────────────────────────────────────────────────────────────────────────────


class TestFlowExecutionForeignKey:
    """P01-AC-006: FK constraint on flow_execution_id references flow_executions."""

    def test_fk_constraint_exists(self, cur):
        constraints = _constraints(cur)
        assert "fk_issues_flow_execution" in constraints, (
            "fk_issues_flow_execution FK constraint not found"
        )

    def test_invalid_flow_execution_id_rejected(self, cur):
        """Inserting a non-existent flow_execution_id must raise ForeignKeyViolation."""
        cur.execute("SELECT workspace_id, tenant_id FROM control.workspaces LIMIT 1")
        row = cur.fetchone()
        if not row:
            pytest.skip("No workspaces available for FK test")
        ws_id, t_id = row
        fake_exec = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO public.issues
                    (workspace_id, tenant_id, flow_execution_id,
                     issue_type, severity, title)
                VALUES (%s, %s, %s, 'threshold_breach', 'critical', 'test')
                """,
                (ws_id, t_id, fake_exec),
            )


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-007: All nine indexes exist
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexes:
    """P01-AC-007: All required indexes are present on public.issues."""

    EXPECTED_INDEXES = [
        "idx_issues_workspace_opened",
        "idx_issues_workspace_status",
        "idx_issues_workspace_severity",
        "idx_issues_flow_execution",
        "idx_issues_rule",
        "idx_issues_dataset",
        "idx_issues_assignee",
        "idx_issues_due_at",
        "uq_issues_node_result",
    ]

    def test_all_indexes_present(self, cur):
        present = _indexes(cur)
        missing = [idx for idx in self.EXPECTED_INDEXES if idx not in present]
        assert not missing, f"Missing indexes: {missing}"

    def test_index_count(self, cur):
        """Sanity check: at least 9 non-PK indexes plus the PK index."""
        present = _indexes(cur)
        # PK index (pk_issues) + 9 explicit indexes = at least 10
        assert len(present) >= 10, (
            f"Expected at least 10 indexes (PK + 9 explicit), found {len(present)}: {present}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# P01-AC-008: updated_at trigger fires on UPDATE
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdatedAtTrigger:
    """P01-AC-008: issues_set_updated_at trigger updates updated_at on UPDATE."""

    def test_trigger_exists(self, cur):
        cur.execute(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE tgname = 'issues_set_updated_at'
            """
        )
        row = cur.fetchone()
        assert row is not None, "Trigger 'issues_set_updated_at' not found"

    def test_set_updated_at_function_exists(self, cur):
        cur.execute(
            """
            SELECT proname
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public' AND p.proname = 'set_updated_at'
            """
        )
        row = cur.fetchone()
        assert row is not None, "Function public.set_updated_at() not found"

    def test_trigger_fires_on_update(self, cur):
        """Insert a row, then UPDATE it; updated_at must change."""
        cur.execute("SELECT workspace_id, tenant_id FROM control.workspaces LIMIT 1")
        ws_row = cur.fetchone()
        if not ws_row:
            pytest.skip("No workspaces available for trigger test")
        ws_id, t_id = ws_row

        cur.execute("SELECT id FROM public.flow_executions LIMIT 1")
        exec_row = cur.fetchone()
        if not exec_row:
            pytest.skip("No flow_executions available for trigger test")
        exec_id = exec_row[0]

        issue_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO public.issues
                (id, workspace_id, tenant_id, flow_execution_id,
                 issue_type, severity, title,
                 opened_at, updated_at, created_at)
            VALUES (%s, %s, %s, %s,
                    'threshold_breach', 'critical', 'Trigger test',
                    NOW() - INTERVAL '1 minute',
                    NOW() - INTERVAL '1 minute',
                    NOW() - INTERVAL '1 minute')
            """,
            (issue_id, ws_id, t_id, exec_id),
        )

        # Capture updated_at before the UPDATE
        cur.execute(
            "SELECT updated_at FROM public.issues WHERE id = %s",
            (issue_id,),
        )
        before = cur.fetchone()[0]

        # Perform UPDATE (simulate a status change)
        cur.execute(
            "UPDATE public.issues SET status = 'in_progress' WHERE id = %s",
            (issue_id,),
        )

        cur.execute(
            "SELECT updated_at FROM public.issues WHERE id = %s",
            (issue_id,),
        )
        after = cur.fetchone()[0]

        assert after > before, (
            f"updated_at was not advanced by trigger: before={before}, after={after}"
        )
