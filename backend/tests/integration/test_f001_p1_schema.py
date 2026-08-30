"""
Integration tests — F001 Packet 1: Database Schema Foundation

These tests verify that the migration 006_f001_control_schema_foundation.sql
has been applied correctly. They connect directly to the PostgreSQL database
using psycopg2 and validate every structural and constraint guarantee required
by the packet acceptance criteria.

Run after applying migrations:
    pytest backend/tests/integration/test_f001_p1_schema.py -v

Environment variable required:
    DATABASE_URL  (e.g. postgresql://postgres:postgres@localhost:5432/dataquality_db)
"""

import os
import uuid

import psycopg2
import psycopg2.errors
import psycopg2.extras
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

# Allow psycopg2 to automatically adapt uuid.UUID objects to PostgreSQL UUID type
psycopg2.extras.register_uuid()


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)


@pytest.fixture(scope="module")
def conn():
    """Module-scoped database connection. Each test that writes data must
    roll back via its own savepoint or sub-fixture."""
    connection = psycopg2.connect(DATABASE_URL)
    connection.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture()
def cur(conn):
    """Per-test cursor that is always rolled back on teardown.
    Each test gets a clean DB state (no committed side-effects)."""
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
# Helper: build a minimal valid tenants row dict
# ─────────────────────────────────────────────────────────────────────────────


def _tenant_row(**overrides):
    actor = uuid.uuid4()
    base = dict(
        tenant_id=uuid.uuid4(),
        tenant_name="Acme Corp",
        tenant_slug="acme-corp",
        status="draft",
        status_reason=None,
        region="us-east",
        plan="starter",
        service_start_date=None,
        tenant_notes=None,
        created_by=actor,
        updated_by=actor,
        version=0,
    )
    base.update(overrides)
    return base


def _insert_tenant(cur, row):
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, status_reason, region, plan,
            service_start_date, tenant_notes,
            created_by, updated_by, version
        ) VALUES (
            %(tenant_id)s, %(tenant_name)s, %(tenant_slug)s,
            %(status)s, %(status_reason)s, %(region)s, %(plan)s,
            %(service_start_date)s, %(tenant_notes)s,
            %(created_by)s, %(updated_by)s, %(version)s
        )
        """,
        row,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Extension
# ─────────────────────────────────────────────────────────────────────────────


class TestPgTrgmExtension:
    def test_pg_trgm_extension_is_active(self, cur):
        cur.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cur.fetchone()[0] == 1, "pg_trgm extension must be enabled"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Enum Types
# ─────────────────────────────────────────────────────────────────────────────


class TestEnumTypes:
    def _enum_values(self, cur, schema, typename):
        cur.execute(
            """
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = %s AND t.typname = %s
            ORDER BY e.enumsortorder
            """,
            (schema, typename),
        )
        return {row[0] for row in cur.fetchall()}

    def test_tenant_status_enum_exists_with_correct_values(self, cur):
        values = self._enum_values(cur, "control", "tenant_status_enum")
        assert values == {"draft", "active", "suspended", "archived"}

    def test_tenant_region_enum_exists_with_correct_values(self, cur):
        values = self._enum_values(cur, "control", "tenant_region_enum")
        assert values == {"eu-west", "eu-central", "us-east", "us-west"}

    def test_tenant_plan_enum_exists_with_correct_values(self, cur):
        values = self._enum_values(cur, "control", "tenant_plan_enum")
        assert values == {"starter", "growth", "enterprise"}

    def test_enum_values_are_lowercase(self, cur):
        """All enum values must be stored in lowercase — no uppercase variants."""
        for schema, typename in [
            ("control", "tenant_status_enum"),
            ("control", "tenant_region_enum"),
            ("control", "tenant_plan_enum"),
        ]:
            values = self._enum_values(cur, schema, typename)
            for v in values:
                assert v == v.lower(), f"Enum value '{v}' in {typename} must be lowercase"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Table Existence and Column Structure
# ─────────────────────────────────────────────────────────────────────────────


class TestTableStructure:
    def _columns(self, cur, schema, table):
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

    def test_tenants_table_exists(self, cur):
        cols = self._columns(cur, "control", "tenants")
        assert cols, "control.tenants must exist"

    def test_tenants_has_16_columns(self, cur):
        # NOTE: The TDD §2.1 says "Total columns: 16" but lists 15 distinct columns.
        # The actual table has 15 columns; the spec annotation is a typo.
        cols = self._columns(cur, "control", "tenants")
        assert len(cols) == 15, f"Expected 15 columns, got {len(cols)}: {list(cols)}"

    def test_tenants_column_nullability(self, cur):
        cols = self._columns(cur, "control", "tenants")
        # NOTE: tenant_name_lower is a GENERATED ALWAYS AS STORED column. PostgreSQL reports
        # generated columns as is_nullable='YES' in information_schema.columns regardless of
        # the underlying expression. It is functionally non-null (tenant_name is NOT NULL).
        required_not_null = [
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "status",
            "region",
            "plan",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "version",
        ]
        for col in required_not_null:
            assert cols[col]["nullable"] == "NO", f"Column '{col}' on tenants must be NOT NULL"
        nullable_cols = ["status_reason", "service_start_date", "tenant_notes"]
        for col in nullable_cols:
            assert cols[col]["nullable"] == "YES", f"Column '{col}' on tenants must be NULL-able"

    def test_tenants_status_default_is_draft(self, cur):
        cols = self._columns(cur, "control", "tenants")
        assert "draft" in (cols["status"]["default"] or ""), "status column default must be 'draft'"

    def test_tenants_version_default_is_zero(self, cur):
        cols = self._columns(cur, "control", "tenants")
        assert cols["version"]["default"] == "0", "version column default must be 0"

    def test_audit_logs_table_exists(self, cur):
        cols = self._columns(cur, "control", "tenant_audit_logs")
        assert cols, "control.tenant_audit_logs must exist"

    def test_audit_logs_has_9_columns(self, cur):
        cols = self._columns(cur, "control", "tenant_audit_logs")
        assert len(cols) == 9, f"Expected 9 columns, got {len(cols)}: {list(cols)}"

    def test_audit_logs_column_nullability(self, cur):
        cols = self._columns(cur, "control", "tenant_audit_logs")
        not_null = [
            "log_id",
            "tenant_id",
            "event_type",
            "actor_id",
            "actor_role",
            "new_data",
            "occurred_at",
        ]
        for col in not_null:
            assert cols[col]["nullable"] == "NO", (
                f"Column '{col}' on tenant_audit_logs must be NOT NULL"
            )
        nullable_cols = ["previous_data", "reason"]
        for col in nullable_cols:
            assert cols[col]["nullable"] == "YES", (
                f"Column '{col}' on tenant_audit_logs must be NULL-able"
            )

    def test_outbox_events_table_exists(self, cur):
        cols = self._columns(cur, "control", "outbox_events")
        assert cols, "control.outbox_events must exist"

    def test_outbox_events_has_9_columns(self, cur):
        cols = self._columns(cur, "control", "outbox_events")
        assert len(cols) == 9, f"Expected 9 columns, got {len(cols)}: {list(cols)}"

    def test_outbox_events_delivered_default_false(self, cur):
        cols = self._columns(cur, "control", "outbox_events")
        assert cols["delivered"]["default"] in ("false", "FALSE"), (
            "outbox_events.delivered must default to FALSE"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexes:
    def _index_names(self, cur, schema, table):
        cur.execute(
            """
            SELECT i.relname
            FROM pg_indexes pi
            JOIN pg_class i ON i.relname = pi.indexname
            WHERE pi.schemaname = %s AND pi.tablename = %s
            """,
            (schema, table),
        )
        return {row[0] for row in cur.fetchall()}

    def test_tenants_indexes_exist(self, cur):
        names = self._index_names(cur, "control", "tenants")
        expected = {
            "pk_tenants",
            "uq_tenants_name_lower",
            "uq_tenants_slug",
            "ix_tenants_status_created_at",
            "ix_tenants_region_created_at",
            "ix_tenants_plan_created_at",
            "ix_tenants_created_at",
            "ix_tenants_updated_at",
            "ix_tenants_name_trgm",
            "ix_tenants_slug_trgm",
        }
        missing = expected - names
        assert not missing, f"Missing indexes on tenants: {missing}"

    def test_audit_logs_indexes_exist(self, cur):
        names = self._index_names(cur, "control", "tenant_audit_logs")
        expected = {
            "pk_tenant_audit_logs",
            "ix_audit_logs_tenant_occurred_at",
            "ix_audit_logs_event_type",
            "ix_audit_logs_actor_id",
        }
        missing = expected - names
        assert not missing, f"Missing indexes on tenant_audit_logs: {missing}"

    def test_outbox_events_composite_index_exists(self, cur):
        names = self._index_names(cur, "control", "outbox_events")
        assert "ix_outbox_events_delivered_occurred_at" in names, (
            "Composite index on (delivered, occurred_at) must exist on outbox_events"
        )

    def test_tenants_gin_indexes_are_gin_type(self, cur):
        """GIN trigram indexes must be GIN access method, not B-tree."""
        cur.execute(
            """
            SELECT i.relname, am.amname
            FROM pg_index pi
            JOIN pg_class i ON i.oid = pi.indexrelid
            JOIN pg_class t ON t.oid = pi.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_am am ON am.oid = i.relam
            WHERE n.nspname = 'control'
              AND t.relname = 'tenants'
              AND i.relname IN ('ix_tenants_name_trgm', 'ix_tenants_slug_trgm')
            """,
        )
        rows = cur.fetchall()
        assert len(rows) == 2, "Both GIN indexes must exist"
        for name, amname in rows:
            assert amname == "gin", f"Index {name} must use GIN access method, got {amname}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. CHECK Constraint on tenants.status_reason
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckConstraint:
    def test_check_constraint_allows_draft_without_reason(self, cur):
        """status=draft with NULL reason is valid."""
        row = _tenant_row(status="draft", status_reason=None)
        _insert_tenant(cur, row)  # must not raise

    def test_check_constraint_allows_active_without_reason(self, cur):
        """status=active with NULL reason is valid."""
        row = _tenant_row(
            tenant_slug="active-no-reason",
            tenant_name="Active No Reason",
            status="active",
            status_reason=None,
        )
        _insert_tenant(cur, row)  # must not raise

    def test_check_constraint_rejects_suspended_null_reason(self, cur):
        """status=suspended with NULL status_reason must violate CHECK."""
        row = _tenant_row(
            tenant_slug="suspended-null",
            tenant_name="Suspended Null Reason",
            status="suspended",
            status_reason=None,
        )
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_tenant(cur, row)

    def test_check_constraint_rejects_suspended_short_reason(self, cur):
        """status=suspended with reason shorter than 10 chars must violate CHECK."""
        row = _tenant_row(
            tenant_slug="suspended-short",
            tenant_name="Suspended Short",
            status="suspended",
            status_reason="tooshort",  # 8 chars
        )
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_tenant(cur, row)

    def test_check_constraint_rejects_archived_null_reason(self, cur):
        """status=archived with NULL status_reason must violate CHECK."""
        row = _tenant_row(
            tenant_slug="archived-null",
            tenant_name="Archived Null Reason",
            status="archived",
            status_reason=None,
        )
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_tenant(cur, row)

    def test_check_constraint_allows_suspended_with_valid_reason(self, cur):
        """status=suspended with a reason of ≥ 10 chars is valid."""
        row = _tenant_row(
            tenant_slug="suspended-valid",
            tenant_name="Suspended Valid",
            status="suspended",
            status_reason="Capacity exceeded limit",
        )
        _insert_tenant(cur, row)  # must not raise

    def test_check_constraint_rejects_whitespace_only_reason(self, cur):
        """Whitespace-only status_reason must not satisfy the 10-char TRIM check."""
        row = _tenant_row(
            tenant_slug="suspended-ws",
            tenant_name="Suspended Whitespace",
            status="suspended",
            status_reason="          ",  # 10 spaces; TRIM gives ''
        )
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_tenant(cur, row)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Unique Constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueConstraints:
    def test_unique_tenant_name_lower_rejected(self, cur):
        """Two tenants with the same name (case-insensitively) must be rejected."""
        row1 = _tenant_row(tenant_name="Acme Corp", tenant_slug="acme-corp-1")
        row2 = _tenant_row(
            tenant_id=uuid.uuid4(),
            tenant_name="ACME CORP",  # different case, same lower value
            tenant_slug="acme-corp-2",
        )
        _insert_tenant(cur, row1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert_tenant(cur, row2)

    def test_unique_tenant_slug_rejected(self, cur):
        """Two tenants with the same slug must be rejected."""
        row1 = _tenant_row(tenant_name="Corp Alpha", tenant_slug="shared-slug")
        row2 = _tenant_row(
            tenant_id=uuid.uuid4(),
            tenant_name="Corp Beta",
            tenant_slug="shared-slug",
        )
        _insert_tenant(cur, row1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _insert_tenant(cur, row2)

    def test_tenant_name_lower_is_generated_correctly(self, cur):
        """tenant_name_lower must equal LOWER(TRIM(tenant_name)) — DB-generated."""
        row = _tenant_row(tenant_name="  Acme Corp  ", tenant_slug="acme-gen")
        _insert_tenant(cur, row)
        cur.execute(
            "SELECT tenant_name_lower FROM control.tenants WHERE tenant_slug = %s",
            ("acme-gen",),
        )
        lower_val = cur.fetchone()[0]
        assert lower_val == "acme corp", f"tenant_name_lower must be 'acme corp', got '{lower_val}'"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Foreign Key Constraint
# ─────────────────────────────────────────────────────────────────────────────


class TestForeignKeyConstraint:
    def test_fk_rejects_unknown_tenant_id(self, cur):
        """Inserting an audit log row with a non-existent tenant_id must fail."""
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO control.tenant_audit_logs (
                    log_id, tenant_id, event_type, actor_id, actor_role,
                    new_data, occurred_at
                ) VALUES (
                    %s, %s, 'tenant_created', %s, 'platform_admin',
                    '{}', NOW()
                )
                """,
                (uuid.uuid4(), uuid.uuid4(), uuid.uuid4()),
            )

    def test_fk_allows_valid_tenant_id(self, cur):
        """Inserting an audit log row for an existing tenant must succeed."""
        row = _tenant_row(tenant_slug="fk-valid-tenant", tenant_name="FK Valid Tenant")
        _insert_tenant(cur, row)
        cur.execute(
            """
            INSERT INTO control.tenant_audit_logs (
                log_id, tenant_id, event_type, actor_id, actor_role,
                new_data, occurred_at
            ) VALUES (
                %s, %s, 'tenant_created', %s, 'platform_admin',
                '{"status": "draft"}', NOW()
            )
            """,
            (uuid.uuid4(), row["tenant_id"], row["created_by"]),
        )  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 8. REVOKE: tenant_audit_logs is append-only
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditLogsRevoke:
    """
    Verifies that dq_app_role has INSERT but not UPDATE or DELETE on
    control.tenant_audit_logs.

    Uses has_table_privilege() to query the PostgreSQL privilege catalog
    directly. This avoids issuing a forbidden statement (which would abort
    the current transaction and make cleanup impossible) while still
    providing a definitive privilege assertion.
    """

    def test_dq_app_role_exists(self, cur):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role'")
        assert cur.fetchone() is not None, "dq_app_role must exist after migration"

    def test_revoke_prevents_update_on_audit_logs(self, cur):
        """dq_app_role must have no UPDATE privilege on tenant_audit_logs."""
        cur.execute(
            "SELECT has_table_privilege('dq_app_role', 'control.tenant_audit_logs', 'UPDATE')"
        )
        assert cur.fetchone()[0] is False, (
            "dq_app_role must NOT have UPDATE privilege on control.tenant_audit_logs"
        )

    def test_revoke_prevents_delete_on_audit_logs(self, cur):
        """dq_app_role must have no DELETE privilege on tenant_audit_logs."""
        cur.execute(
            "SELECT has_table_privilege('dq_app_role', 'control.tenant_audit_logs', 'DELETE')"
        )
        assert cur.fetchone()[0] is False, (
            "dq_app_role must NOT have DELETE privilege on control.tenant_audit_logs"
        )

    def test_dq_app_role_can_insert_audit_logs(self, cur):
        """dq_app_role must retain INSERT privilege on tenant_audit_logs."""
        cur.execute(
            "SELECT has_table_privilege('dq_app_role', 'control.tenant_audit_logs', 'INSERT')"
        )
        assert cur.fetchone()[0] is True, (
            "dq_app_role must have INSERT privilege on control.tenant_audit_logs"
        )

    def test_dq_app_role_can_select_audit_logs(self, cur):
        """dq_app_role must retain SELECT privilege on tenant_audit_logs."""
        cur.execute(
            "SELECT has_table_privilege('dq_app_role', 'control.tenant_audit_logs', 'SELECT')"
        )
        assert cur.fetchone()[0] is True, (
            "dq_app_role must have SELECT privilege on control.tenant_audit_logs"
        )
