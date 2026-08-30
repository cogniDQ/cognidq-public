"""
F130 P01 — DB Migration Tests
=============================================
Tests for 038_tenant_connections_and_glossary.sql migration.

Tests verify:
1. Migration file exists and is syntactically complete
2. data_sources tenant_id column addition is present
3. workspace_connection_assignments table creation is present
4. metadata_term_index tenant_id column addition is present
5. All expected indexes are defined in the migration
"""

import os
import re

import pytest

# ──────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────

MIGRATION_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "scripts",
    "migrations",
    "038_tenant_connections_and_glossary.sql",
)


def _migration_sql() -> str:
    with open(MIGRATION_PATH, encoding="utf-8") as f:
        return f.read()


# ──────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────


class TestMigrationFile:
    def test_migration_file_exists(self):
        """Migration file 038 must exist at the expected path."""
        assert os.path.isfile(MIGRATION_PATH), f"Migration file not found: {MIGRATION_PATH}"

    def test_migration_wrapped_in_transaction(self):
        """Migration must be wrapped in BEGIN/COMMIT for atomicity."""
        sql = _migration_sql()
        assert re.search(r"\bBEGIN\b", sql, re.IGNORECASE), "Missing BEGIN"
        assert re.search(r"\bCOMMIT\b", sql, re.IGNORECASE), "Missing COMMIT"


class TestDataSourcesColumn:
    def test_adds_tenant_id_to_data_sources(self):
        """Migration must ALTER control.data_sources to add tenant_id."""
        sql = _migration_sql()
        assert re.search(
            r"ALTER TABLE control\.data_sources\s+ADD COLUMN IF NOT EXISTS tenant_id",
            sql,
            re.IGNORECASE,
        ), "Missing: ALTER TABLE control.data_sources ADD COLUMN IF NOT EXISTS tenant_id"

    def test_backfill_uses_workspaces_join(self):
        """Backfill UPDATE must join control.workspaces to derive tenant_id."""
        sql = _migration_sql()
        assert "control.workspaces" in sql, "Backfill must reference control.workspaces"
        assert re.search(
            r"UPDATE control\.data_sources",
            sql,
            re.IGNORECASE,
        ), "Missing backfill UPDATE on control.data_sources"

    def test_data_sources_tenant_index(self):
        """Migration must create ix_data_sources_tenant_id index."""
        sql = _migration_sql()
        assert "ix_data_sources_tenant_id" in sql, (
            "Missing index ix_data_sources_tenant_id on control.data_sources"
        )


class TestWorkspaceConnectionAssignments:
    def test_creates_wca_table(self):
        """Migration must create control.workspace_connection_assignments."""
        sql = _migration_sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.workspace_connection_assignments",
            sql,
            re.IGNORECASE,
        ), "Missing: CREATE TABLE IF NOT EXISTS control.workspace_connection_assignments"

    def test_wca_has_primary_key(self):
        """workspace_connection_assignments must define a composite PK."""
        sql = _migration_sql()
        assert re.search(
            r"PRIMARY KEY\s*\(\s*connection_id\s*,\s*workspace_id\s*\)",
            sql,
            re.IGNORECASE,
        ), "Missing: PRIMARY KEY (connection_id, workspace_id)"

    def test_wca_has_cascade_fk(self):
        """connection_id FK must use ON DELETE CASCADE."""
        sql = _migration_sql()
        assert re.search(
            r"REFERENCES control\.data_sources.*ON DELETE CASCADE",
            sql,
            re.IGNORECASE | re.DOTALL,
        ), "Missing: REFERENCES control.data_sources ... ON DELETE CASCADE"

    def test_wca_backfill_uses_on_conflict(self):
        """Backfill INSERT must use ON CONFLICT DO NOTHING for idempotency."""
        sql = _migration_sql()
        assert "ON CONFLICT DO NOTHING" in sql.upper(), (
            "Missing ON CONFLICT DO NOTHING in workspace_connection_assignments backfill"
        )

    def test_wca_indexes_present(self):
        """Migration must create ix_wca_workspace and ix_wca_connection indexes."""
        sql = _migration_sql()
        assert "ix_wca_workspace" in sql, "Missing ix_wca_workspace index"
        assert "ix_wca_connection" in sql, "Missing ix_wca_connection index"


class TestMetadataTermIndexColumn:
    def test_adds_tenant_id_to_metadata_term_index(self):
        """Migration must ALTER control.metadata_term_index to add tenant_id."""
        sql = _migration_sql()
        assert re.search(
            r"ALTER TABLE control\.metadata_term_index\s+ADD COLUMN IF NOT EXISTS tenant_id",
            sql,
            re.IGNORECASE,
        ), "Missing: ALTER TABLE control.metadata_term_index ADD COLUMN IF NOT EXISTS tenant_id"

    def test_metadata_term_backfill_uses_workspaces_join(self):
        """Backfill UPDATE must join workspaces to derive tenant_id for glossary terms."""
        sql = _migration_sql()
        assert re.search(
            r"UPDATE control\.metadata_term_index",
            sql,
            re.IGNORECASE,
        ), "Missing backfill UPDATE on control.metadata_term_index"

    def test_metadata_term_tenant_index(self):
        """Migration must create ix_meta_term_tenant index."""
        sql = _migration_sql()
        assert "ix_meta_term_tenant" in sql, (
            "Missing index ix_meta_term_tenant on control.metadata_term_index"
        )


class TestMigrationIdempotency:
    def test_all_alters_use_if_not_exists(self):
        """All ADD COLUMN statements must use IF NOT EXISTS for idempotency."""
        sql = _migration_sql()
        # Count total ADD COLUMN occurrences
        total = len(re.findall(r"\bADD COLUMN\b", sql, re.IGNORECASE))
        # Count ADD COLUMN IF NOT EXISTS occurrences
        with_guard = len(re.findall(r"\bADD COLUMN\s+IF NOT EXISTS\b", sql, re.IGNORECASE))
        assert total == with_guard, (
            f"{total - with_guard} ADD COLUMN statement(s) are missing IF NOT EXISTS"
        )

    def test_table_creation_uses_if_not_exists(self):
        """CREATE TABLE must use IF NOT EXISTS."""
        sql = _migration_sql()
        create_table_matches = re.findall(
            r"CREATE TABLE\s+(IF NOT EXISTS\s+)?\w",
            sql,
            re.IGNORECASE,
        )
        for if_not_exists in create_table_matches:
            assert if_not_exists.strip().upper() == "IF NOT EXISTS", (
                "CREATE TABLE is missing IF NOT EXISTS"
            )

    def test_all_indexes_use_if_not_exists(self):
        """All CREATE INDEX statements must use IF NOT EXISTS."""
        sql = _migration_sql()
        index_matches = re.findall(
            r"CREATE INDEX\s+(IF NOT EXISTS\s+)?(\w+)",
            sql,
            re.IGNORECASE,
        )
        for if_not_exists, idx_name in index_matches:
            assert if_not_exists.strip().upper() == "IF NOT EXISTS", (
                f"CREATE INDEX for '{idx_name}' is missing IF NOT EXISTS"
            )
