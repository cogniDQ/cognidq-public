"""
Integration tests — F005 P02: DatasetRepository

Tests CRUD operations on control.datasets using a live database.

Test IDs: REPO-01 through REPO-10
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
    DatasetNotFoundError,
    DuplicateDatasetNameError,
    DuplicatePhysicalIdentifierError,
)
from app.services.datasets.models import (
    Dataset,
    DatasetListFilters,
    DatasetStatus,
)
from app.services.datasets.repository import DatasetRepository

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
    connection.execute(text("SAVEPOINT sp_ds_repo_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    connection.execute(text("ROLLBACK TO SAVEPOINT sp_ds_repo_test"))
    transaction.rollback()
    connection.close()


@pytest.fixture()
def repo():
    return DatasetRepository()


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


def _make_dataset(
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    data_source_id: uuid.UUID,
    *,
    name: str = "test-dataset",
    dtype: str = "table",
    physical_id: str = "public.test_table",
) -> Dataset:
    now = datetime.now(UTC)
    return Dataset(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        dataset_name=name,
        dataset_type=dtype,
        physical_identifier=physical_id,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# REPO-01: insert
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryInsert:
    """REPO-01"""

    def test_insert_returns_domain_model(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        ds = _make_dataset(wid, tid, dsid)
        result = repo.insert(db, ds)

        assert result.dataset_id is not None
        assert result.dataset_name == "test-dataset"
        assert result.status == DatasetStatus.draft
        assert result.criticality == "low"
        assert result.created_at is not None

    def test_duplicate_name_raises(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        repo.insert(db, _make_dataset(wid, tid, dsid, name="dup-name", physical_id="tab1"))
        with pytest.raises(DuplicateDatasetNameError):
            repo.insert(db, _make_dataset(wid, tid, dsid, name="DUP-NAME", physical_id="tab2"))

    def test_duplicate_physical_id_raises(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        repo.insert(db, _make_dataset(wid, tid, dsid, name="a1", physical_id="public.orders"))
        with pytest.raises(DuplicatePhysicalIdentifierError):
            repo.insert(db, _make_dataset(wid, tid, dsid, name="a2", physical_id="Public.Orders"))

    def test_same_name_different_workspace_ok(self, db, repo):
        tid = _new_tenant(db)
        wid1 = _new_workspace(db, tid)
        wid2 = _new_workspace(db, tid)
        dsid1 = _new_data_source(db, wid1, tid)
        dsid2 = _new_data_source(db, wid2, tid)

        repo.insert(db, _make_dataset(wid1, tid, dsid1, name="shared"))
        result = repo.insert(db, _make_dataset(wid2, tid, dsid2, name="shared"))
        assert result.dataset_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# REPO-02: find_by_id
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryFindById:
    """REPO-02"""

    def test_find_existing(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        found = repo.find_by_id(db, workspace_id=wid, dataset_id=created.dataset_id)
        assert found is not None
        assert found.dataset_name == "test-dataset"

    def test_find_nonexistent_returns_none(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        result = repo.find_by_id(db, workspace_id=wid, dataset_id=uuid.uuid4())
        assert result is None

    def test_cross_workspace_isolation(self, db, repo):
        tid = _new_tenant(db)
        wid1 = _new_workspace(db, tid)
        wid2 = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid1, tid)
        created = repo.insert(db, _make_dataset(wid1, tid, dsid))

        result = repo.find_by_id(db, workspace_id=wid2, dataset_id=created.dataset_id)
        assert result is None

    def test_find_for_update(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        found = repo.find_by_id_for_update(db, workspace_id=wid, dataset_id=created.dataset_id)
        assert found is not None
        assert found.dataset_id == created.dataset_id


# ─────────────────────────────────────────────────────────────────────────────
# REPO-03: list_datasets
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryList:
    """REPO-03"""

    def test_list_returns_items_and_count(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        for i in range(3):
            repo.insert(db, _make_dataset(wid, tid, dsid, name=f"ds-{i}", physical_id=f"t{i}"))

        result = repo.list_datasets(db, workspace_id=wid, filters=DatasetListFilters())
        assert len(result.items) == 3
        assert result.total_count == 3

    def test_list_filter_by_status(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, name="draft-ds", physical_id="t_d"))

        result = repo.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(status="draft"),
        )
        assert result.total_count >= 1
        assert all(i.status == "draft" for i in result.items)

    def test_list_filter_by_search(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, name="orders_fact", physical_id="p.orders"))
        repo.insert(db, _make_dataset(wid, tid, dsid, name="users_dim", physical_id="p.users"))

        result = repo.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(search="orders"),
        )
        assert result.total_count >= 1
        assert any("orders" in i.dataset_name.lower() for i in result.items)

    def test_list_pagination(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        for i in range(5):
            repo.insert(db, _make_dataset(wid, tid, dsid, name=f"p-{i}", physical_id=f"pt{i}"))

        page1 = repo.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(limit=2, offset=0),
        )
        page2 = repo.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(limit=2, offset=2),
        )
        assert len(page1.items) == 2
        assert len(page2.items) == 2
        assert page1.total_count == 5

    def test_list_includes_data_source_name(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid))

        result = repo.list_datasets(db, workspace_id=wid, filters=DatasetListFilters())
        assert result.items[0].data_source_name is not None


# ─────────────────────────────────────────────────────────────────────────────
# REPO-04: update
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryUpdate:
    """REPO-04"""

    def test_update_metadata(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        created.dataset_name = "updated-name"
        created.description = "new desc"
        created.updated_by = uuid.uuid4()
        updated = repo.update(db, created)

        assert updated.dataset_name == "updated-name"
        assert updated.description == "new desc"
        assert updated.updated_at > created.created_at

    def test_update_nonexistent_raises(self, db, repo):
        ds = Dataset(
            dataset_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            data_source_id=uuid.uuid4(),
            dataset_name="ghost",
            dataset_type="table",
            physical_identifier="ghost.table",
            created_by=uuid.uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with pytest.raises(DatasetNotFoundError):
            repo.update(db, ds)

    def test_update_duplicate_name_raises(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, name="taken-name", physical_id="t1"))
        ds2 = repo.insert(db, _make_dataset(wid, tid, dsid, name="other-name", physical_id="t2"))

        ds2.dataset_name = "taken-name"
        ds2.updated_by = uuid.uuid4()
        with pytest.raises(DuplicateDatasetNameError):
            repo.update(db, ds2)


# ─────────────────────────────────────────────────────────────────────────────
# REPO-05: update_status
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryUpdateStatus:
    """REPO-05"""

    def test_transition_draft_to_active(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        now = datetime.now(UTC)
        updated = repo.update_status(
            db,
            dataset_id=created.dataset_id,
            workspace_id=wid,
            new_status="active",
            actor_id=uuid.uuid4(),
            activated_at=now,
        )
        assert updated.status == DatasetStatus.active
        assert updated.activated_at is not None

    def test_transition_to_archived(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        now = datetime.now(UTC)
        actor = uuid.uuid4()
        repo.update_status(
            db,
            dataset_id=created.dataset_id,
            workspace_id=wid,
            new_status="active",
            actor_id=actor,
            activated_at=now,
        )
        archived = repo.update_status(
            db,
            dataset_id=created.dataset_id,
            workspace_id=wid,
            new_status="archived",
            actor_id=actor,
            archived_at=now,
            archived_by=actor,
        )
        assert archived.status == DatasetStatus.archived
        assert archived.archived_at is not None
        assert archived.archived_by is not None

    def test_update_status_nonexistent_raises(self, db, repo):
        with pytest.raises(DatasetNotFoundError):
            repo.update_status(
                db,
                dataset_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                new_status="active",
                actor_id=uuid.uuid4(),
            )


# ─────────────────────────────────────────────────────────────────────────────
# REPO-06: check_name_exists
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryCheckName:
    """REPO-06"""

    def test_name_exists(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, name="unique-name"))

        assert repo.check_name_exists(db, workspace_id=wid, dataset_name="unique-name") is True
        assert repo.check_name_exists(db, workspace_id=wid, dataset_name="UNIQUE-NAME") is True

    def test_name_not_exists(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        assert repo.check_name_exists(db, workspace_id=wid, dataset_name="no-such") is False

    def test_exclude_id(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid, name="self-check"))

        assert (
            repo.check_name_exists(
                db,
                workspace_id=wid,
                dataset_name="self-check",
                exclude_id=created.dataset_id,
            )
            is False
        )


# ─────────────────────────────────────────────────────────────────────────────
# REPO-07: check_physical_id_exists
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryCheckPhysicalId:
    """REPO-07"""

    def test_physical_id_exists(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, physical_id="public.orders"))

        assert (
            repo.check_physical_id_exists(
                db,
                data_source_id=dsid,
                physical_identifier="public.orders",
            )
            is True
        )

    def test_case_insensitive(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        repo.insert(db, _make_dataset(wid, tid, dsid, physical_id="public.orders"))

        assert (
            repo.check_physical_id_exists(
                db,
                data_source_id=dsid,
                physical_identifier="Public.Orders",
            )
            is True
        )

    def test_archived_excluded(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid, physical_id="old.table"))

        # Archive it
        now = datetime.now(UTC)
        actor = uuid.uuid4()
        repo.update_status(
            db,
            dataset_id=created.dataset_id,
            workspace_id=wid,
            new_status="archived",
            actor_id=actor,
            archived_at=now,
            archived_by=actor,
        )

        assert (
            repo.check_physical_id_exists(
                db,
                data_source_id=dsid,
                physical_identifier="old.table",
            )
            is False
        )


# ─────────────────────────────────────────────────────────────────────────────
# REPO-08: count_by_data_source
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetRepositoryCountByDataSource:
    """REPO-08"""

    def test_count_non_archived(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        for i in range(3):
            repo.insert(db, _make_dataset(wid, tid, dsid, name=f"c-{i}", physical_id=f"ct{i}"))

        count = repo.count_by_data_source(db, data_source_id=dsid)
        assert count == 3

    def test_count_excludes_archived(self, db, repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = repo.insert(db, _make_dataset(wid, tid, dsid))

        now = datetime.now(UTC)
        actor = uuid.uuid4()
        repo.update_status(
            db,
            dataset_id=created.dataset_id,
            workspace_id=wid,
            new_status="archived",
            actor_id=actor,
            archived_at=now,
            archived_by=actor,
        )

        count = repo.count_by_data_source(db, data_source_id=dsid)
        assert count == 0
