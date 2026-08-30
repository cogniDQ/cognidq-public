"""
Integration tests — F005 Packet 1: Database Schema and Migration

These tests verify that migration 010_f005_datasets.sql has been
applied correctly. They connect directly to the PostgreSQL database using
psycopg2 and validate every structural and constraint guarantee required by
the packet plan acceptance criteria (TDD §2, §13).

Test IDs: SCH-01 through SCH-13

Run after applying the migration:
    pytest backend/tests/integration/test_f005_p01_schema.py -v

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


def _new_dataset(
    cur,
    workspace_id,
    tenant_id,
    data_source_id,
    *,
    name=None,
    physical_id=None,
    dataset_type="table",
    status=None,
):
    ds_id = uuid.uuid4()
    actor = uuid.uuid4()
    ds_name = name or f"Dataset {ds_id}"
    phys_id = physical_id or f"schema.{ds_name.lower().replace(' ', '_')}"
    cur.execute(
        """
        INSERT INTO control.datasets (
            dataset_id, workspace_id, tenant_id, data_source_id,
            dataset_name, dataset_type, physical_identifier,
            created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (ds_id, workspace_id, tenant_id, data_source_id, ds_name, dataset_type, phys_id, actor),
    )
    if status and status != "draft":
        cur.execute(
            "UPDATE control.datasets SET status = %s WHERE dataset_id = %s",
            (status, ds_id),
        )
    return ds_id


def _new_field(cur, dataset_id, *, name=None, ordinal=1):
    fid = uuid.uuid4()
    fname = name or f"field_{fid}"
    cur.execute(
        """
        INSERT INTO control.dataset_fields (
            field_id, dataset_id, field_name, data_type, ordinal_position
        ) VALUES (%s, %s, %s, 'varchar', %s)
        """,
        (fid, dataset_id, fname, ordinal),
    )
    return fid


# ─────────────────────────────────────────────────────────────────────────────
# SCH-01: control.datasets table exists with all 21 columns and correct types
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetsTableStructure:
    """AC-P01-001"""

    def test_table_exists_in_control_schema(self, cur):
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'control' AND table_name = 'datasets'
            """
        )
        assert cur.fetchone() is not None, "control.datasets table not found"

    def test_all_required_columns_present(self, cur):
        cols = _columns(cur, "control", "datasets")
        expected = {
            "dataset_id",
            "workspace_id",
            "tenant_id",
            "data_source_id",
            "dataset_name",
            "dataset_type",
            "physical_identifier",
            "schema_name",
            "description",
            "business_domain",
            "criticality",
            "owner_user_id",
            "freshness_expectation",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "activated_at",
            "archived_at",
            "archived_by",
        }
        missing = expected - set(cols.keys())
        assert not missing, f"Missing columns: {sorted(missing)}"

    def test_column_types(self, cur):
        cols = _columns(cur, "control", "datasets")
        assert cols["dataset_id"]["data_type"] == "uuid"
        assert cols["workspace_id"]["data_type"] == "uuid"
        assert cols["tenant_id"]["data_type"] == "uuid"
        assert cols["data_source_id"]["data_type"] == "uuid"
        assert cols["dataset_name"]["data_type"] == "character varying"
        assert cols["dataset_type"]["data_type"] == "character varying"
        assert cols["physical_identifier"]["data_type"] == "character varying"
        assert cols["schema_name"]["data_type"] == "character varying"
        assert cols["description"]["data_type"] == "character varying"
        assert cols["business_domain"]["data_type"] == "character varying"
        assert cols["criticality"]["data_type"] == "character varying"
        assert cols["owner_user_id"]["data_type"] == "uuid"
        assert cols["freshness_expectation"]["data_type"] == "character varying"
        assert cols["status"]["data_type"] == "character varying"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["updated_at"]["data_type"] == "timestamp with time zone"
        assert cols["created_by"]["data_type"] == "uuid"
        assert cols["updated_by"]["data_type"] == "uuid"
        assert cols["activated_at"]["data_type"] == "timestamp with time zone"
        assert cols["archived_at"]["data_type"] == "timestamp with time zone"
        assert cols["archived_by"]["data_type"] == "uuid"


# ─────────────────────────────────────────────────────────────────────────────
# SCH-02: control.dataset_fields table exists with all 11 columns
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetFieldsTableStructure:
    """AC-P01-002"""

    def test_table_exists_in_control_schema(self, cur):
        cur.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'control' AND table_name = 'dataset_fields'
            """
        )
        assert cur.fetchone() is not None, "control.dataset_fields table not found"

    def test_all_required_columns_present(self, cur):
        cols = _columns(cur, "control", "dataset_fields")
        expected = {
            "field_id",
            "dataset_id",
            "field_name",
            "data_type",
            "nullable",
            "business_definition",
            "sensitivity_classification",
            "is_key_candidate",
            "ordinal_position",
            "created_at",
            "updated_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, f"Missing columns: {sorted(missing)}"

    def test_column_types(self, cur):
        cols = _columns(cur, "control", "dataset_fields")
        assert cols["field_id"]["data_type"] == "uuid"
        assert cols["dataset_id"]["data_type"] == "uuid"
        assert cols["field_name"]["data_type"] == "character varying"
        assert cols["data_type"]["data_type"] == "character varying"
        assert cols["nullable"]["data_type"] == "boolean"
        assert cols["business_definition"]["data_type"] == "character varying"
        assert cols["sensitivity_classification"]["data_type"] == "character varying"
        assert cols["is_key_candidate"]["data_type"] == "boolean"
        assert cols["ordinal_position"]["data_type"] == "integer"
        assert cols["created_at"]["data_type"] == "timestamp with time zone"
        assert cols["updated_at"]["data_type"] == "timestamp with time zone"

    def test_nullable_columns(self, cur):
        cols = _columns(cur, "control", "dataset_fields")
        for col in [
            "field_id",
            "dataset_id",
            "field_name",
            "data_type",
            "nullable",
            "sensitivity_classification",
            "is_key_candidate",
            "ordinal_position",
            "created_at",
            "updated_at",
        ]:
            assert cols[col]["nullable"] == "NO", f"{col} should be NOT NULL"
        assert cols["business_definition"]["nullable"] == "YES", (
            "business_definition should be NULLABLE"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-03: PRIMARY KEY constraints on both tables
# ─────────────────────────────────────────────────────────────────────────────


class TestPrimaryKeyConstraints:
    """AC-P01-003"""

    def test_datasets_pk_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'datasets'
              AND constraint_type = 'PRIMARY KEY'
            """
        )
        row = cur.fetchone()
        assert row is not None, "PK not found on datasets"
        assert row[0] == "pk_datasets"

    def test_dataset_fields_pk_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'dataset_fields'
              AND constraint_type = 'PRIMARY KEY'
            """
        )
        row = cur.fetchone()
        assert row is not None, "PK not found on dataset_fields"
        assert row[0] == "pk_dataset_fields"

    def test_duplicate_dataset_pk_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO control.datasets (
                    dataset_id, workspace_id, tenant_id, data_source_id,
                    dataset_name, dataset_type, physical_identifier, created_by
                ) VALUES (%s, %s, %s, %s, 'Dup', 'table', 'dup.tbl', %s)
                """,
                (ds_id, wid, tid, src_id, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-04: UNIQUE index on (workspace_id, lower(dataset_name))
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueDatasetNamePerWorkspace:
    """AC-P01-004"""

    def test_unique_name_index_exists(self, cur):
        indexes = _indexes(cur, "control", "datasets")
        assert "uq_dataset_name_workspace" in indexes

    def test_duplicate_name_same_workspace_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(cur, wid, tid, src_id, name="Sales Data")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_dataset(cur, wid, tid, src_id, name="Sales Data", physical_id="other.sales_data_2")

    def test_duplicate_name_case_insensitive_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(cur, wid, tid, src_id, name="sales-data")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_dataset(cur, wid, tid, src_id, name="SALES-DATA", physical_id="other.sales_data_2")

    def test_same_name_different_workspace_allowed(self, cur):
        tid = _new_tenant(cur)
        wid1 = _new_workspace(cur, tid)
        wid2 = _new_workspace(cur, tid)
        src_id1 = _new_data_source(cur, wid1, tid)
        src_id2 = _new_data_source(cur, wid2, tid)
        _new_dataset(cur, wid1, tid, src_id1, name="shared-name")
        _new_dataset(cur, wid2, tid, src_id2, name="shared-name")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# SCH-05: Partial UNIQUE index on (data_source_id, lower(physical_identifier))
# ─────────────────────────────────────────────────────────────────────────────


class TestUniquePhysicalIdentifierPerSource:
    """AC-P01-005"""

    def test_partial_unique_index_exists(self, cur):
        indexes = _indexes(cur, "control", "datasets")
        assert "uq_dataset_physical_id_source" in indexes

    def test_duplicate_physical_id_same_source_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(cur, wid, tid, src_id, name="DS1", physical_id="public.orders")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_dataset(cur, wid, tid, src_id, name="DS2", physical_id="public.orders")

    def test_duplicate_physical_id_case_insensitive_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(cur, wid, tid, src_id, name="DS1", physical_id="public.Orders")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_dataset(cur, wid, tid, src_id, name="DS2", physical_id="PUBLIC.ORDERS")

    def test_same_physical_id_archived_allowed(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(
            cur, wid, tid, src_id, name="DS1", physical_id="public.orders", status="archived"
        )
        # New dataset with same physical_id should be allowed since old is archived
        _new_dataset(cur, wid, tid, src_id, name="DS2", physical_id="public.orders")

    def test_same_physical_id_different_source_allowed(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id1 = _new_data_source(cur, wid, tid, name="Source A")
        src_id2 = _new_data_source(cur, wid, tid, name="Source B")
        _new_dataset(cur, wid, tid, src_id1, name="DS1", physical_id="public.orders")
        _new_dataset(
            cur, wid, tid, src_id2, name="DS2", physical_id="public.orders"
        )  # different source — allowed


# ─────────────────────────────────────────────────────────────────────────────
# SCH-06: UNIQUE index on (dataset_id, lower(field_name))
# ─────────────────────────────────────────────────────────────────────────────


class TestUniqueFieldNamePerDataset:
    """AC-P01-006"""

    def test_unique_field_name_index_exists(self, cur):
        indexes = _indexes(cur, "control", "dataset_fields")
        assert "uq_field_name_dataset" in indexes

    def test_duplicate_field_name_same_dataset_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        _new_field(cur, ds_id, name="customer_id", ordinal=1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_field(cur, ds_id, name="customer_id", ordinal=2)

    def test_duplicate_field_name_case_insensitive_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        _new_field(cur, ds_id, name="customer_id", ordinal=1)
        with pytest.raises(psycopg2.errors.UniqueViolation):
            _new_field(cur, ds_id, name="CUSTOMER_ID", ordinal=2)

    def test_same_field_name_different_dataset_allowed(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id1 = _new_dataset(cur, wid, tid, src_id, name="DS1", physical_id="t1")
        ds_id2 = _new_dataset(cur, wid, tid, src_id, name="DS2", physical_id="t2")
        _new_field(cur, ds_id1, name="customer_id", ordinal=1)
        _new_field(cur, ds_id2, name="customer_id", ordinal=1)  # different dataset — allowed


# ─────────────────────────────────────────────────────────────────────────────
# SCH-07: CHECK constraint on dataset_type
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetTypeCheckConstraint:
    """AC-P01-007"""

    def test_valid_dataset_types_accepted(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        for i, dtype in enumerate(("table", "view", "file", "logical")):
            _new_dataset(
                cur,
                wid,
                tid,
                src_id,
                name=f"ds-{dtype}",
                physical_id=f"s.{dtype}_{i}",
                dataset_type=dtype,
            )

    def test_invalid_dataset_type_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            _new_dataset(
                cur, wid, tid, src_id, name="bad", physical_id="s.bad", dataset_type="stream"
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-08: status defaults to 'draft'
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusDefault:
    """AC-P01-008"""

    def test_status_defaults_to_draft(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        cur.execute(
            "SELECT status FROM control.datasets WHERE dataset_id = %s",
            (ds_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "draft"

    def test_invalid_status_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.datasets (
                    dataset_id, workspace_id, tenant_id, data_source_id,
                    dataset_name, dataset_type, physical_identifier,
                    created_by, status
                ) VALUES (%s, %s, %s, %s, 'Bad', 'table', 's.bad', %s, 'deleted')
                """,
                (uuid.uuid4(), wid, tid, src_id, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-09: criticality defaults to 'low'
# ─────────────────────────────────────────────────────────────────────────────


class TestCriticalityDefault:
    """AC-P01-009"""

    def test_criticality_defaults_to_low(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        cur.execute(
            "SELECT criticality FROM control.datasets WHERE dataset_id = %s",
            (ds_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "low"

    def test_invalid_criticality_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.datasets (
                    dataset_id, workspace_id, tenant_id, data_source_id,
                    dataset_name, dataset_type, physical_identifier,
                    created_by, criticality
                ) VALUES (%s, %s, %s, %s, 'Bad', 'table', 's.bad', %s, 'extreme')
                """,
                (uuid.uuid4(), wid, tid, src_id, uuid.uuid4()),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-10: sensitivity_classification defaults to 'internal'
# ─────────────────────────────────────────────────────────────────────────────


class TestSensitivityDefault:
    """AC-P01-010"""

    def test_sensitivity_defaults_to_internal(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        fid = _new_field(cur, ds_id, name="col1", ordinal=1)
        cur.execute(
            "SELECT sensitivity_classification FROM control.dataset_fields WHERE field_id = %s",
            (fid,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "internal"

    def test_valid_sensitivity_values_accepted(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        for i, sc in enumerate(("public", "internal", "confidential", "restricted")):
            fid = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO control.dataset_fields (
                    field_id, dataset_id, field_name, data_type,
                    ordinal_position, sensitivity_classification
                ) VALUES (%s, %s, %s, 'varchar', %s, %s)
                """,
                (fid, ds_id, f"col_{sc}", i + 1, sc),
            )

    def test_invalid_sensitivity_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO control.dataset_fields (
                    field_id, dataset_id, field_name, data_type,
                    ordinal_position, sensitivity_classification
                ) VALUES (%s, %s, 'bad_col', 'varchar', 1, 'top_secret')
                """,
                (uuid.uuid4(), ds_id),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-11: FK datasets.data_source_id → data_sources RESTRICT on delete
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceForeignKey:
    """AC-P01-011"""

    def test_fk_data_source_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'datasets'
              AND constraint_type = 'FOREIGN KEY'
              AND constraint_name = 'fk_datasets_data_source'
            """
        )
        assert cur.fetchone() is not None, "FK fk_datasets_data_source not found"

    def test_nonexistent_data_source_rejected(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        fake_src = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                """
                INSERT INTO control.datasets (
                    dataset_id, workspace_id, tenant_id, data_source_id,
                    dataset_name, dataset_type, physical_identifier, created_by
                ) VALUES (%s, %s, %s, %s, 'Orphan', 'table', 's.orphan', %s)
                """,
                (uuid.uuid4(), wid, tid, fake_src, uuid.uuid4()),
            )

    def test_delete_data_source_with_datasets_restricted(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        _new_dataset(cur, wid, tid, src_id)
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute(
                "DELETE FROM control.data_sources WHERE data_source_id = %s",
                (src_id,),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SCH-12: FK dataset_fields.dataset_id → datasets CASCADE on delete
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetFieldsCascadeDelete:
    """AC-P01-012"""

    def test_fk_dataset_fields_dataset_exists(self, cur):
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'control'
              AND table_name = 'dataset_fields'
              AND constraint_type = 'FOREIGN KEY'
              AND constraint_name = 'fk_dataset_fields_dataset'
            """
        )
        assert cur.fetchone() is not None, "FK fk_dataset_fields_dataset not found"

    def test_fields_cascade_on_dataset_delete(self, cur):
        tid = _new_tenant(cur)
        wid = _new_workspace(cur, tid)
        src_id = _new_data_source(cur, wid, tid)
        ds_id = _new_dataset(cur, wid, tid, src_id)
        fid = _new_field(cur, ds_id, name="col1", ordinal=1)

        # Verify field exists
        cur.execute(
            "SELECT field_id FROM control.dataset_fields WHERE field_id = %s",
            (fid,),
        )
        assert cur.fetchone() is not None, "Field should exist before delete"

        # Delete the dataset — fields should cascade
        cur.execute(
            "DELETE FROM control.datasets WHERE dataset_id = %s",
            (ds_id,),
        )
        cur.execute(
            "SELECT field_id FROM control.dataset_fields WHERE field_id = %s",
            (fid,),
        )
        assert cur.fetchone() is None, "Field should be CASCADE deleted with dataset"

    def test_orphan_field_rejected(self, cur):
        fake_ds_id = uuid.uuid4()
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _new_field(cur, fake_ds_id, name="orphan", ordinal=1)


# ─────────────────────────────────────────────────────────────────────────────
# SCH-13: All declared indexes exist in pg_indexes
# ─────────────────────────────────────────────────────────────────────────────


class TestIndexesExist:
    """AC-P01-013"""

    def test_datasets_indexes_exist(self, cur):
        indexes = _indexes(cur, "control", "datasets")
        expected = {
            "pk_datasets",
            "uq_dataset_name_workspace",
            "uq_dataset_physical_id_source",
            "idx_datasets_workspace",
            "idx_datasets_data_source",
            "idx_datasets_status",
            "idx_datasets_owner",
            "idx_datasets_business_domain",
            "idx_datasets_criticality",
            "idx_datasets_tenant",
            "idx_datasets_type",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on datasets: {sorted(missing)}"

    def test_dataset_fields_indexes_exist(self, cur):
        indexes = _indexes(cur, "control", "dataset_fields")
        expected = {
            "pk_dataset_fields",
            "uq_field_name_dataset",
            "idx_dataset_fields_dataset",
        }
        missing = expected - indexes
        assert not missing, f"Missing indexes on dataset_fields: {sorted(missing)}"
