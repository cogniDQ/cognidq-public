"""
Integration tests — F004 Packet 1: Database Schema and Migration

These tests verify that migration 009_f004_data_sources.sql has been
applied correctly. They connect directly to the PostgreSQL database using
psycopg2 and validate every structural and constraint guarantee required by
the packet plan acceptance criteria (TDD §3.1, §3.2).

Test IDs: SCH-01 through SCH-12

Run after applying the migration:
    pytest backend/tests/integration/test_f004_p01_schema.py -v

Environment variable:
    DATABASE_URL  (e.g. postgresql://postgres:postgres@localhost:5432/dq_db)
    Defaults to the Docker Compose default if not set.
"""

import os
import uuid

import psycopg2
import psycopg2.errors
import psycopg2.extras
import pytest

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
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


def _new_workspace(cur, tenant_id):
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
            %s, %s, %s, %s, %s, NULL, 'UTC', 'active', NULL,
            NOW(), NOW(), %s, %s, 0
        )
        """,
        (wid, tenant_id, name, name.lower(), f"ws-{str(wid)[:8]}", actor, actor),
    )
    return wid


def _new_data_source(cur, workspace_id, tenant_id, *, name=None):
    """Insert a minimal valid data source and return its data_source_id."""
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    src_name = name or f"Source {ds_id}"
    cur.execute(
        """
        INSERT INTO control.data_sources (
            data_source_id, workspace_id, tenant_id,
            source_name, source_type, connection_mode, environment,
            created_by
        ) VALUES (%s, %s, %s, %s, 'postgresql', 'direct', 'development', %s)
        """,
        (ds_id, workspace_id, tenant_id, src_name, actor),
    )
    return ds_id


def _new_credential(cur, data_source_id, *, payload=b"encrypted_blob"):
    """Insert a minimal credential row and return its credential_id."""
    cred_id = uuid.uuid4()
    actor = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.data_source_credentials (
            credential_id, data_source_id, source_type, encrypted_payload, created_by
        ) VALUES (%s, %s, 'postgresql', %s, %s)
        """,
        (cred_id, data_source_id, payload, actor),
    )
    return cred_id


# ─────────────────────────────────────────────────────────────────────────────
# SCH-01: control.data_sources table exists with all required columns
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourcesTableStructure:
    """SCH-01"""

    def test_table_exists_in_control_schema(self, cur):
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'control' AND table_name = 'data_sources'
            """
        )
        assert cur.fetchone() is not None, "control.data_sources table not found"

    def test_all_required_columns_present(self, cur):
        cols = _columns(cur, "control", "data_sources")
        expected = {
            "data_source_id",
            "workspace_id",
            "tenant_id",
            "source_name",
            "source_type",
            "connection_mode",
            "environment",
            "description",
            "credential_reference",
            "status",
            "last_test_status",
            "last_tested_at",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "archived_at",
            "archived_by",
        }
        missing = expected - set(cols.keys())
        assert not missing, f"Missing columns: {sorted(missing)}"

    def test_column_types(self, cur):
        cols = _columns(cur, "control", "data_sources")
        assert cols["data_source_id"]["data_type"] == "uuid"
        assert cols["workspace_id"]["data_type"] == "uuid"
        assert cols["tenant_id"]["data_type"] == "uuid"
        assert cols["source_name"]["data_type"] == "character varying"
        assert cols["source_type"]["data_type"] == "character varying"
        assert cols["connection_mode"]["data_type"] == "character varying"
        assert cols["environment"]["data_type"] == "character varying"
        assert cols["description"]["data_type"] == "character varying"
        assert cols["credential_reference"]["data_type"] == "uuid"
        assert cols["status"]["data_type"] == "character varying"
        assert cols["last_test_status"]["data_type"] == "character varying"
        assert cols["last_tested_at"]["data_type"] == "timestamp with time zone"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["updated_at"]["data_type"] == "timestamp with time zone"
        assert cols["created_by"]["data_type"] == "uuid"
        assert cols["archived_at"]["data_type"] == "timestamp with time zone"
        assert cols["archived_by"]["data_type"] == "uuid"


# ─────────────────────────────────────────────────────────────────────────────
# SCH-02: control.data_source_credentials table exists with all required columns
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceCredentialsTableStructure:
    """SCH-02"""

    def test_credentials_table_exists(self, cur):
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'control' AND table_name = 'data_source_credentials'
            """
        )
        assert cur.fetchone() is not None, "control.data_source_credentials table not found"

    def test_credentials_all_columns_present(self, cur):
        cols = _columns(cur, "control", "data_source_credentials")
        expected = {
            "credential_id",
            "data_source_id",
            "source_type",
            "encrypted_payload",
            "created_at",
            "created_by",
            "superseded_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, f"Missing columns: {sorted(missing)}"

    def test_credentials_column_types(self, cur):
        cols = _columns(cur, "control", "data_source_credentials")
        assert cols["credential_id"]["data_type"] == "uuid"
        assert cols["data_source_id"]["data_type"] == "uuid"
        assert cols["source_type"]["data_type"] == "character varying"
        assert cols["encrypted_payload"]["data_type"] == "bytea"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["created_by"]["data_type"] == "uuid"
        assert cols["superseded_at"]["data_type"] == "timestamp with time zone"

    def test_credentials_nullable_columns(self, cur):
        cols = _columns(cur, "control", "data_source_credentials")
        for col in [
            "credential_id",
            "data_source_id",
            "source_type",
            "encrypted_payload",
            "created_at",
            "created_by",
        ]:
            assert cols[col]["nullable"] == "NO", f"{col} should be NOT NULL"
        assert cols["superseded_at"]["nullable"] == "YES", "superseded_at should be NULLABLE"


# ─────────────────────────────────────────────────────────────────────────────
# SCH-03: PRIMARY KEY constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestPrimaryKeyConstraints:
    """SCH-03"""

    def test_data_sources_pk_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'data_sources'
              AND constraint_type = 'PRIMARY KEY'
            """
        )
        row = cur.fetchone()
        assert row is not None, "PK not found on data_sources"
        assert row[0] == "pk_data_sources"

    def test_credentials_pk_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'data_source_credentials'
              AND constraint_type = 'PRIMARY KEY'
            """
        )
        row = cur.fetchone()
        assert row is not None, "PK not found on data_source_credentials"
        assert row[0] == "pk_data_source_credentials"

    def test_duplicate_data_source_pk_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        ds_id = _new_data_source(cur, wid, tid)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, 'Duplicate', 'postgresql', 'direct', 'development', %s)
                """,
                (ds_id, wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-04: UNIQUE index on (workspace_id, lower(source_name)) is enforced
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueNamePerWorkspace:
    """SCH-04"""

    def test_unique_name_index_exists(self, cur):
        indexes = _indexes(cur, "control", "data_sources")
        assert "uq_data_source_name_workspace" in indexes

    def test_duplicate_name_same_workspace_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        _new_data_source(cur, wid, tid, name="My PostgreSQL Source")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_data_source(cur, wid, tid, name="My PostgreSQL Source")

    def test_duplicate_name_case_insensitive_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        _new_data_source(cur, wid, tid, name="prod-db")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_data_source(cur, wid, tid, name="PROD-DB")

    def test_same_name_different_workspace_allowed(self, cur):
        tid = _new_tenant(cur)
        wid1 = _new_workspace(cur, tid)
        wid2 = _new_workspace(cur, tid)
        _new_data_source(cur, wid1, tid, name="shared-name")
        _new_data_source(cur, wid2, tid, name="shared-name")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# SCH-05: CHECK on source_type rejects invalid value
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceTypeCheckConstraint:
    """SCH-05"""

    def test_valid_source_types_accepted(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        actor = uuid.uuid4()
        for stype in ("postgresql", "mysql", "mssql", "oracle", "snowflake", "bigquery"):
            ds_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, %s, %s, 'direct', 'development', %s)
                """,
                (ds_id, wid, tid, f"src-{stype}", stype, actor),
            )

    def test_invalid_source_type_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, 'Bad', 'mongodb', 'direct', 'development', %s)
                """,
                (uuid.uuid4(), wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-06: CHECK on connection_mode rejects invalid value
# ─────────────────────────────────────────────────────────────────────────────


class TestConnectionModeCheckConstraint:
    """SCH-06"""

    def test_invalid_connection_mode_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, 'SomeSrc', 'postgresql', 'tunnel', 'development', %s)
                """,
                (uuid.uuid4(), wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-07: CHECK on environment rejects invalid value
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvironmentCheckConstraint:
    """SCH-07"""

    def test_invalid_environment_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, 'SomeSrc', 'postgresql', 'direct', 'disaster-recovery', %s)
                """,
                (uuid.uuid4(), wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-08: status defaults to 'active'
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusDefault:
    """SCH-08"""

    def test_status_defaults_to_active(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        ds_id = _new_data_source(cur, wid, tid)
        cur.execute(
            "SELECT status FROM control.data_sources WHERE data_source_id = %s",
            (ds_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "active"

    def test_invalid_status_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment,
                    created_by, status
                ) VALUES (%s, %s, %s, 'Src', 'postgresql', 'direct', 'development', %s, 'deleted')
                """,
                (uuid.uuid4(), wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-09: last_test_status defaults to 'untested'
# ─────────────────────────────────────────────────────────────────────────────


class TestLastTestStatusDefault:
    """SCH-09"""

    def test_last_test_status_defaults_to_untested(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        ds_id = _new_data_source(cur, wid, tid)
        cur.execute(
            "SELECT last_test_status FROM control.data_sources WHERE data_source_id = %s",
            (ds_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "untested"

    def test_invalid_test_status_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment,
                    created_by, last_test_status
                ) VALUES (%s, %s, %s, 'Src', 'postgresql', 'direct', 'development', %s, 'pending')
                """,
                (uuid.uuid4(), wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-10: FK workspace_id → workspaces RESTRICT on delete
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceForeignKey:
    """SCH-10"""

    def test_fk_workspace_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'data_sources'
              AND constraint_type = 'FOREIGN KEY'
              AND constraint_name = 'fk_data_sources_workspace'
            """
        )
        assert cur.fetchone() is not None, "FK fk_data_sources_workspace not found"

    def test_nonexistent_workspace_rejected(self, cur):
        tid = _new_tenant(cur)
        fake_wid = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO control.data_sources (
                    data_source_id, workspace_id, tenant_id,
                    source_name, source_type, connection_mode, environment, created_by
                ) VALUES (%s, %s, %s, 'Orphan', 'postgresql', 'direct', 'development', %s)
                """,
                (uuid.uuid4(), fake_wid, tid, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-11: FK data_source_credentials.data_source_id CASCADE on delete
# ─────────────────────────────────────────────────────────────────────────────


class TestCredentialsCascadeDelete:
    """SCH-11"""

    def test_credentials_cascade_on_data_source_delete(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        ds_id = _new_data_source(cur, wid, tid)
        cred_id = _new_credential(cur, ds_id)

        # Verify credential exists
        cur.execute(
            "SELECT credential_id FROM control.data_source_credentials WHERE credential_id = %s",
            (cred_id,),
        )
        assert cur.fetchone() is not None, "Credential should exist before delete"

        # Delete the data source — credential should cascade
        cur.execute(
            "DELETE FROM control.data_sources WHERE data_source_id = %s",
            (ds_id,),
        )
        cur.execute(
            "SELECT credential_id FROM control.data_source_credentials WHERE credential_id = %s",
            (cred_id,),
        )
        assert cur.fetchone() is None, "Credential should be CASCADE deleted with data source"

    def test_orphan_credential_rejected(self, cur):
        fake_ds_id = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _new_credential(cur, fake_ds_id)


# ─────────────────────────────────────────────────────────────────────────────
# SCH-12: All declared indexes exist in pg_indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexesExist:
    """SCH-12"""

    def test_data_sources_indexes_exist(self, cur):
        indexes = _indexes(cur, "control", "data_sources")
        expected = {
            "pk_data_sources",
            "uq_data_source_name_workspace",
            "idx_data_sources_workspace",
            "idx_data_sources_tenant",
            "idx_data_sources_status",
            "idx_data_sources_source_type",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on data_sources: {sorted(missing)}"

    def test_credentials_indexes_exist(self, cur):
        indexes = _indexes(cur, "control", "data_source_credentials")
        expected = {
            "pk_data_source_credentials",
            "idx_ds_credentials_data_source",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on data_source_credentials: {sorted(missing)}"
