"""
Integration tests — F005 P02: DatasetFieldRepository

Tests CRUD operations on control.dataset_fields using a live database.

Test IDs: FREPO-01 through FREPO-09
"""

import os
import uuid
from datetime import UTC, datetime, timezone

import psycopg2
import psycopg2.extras
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

psycopg2.extras.register_uuid()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

from app.services.datasets.errors import (
    DatasetFieldNotFoundError,
    DuplicateFieldNameError,
)
from app.services.datasets.field_repository import DatasetFieldRepository
from app.services.datasets.models import DatasetField

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    return create_engine(DATABASE_URL)


@pytest.fixture()
def db(engine):
    """Per-test session with SAVEPOINT rollback for isolation."""
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text("SAVEPOINT sp_frepo_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    connection.execute(text("ROLLBACK TO SAVEPOINT sp_frepo_test"))
    transaction.rollback()
    connection.close()


@pytest.fixture()
def repo():
    return DatasetFieldRepository()


def _new_tenant(db: Session) -> uuid.UUID:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version, created_at, updated_at
            ) VALUES (
                :tid, :name, :slug, 'active', 'eu-west', 'starter',
                :actor, :actor, 0, NOW(), NOW()
            )
        """),
        {"tid": str(tid), "name": f"T {tid}", "slug": f"t-{str(tid)[:8]}", "actor": str(actor)},
    )
    return tid


def _new_workspace(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS {wid}"
    db.execute(
        text("""
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, default_timezone, status,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                :wid, :tid, :name, :name_lower, :slug, 'UTC', 'active',
                NOW(), NOW(), :actor, :actor, 0
            )
        """),
        {
            "wid": str(wid),
            "tid": str(tenant_id),
            "name": name,
            "name_lower": name.lower(),
            "slug": f"ws-{str(wid)[:8]}",
            "actor": str(actor),
        },
    )
    return wid


def _new_data_source(db: Session, workspace_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    dsid = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO control.data_sources (
                data_source_id, workspace_id, tenant_id,
                source_name, source_type, connection_mode, environment,
                status, last_test_status,
                created_at, updated_at, created_by
            ) VALUES (
                :dsid, :wid, :tid,
                :name, 'postgresql', 'direct', 'production',
                'active', 'untested',
                NOW(), NOW(), :actor
            )
        """),
        {
            "dsid": str(dsid),
            "wid": str(workspace_id),
            "tid": str(tenant_id),
            "name": f"DS {dsid}",
            "actor": str(uuid.uuid4()),
        },
    )
    return dsid


def _new_dataset(
    db: Session, workspace_id: uuid.UUID, tenant_id: uuid.UUID, data_source_id: uuid.UUID
) -> uuid.UUID:
    did = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO control.datasets (
                dataset_id, workspace_id, tenant_id, data_source_id,
                dataset_name, dataset_type, physical_identifier,
                status, created_at, updated_at, created_by
            ) VALUES (
                :did, :wid, :tid, :dsid,
                :name, 'table', :phys,
                'draft', NOW(), NOW(), :actor
            )
        """),
        {
            "did": str(did),
            "wid": str(workspace_id),
            "tid": str(tenant_id),
            "dsid": str(data_source_id),
            "name": f"Dataset {did}",
            "phys": f"schema.table_{str(did)[:8]}",
            "actor": str(uuid.uuid4()),
        },
    )
    return did


def _make_field(
    dataset_id: uuid.UUID,
    *,
    name: str = "col1",
    data_type: str = "integer",
    ordinal: int = 1,
) -> DatasetField:
    now = datetime.now(UTC)
    return DatasetField(
        dataset_id=dataset_id,
        field_name=name,
        data_type=data_type,
        ordinal_position=ordinal,
        created_at=now,
        updated_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scaffolding fixture for tests that need a dataset
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def dataset_id(db):
    tid = _new_tenant(db)
    wid = _new_workspace(db, tid)
    dsid = _new_data_source(db, wid, tid)
    return _new_dataset(db, wid, tid, dsid)


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-01: insert
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryInsert:
    """FREPO-01"""

    def test_insert_returns_field(self, db, repo, dataset_id):
        f = _make_field(dataset_id)
        result = repo.insert(db, f)

        assert result.field_id is not None
        assert result.field_name == "col1"
        assert result.data_type == "integer"
        assert result.ordinal_position == 1
        assert result.nullable is True
        assert result.sensitivity_classification == "internal"
        assert result.is_key_candidate is False

    def test_duplicate_field_name_raises(self, db, repo, dataset_id):
        repo.insert(db, _make_field(dataset_id, name="dup_col", ordinal=1))
        with pytest.raises(DuplicateFieldNameError):
            repo.insert(db, _make_field(dataset_id, name="DUP_COL", ordinal=2))

    def test_same_name_different_dataset_ok(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        did1 = _new_dataset(db, wid, tid, dsid)
        did2 = _new_dataset(db, wid, tid, dsid)

        repo.insert(db, _make_field(did1, name="shared_col"))
        result = repo.insert(db, _make_field(did2, name="shared_col"))
        assert result.field_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-02: find_by_id
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryFindById:
    """FREPO-02"""

    def test_find_existing(self, db, repo, dataset_id):
        created = repo.insert(db, _make_field(dataset_id))
        found = repo.find_by_id(db, dataset_id=dataset_id, field_id=created.field_id)
        assert found is not None
        assert found.field_name == "col1"

    def test_nonexistent_returns_none(self, db, repo, dataset_id):
        result = repo.find_by_id(db, dataset_id=dataset_id, field_id=uuid.uuid4())
        assert result is None

    def test_wrong_dataset_returns_none(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        did1 = _new_dataset(db, wid, tid, dsid)
        did2 = _new_dataset(db, wid, tid, dsid)
        created = repo.insert(db, _make_field(did1))

        result = repo.find_by_id(db, dataset_id=did2, field_id=created.field_id)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-03: find_all_by_dataset
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryFindAll:
    """FREPO-03"""

    def test_returns_ordered_by_ordinal(self, db, repo, dataset_id):
        repo.insert(db, _make_field(dataset_id, name="c3", ordinal=3))
        repo.insert(db, _make_field(dataset_id, name="c1", ordinal=1))
        repo.insert(db, _make_field(dataset_id, name="c2", ordinal=2))

        fields = repo.find_all_by_dataset(db, dataset_id=dataset_id)
        assert len(fields) == 3
        assert [f.ordinal_position for f in fields] == [1, 2, 3]

    def test_empty_dataset_returns_empty_list(self, db, repo, dataset_id):
        fields = repo.find_all_by_dataset(db, dataset_id=dataset_id)
        assert fields == []


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-04: update
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryUpdate:
    """FREPO-04"""

    def test_update_data_type(self, db, repo, dataset_id):
        created = repo.insert(db, _make_field(dataset_id))
        created.data_type = "bigint"
        updated = repo.update(db, created)
        assert updated.data_type == "bigint"
        assert updated.updated_at >= created.created_at

    def test_update_nonexistent_raises(self, db, repo, dataset_id):
        f = DatasetField(
            field_id=uuid.uuid4(),
            dataset_id=dataset_id,
            field_name="ghost",
            data_type="int",
            ordinal_position=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with pytest.raises(DatasetFieldNotFoundError):
            repo.update(db, f)


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-05: delete
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryDelete:
    """FREPO-05"""

    def test_delete_existing(self, db, repo, dataset_id):
        created = repo.insert(db, _make_field(dataset_id))
        result = repo.delete(db, dataset_id=dataset_id, field_id=created.field_id)
        assert result is True

        found = repo.find_by_id(db, dataset_id=dataset_id, field_id=created.field_id)
        assert found is None

    def test_delete_nonexistent_returns_false(self, db, repo, dataset_id):
        result = repo.delete(db, dataset_id=dataset_id, field_id=uuid.uuid4())
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-06: delete_all_by_dataset
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryDeleteAll:
    """FREPO-06"""

    def test_delete_all(self, db, repo, dataset_id):
        for i in range(3):
            repo.insert(db, _make_field(dataset_id, name=f"f{i}", ordinal=i + 1))

        count = repo.delete_all_by_dataset(db, dataset_id=dataset_id)
        assert count == 3
        assert repo.count_by_dataset(db, dataset_id=dataset_id) == 0

    def test_delete_all_empty_returns_zero(self, db, repo, dataset_id):
        count = repo.delete_all_by_dataset(db, dataset_id=dataset_id)
        assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-07: count_by_dataset / max_ordinal
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryCountAndOrdinal:
    """FREPO-07"""

    def test_count(self, db, repo, dataset_id):
        for i in range(4):
            repo.insert(db, _make_field(dataset_id, name=f"c{i}", ordinal=i + 1))
        assert repo.count_by_dataset(db, dataset_id=dataset_id) == 4

    def test_count_empty(self, db, repo, dataset_id):
        assert repo.count_by_dataset(db, dataset_id=dataset_id) == 0

    def test_max_ordinal(self, db, repo, dataset_id):
        repo.insert(db, _make_field(dataset_id, name="a", ordinal=5))
        repo.insert(db, _make_field(dataset_id, name="b", ordinal=10))
        assert repo.max_ordinal(db, dataset_id=dataset_id) == 10

    def test_max_ordinal_empty(self, db, repo, dataset_id):
        assert repo.max_ordinal(db, dataset_id=dataset_id) == 0


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-08: check_name_exists
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryCheckName:
    """FREPO-08"""

    def test_name_exists(self, db, repo, dataset_id):
        repo.insert(db, _make_field(dataset_id, name="order_id"))
        assert repo.check_name_exists(db, dataset_id=dataset_id, field_name="order_id") is True
        assert repo.check_name_exists(db, dataset_id=dataset_id, field_name="ORDER_ID") is True

    def test_name_not_exists(self, db, repo, dataset_id):
        assert repo.check_name_exists(db, dataset_id=dataset_id, field_name="nope") is False

    def test_exclude_id(self, db, repo, dataset_id):
        created = repo.insert(db, _make_field(dataset_id, name="self_ref"))
        assert (
            repo.check_name_exists(
                db,
                dataset_id=dataset_id,
                field_name="self_ref",
                exclude_id=created.field_id,
            )
            is False
        )


# ─────────────────────────────────────────────────────────────────────────────
# FREPO-09: bulk_insert
# ─────────────────────────────────────────────────────────────────────────────


class TestFieldRepositoryBulkInsert:
    """FREPO-09"""

    def test_bulk_insert(self, db, repo, dataset_id):
        fields = [_make_field(dataset_id, name=f"bulk_{i}", ordinal=i + 1) for i in range(5)]
        result = repo.bulk_insert(db, fields)
        assert len(result) == 5
        assert all(f.field_id is not None for f in result)

    def test_bulk_insert_duplicate_raises(self, db, repo, dataset_id):
        repo.insert(db, _make_field(dataset_id, name="existing", ordinal=1))
        fields = [
            _make_field(dataset_id, name="existing", ordinal=2),
        ]
        with pytest.raises(DuplicateFieldNameError):
            repo.bulk_insert(db, fields)
