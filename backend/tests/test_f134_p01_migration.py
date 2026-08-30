"""
F134 P01 — DB Migration Tests
=============================================
Tests for 040_f134_demo_sandbox_schema.sql migration.

Tests verify:
1. Migration file exists and is syntactically complete (BEGIN/COMMIT)
2. All four enum types are defined with correct values
3. control.tenants gains tenant_type column and CHECK constraint
4. seed_source columns added on asset tables
5. sandbox_admin added to workspace_role_assignments CHECK constraint
6. All eight new tables are created with expected columns
7. sandbox_usage_events is partitioned (PARTITION BY RANGE)
8. Seed rows inserted for demo_templates and access_profiles
9. All expected indexes are defined
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
    "040_f134_demo_sandbox_schema.sql",
)


def _sql() -> str:
    with open(MIGRATION_PATH, encoding="utf-8") as fh:
        return fh.read()


# ──────────────────────────────────────────────────────
# 1. File-level assertions
# ──────────────────────────────────────────────────────


class TestMigrationFile:
    def test_file_exists(self):
        assert os.path.isfile(MIGRATION_PATH), f"Migration file not found: {MIGRATION_PATH}"

    def test_wrapped_in_transaction(self):
        sql = _sql()
        assert re.search(r"\bBEGIN\b", sql, re.IGNORECASE), "Missing BEGIN"
        assert re.search(r"\bCOMMIT\b", sql, re.IGNORECASE), "Missing COMMIT"

    def test_uses_idempotent_create_table(self):
        sql = _sql()
        all_creates = re.findall(
            r"CREATE TABLE\s+(IF NOT EXISTS\s+)?control\.\w+",
            sql,
            re.IGNORECASE,
        )
        for match in all_creates:
            assert "IF NOT EXISTS" in match.upper(), (
                f"CREATE TABLE missing IF NOT EXISTS guard: {match}"
            )


# ──────────────────────────────────────────────────────
# 2. Enum types
# ──────────────────────────────────────────────────────


class TestEnumTypes:
    def test_demo_request_status_enum_defined(self):
        sql = _sql()
        assert "demo_request_status" in sql
        assert "submitted" in sql
        assert "under_review" in sql
        assert "provisioned" in sql
        assert "converted" in sql

    def test_sandbox_environment_status_enum_defined(self):
        sql = _sql()
        assert "sandbox_environment_status" in sql
        assert "provisioning_failed" in sql
        assert "suspended" in sql
        assert "archived" in sql

    def test_provisioning_job_status_enum_defined(self):
        sql = _sql()
        assert "provisioning_job_status" in sql
        assert re.search(r"\bpending\b", sql), "Missing 'pending' in provisioning_job_status"
        assert re.search(r"\brunning\b", sql), "Missing 'running' in provisioning_job_status"
        assert re.search(r"\bsucceeded\b", sql), "Missing 'succeeded' in provisioning_job_status"
        assert re.search(r"\bfailed\b", sql), "Missing 'failed' in provisioning_job_status"

    def test_sandbox_usage_event_type_enum_defined(self):
        sql = _sql()
        assert "sandbox_usage_event_type" in sql
        for expected in (
            "login",
            "page_view",
            "check_executed",
            "rule_created",
            "onboarding_step_completed",
            "invitation_accepted",
            "extension_requested",
        ):
            assert expected in sql, f"Missing usage event type: {expected}"

    def test_enums_use_idempotent_do_guard(self):
        """Each enum type must be guarded by a DO $$ IF NOT EXISTS block."""
        sql = _sql()
        for enum_name in (
            "demo_request_status",
            "sandbox_environment_status",
            "provisioning_job_status",
            "sandbox_usage_event_type",
        ):
            # Verify the enum is created inside a DO $$ guard
            pattern = rf"DO \$\$.*?{re.escape(enum_name)}.*?CREATE TYPE.*?{re.escape(enum_name)}"
            assert re.search(pattern, sql, re.DOTALL | re.IGNORECASE), (
                f"Enum '{enum_name}' must be created inside an idempotent DO $$ guard"
            )


# ──────────────────────────────────────────────────────
# 3. control.tenants modification
# ──────────────────────────────────────────────────────


class TestTenantsModification:
    def test_tenant_type_column_added(self):
        sql = _sql()
        assert re.search(
            r"ALTER TABLE control\.tenants.*?ADD COLUMN.*?tenant_type",
            sql,
            re.DOTALL | re.IGNORECASE,
        ), "Missing: ADD COLUMN tenant_type on control.tenants"

    def test_tenant_type_has_default_customer(self):
        sql = _sql()
        assert "DEFAULT 'customer'" in sql, "tenant_type column must have DEFAULT 'customer'"

    def test_tenant_type_check_constraint(self):
        sql = _sql()
        assert "ck_tenants_tenant_type" in sql, (
            "Missing CHECK constraint ck_tenants_tenant_type on control.tenants"
        )
        assert "'sandbox'" in sql, "CHECK constraint must include 'sandbox'"
        assert "'internal'" in sql, "CHECK constraint must include 'internal'"

    def test_backfill_existing_rows(self):
        sql = _sql()
        assert re.search(
            r"UPDATE control\.tenants\s+SET\s+tenant_type\s*=\s*'customer'",
            sql,
            re.IGNORECASE,
        ), "Missing backfill UPDATE on control.tenants"


# ──────────────────────────────────────────────────────
# 4. seed_source columns on asset tables
# ──────────────────────────────────────────────────────


class TestSeedSourceColumns:
    def test_seed_source_on_data_sources(self):
        sql = _sql()
        assert re.search(
            r"control\.data_sources.*?seed_source",
            sql,
            re.DOTALL | re.IGNORECASE,
        ), "Missing seed_source column on control.data_sources"

    def test_seed_source_on_metadata_term_index(self):
        sql = _sql()
        assert re.search(
            r"metadata_term_index.*?seed_source",
            sql,
            re.DOTALL | re.IGNORECASE,
        ), "Missing seed_source column on metadata_term_index"


# ──────────────────────────────────────────────────────
# 5. workspace_role_assignments — sandbox_admin added
# ──────────────────────────────────────────────────────


class TestWorkspaceRoleAssignmentsUpdate:
    def test_sandbox_admin_added_to_check_constraint(self):
        sql = _sql()
        assert "sandbox_admin" in sql, (
            "sandbox_admin role must be added to ck_wra_role_name CHECK constraint"
        )

    def test_constraint_drop_and_recreate(self):
        sql = _sql()
        assert re.search(
            r"DROP CONSTRAINT.*?ck_wra_role_name",
            sql,
            re.IGNORECASE | re.DOTALL,
        ), "Old ck_wra_role_name constraint must be dropped before recreating"
        assert re.search(
            r"ADD CONSTRAINT ck_wra_role_name",
            sql,
            re.IGNORECASE,
        ), "New ck_wra_role_name constraint must be added"

    def test_all_original_roles_preserved(self):
        sql = _sql()
        for role in (
            "workspace_administrator",
            "data_engineer",
            "data_steward",
            "business_analyst",
            "governance_viewer",
        ):
            assert role in sql, f"Original role '{role}' must be preserved in ck_wra_role_name"


# ──────────────────────────────────────────────────────
# 6. New tables
# ──────────────────────────────────────────────────────


class TestNewTables:
    def test_demo_templates_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.demo_templates",
            sql,
            re.IGNORECASE,
        )
        assert "seeder_module" in sql
        assert "default_duration_days" in sql

    def test_access_profiles_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.access_profiles",
            sql,
            re.IGNORECASE,
        )
        assert "uq_access_profiles_code" in sql
        assert "flags" in sql

    def test_demo_requests_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.demo_requests",
            sql,
            re.IGNORECASE,
        )
        assert "public_status_token" in sql
        assert "work_email" in sql
        assert "uq_demo_requests_public_status_token" in sql
        assert "chk_demo_requests_consent" in sql

    def test_sandbox_environments_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.sandbox_environments",
            sql,
            re.IGNORECASE,
        )
        assert "demo_request_id" in sql
        assert "access_profile_id" in sql
        assert "uq_sandbox_env_demo_request" in sql
        assert "chk_sandbox_env_extension_count" in sql

    def test_sandbox_users_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.sandbox_users",
            sql,
            re.IGNORECASE,
        )
        assert "invitation_token_hash" in sql

    def test_sandbox_extensions_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.sandbox_extensions",
            sql,
            re.IGNORECASE,
        )
        assert "extension_days" in sql
        assert "previous_expires_at" in sql

    def test_provisioning_jobs_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.provisioning_jobs",
            sql,
            re.IGNORECASE,
        )
        assert "celery_task_id" in sql
        assert "attempt_count" in sql

    def test_sandbox_usage_events_table(self):
        sql = _sql()
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS control\.sandbox_usage_events",
            sql,
            re.IGNORECASE,
        )

    def test_sandbox_usage_events_is_partitioned(self):
        sql = _sql()
        assert re.search(
            r"PARTITION BY RANGE\s*\(\s*occurred_at\s*\)",
            sql,
            re.IGNORECASE,
        ), "sandbox_usage_events must be range-partitioned on occurred_at"

    def test_usage_events_partition_created(self):
        sql = _sql()
        # The migration creates monthly partitions via a DO $$ loop
        assert re.search(
            r"PARTITION OF control\.sandbox_usage_events",
            sql,
            re.IGNORECASE,
        ), "At least one partition of sandbox_usage_events must be created"


# ──────────────────────────────────────────────────────
# 7. Seed rows
# ──────────────────────────────────────────────────────


class TestSeedRows:
    def test_general_dq_template_seeded(self):
        sql = _sql()
        assert re.search(
            r"INSERT INTO control\.demo_templates",
            sql,
            re.IGNORECASE,
        ), "Missing INSERT into control.demo_templates"
        assert "general_dq" in sql
        assert "ON CONFLICT (id) DO NOTHING" in sql

    def test_mvp_default_access_profile_seeded(self):
        sql = _sql()
        assert re.search(
            r"INSERT INTO control\.access_profiles",
            sql,
            re.IGNORECASE,
        ), "Missing INSERT into control.access_profiles"
        assert "mvp_default" in sql
        assert "ON CONFLICT (code) DO NOTHING" in sql


# ──────────────────────────────────────────────────────
# 8. Indexes
# ──────────────────────────────────────────────────────


class TestIndexes:
    def test_demo_requests_status_index(self):
        assert "ix_demo_requests_status" in _sql()

    def test_demo_requests_created_at_index(self):
        assert "ix_demo_requests_created_at" in _sql()

    def test_demo_requests_email_partial_index(self):
        sql = _sql()
        assert "ix_demo_requests_email_active" in sql
        # Must be partial — WHERE clause required
        assert re.search(
            r"ix_demo_requests_email_active.*?WHERE",
            sql,
            re.DOTALL | re.IGNORECASE,
        ), "ix_demo_requests_email_active must be a partial index (WHERE clause)"

    def test_sandbox_env_status_index(self):
        assert "ix_sandbox_env_status" in _sql()

    def test_sandbox_env_tenant_index(self):
        assert "ix_sandbox_env_tenant" in _sql()

    def test_sandbox_env_expires_at_partial_index(self):
        sql = _sql()
        assert "ix_sandbox_env_expires_at" in sql
        assert re.search(
            r"ix_sandbox_env_expires_at.*?WHERE",
            sql,
            re.DOTALL | re.IGNORECASE,
        ), "ix_sandbox_env_expires_at must be a partial index (WHERE clause)"

    def test_sandbox_users_sandbox_index(self):
        assert "ix_sandbox_users_sandbox" in _sql()

    def test_provisioning_jobs_indexes(self):
        sql = _sql()
        assert "ix_provisioning_jobs_demo_request" in sql
        assert "ix_provisioning_jobs_status" in sql

    def test_all_indexes_use_if_not_exists(self):
        sql = _sql()
        for idx_name in (
            "ix_demo_requests_status",
            "ix_demo_requests_created_at",
            "ix_demo_requests_email_active",
            "ix_sandbox_env_status",
            "ix_sandbox_env_tenant",
            "ix_sandbox_env_expires_at",
            "ix_sandbox_users_sandbox",
            "ix_sandbox_users_user",
            "ix_sandbox_extensions_sandbox",
            "ix_provisioning_jobs_demo_request",
            "ix_provisioning_jobs_status",
        ):
            pattern = rf"CREATE INDEX IF NOT EXISTS {idx_name}"
            assert re.search(pattern, sql, re.IGNORECASE), (
                f"Index '{idx_name}' must use CREATE INDEX IF NOT EXISTS"
            )
