"""
Integration tests — F004 P02: DataSource and Credential Repository Layer

Tests CRUD operations on control.data_sources and
control.data_source_credentials using a live database (Docker Compose).

Test IDs: REPO-01 through REPO-10

Environment variable:
    DATABASE_URL — defaults to the Docker Compose default.
"""

import os
import uuid
from datetime import datetime, timezone

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

from app.services.data_sources.credential_repository import (
    CredentialNotFoundError,
    CredentialRepository,
)
from app.services.data_sources.models import DataSourceStatus, TestStatus
from app.services.data_sources.repository import (
    DataSourceArchivedError,
    DataSourceNotFoundError,
    DataSourceRepository,
    DuplicateSourceNameError,
)

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
    connection.execute(text("SAVEPOINT sp_repo_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    connection.execute(text("ROLLBACK TO SAVEPOINT sp_repo_test"))
    transaction.rollback()
    connection.close()


@pytest.fixture()
def ds_repo():
    return DataSourceRepository()


@pytest.fixture()
def cred_repo():
    return CredentialRepository()


def _new_tenant(db: Session) -> uuid.UUID:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    db.execute(
        text(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version, created_at, updated_at
            ) VALUES (
                :tid, :name, :slug, 'active', 'eu-west', 'starter',
                :actor, :actor, 0, NOW(), NOW()
            )
            """
        ),
        {"tid": str(tid), "name": f"T {tid}", "slug": f"t-{str(tid)[:8]}", "actor": str(actor)},
    )
    return tid


def _new_workspace(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS {wid}"
    db.execute(
        text(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, default_timezone, status,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                :wid, :tid, :name, :name_lower, :slug, 'UTC', 'active',
                NOW(), NOW(), :actor, :actor, 0
            )
            """
        ),
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


# ─────────────────────────────────────────────────────────────────────────────
# REPO-01: DataSourceRepository.create inserts a row
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceRepositoryCreate:
    """REPO-01"""

    def test_create_returns_domain_model(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()

        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="prod-pg",
            source_type="postgresql",
            connection_mode="direct",
            environment="production",
            created_by=actor,
        )

        assert ds.data_source_id is not None
        assert ds.source_name == "prod-pg"
        assert ds.status == DataSourceStatus.active
        assert ds.last_test_status == TestStatus.untested
        assert ds.created_at is not None

    def test_duplicate_name_raises_duplicate_error(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="duplicate-name",
            source_type="postgresql",
            connection_mode="direct",
            environment="staging",
            created_by=actor,
        )
        with pytest.raises(DuplicateSourceNameError):
            ds_repo.create(
                db,
                workspace_id=wid,
                tenant_id=tid,
                source_name="duplicate-name",
                source_type="mysql",
                connection_mode="direct",
                environment="staging",
                created_by=actor,
            )


# ─────────────────────────────────────────────────────────────────────────────
# REPO-02: find_by_id
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceRepositoryFindById:
    """REPO-02"""

    def test_find_existing_data_source(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        created = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="find-me",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )

        found = ds_repo.find_by_id(db, data_source_id=created.data_source_id, workspace_id=wid)
        assert found.data_source_id == created.data_source_id
        assert found.source_name == "find-me"

    def test_find_nonexistent_raises_not_found(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        with pytest.raises(DataSourceNotFoundError):
            ds_repo.find_by_id(db, data_source_id=uuid.uuid4(), workspace_id=wid)

    def test_cross_workspace_isolation(self, db, ds_repo):
        """find_by_id should not return a data source from a different workspace."""
        tid = _new_tenant(db)
        wid1 = _new_workspace(db, tid)
        wid2 = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid1,
            tenant_id=tid,
            source_name="isolated",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        with pytest.raises(DataSourceNotFoundError):
            ds_repo.find_by_id(db, data_source_id=ds.data_source_id, workspace_id=wid2)


# ─────────────────────────────────────────────────────────────────────────────
# REPO-03: list
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceRepositoryList:
    """REPO-03"""

    def test_list_returns_items_and_count(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        for i in range(3):
            ds_repo.create(
                db,
                workspace_id=wid,
                tenant_id=tid,
                source_name=f"src-{i}-{uuid.uuid4()}",
                source_type="postgresql",
                connection_mode="direct",
                environment="development",
                created_by=actor,
            )
        items, total = ds_repo.list(db, workspace_id=wid, tenant_id=tid)
        assert total >= 3
        assert len(items) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# REPO-04: update_metadata
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceRepositoryUpdateMetadata:
    """REPO-04"""

    def test_update_source_name(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="original-name",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        ds_repo.update_metadata(
            db,
            data_source_id=ds.data_source_id,
            workspace_id=wid,
            updated_by=actor,
            source_name="renamed",
        )
        updated = ds_repo.find_by_id(db, data_source_id=ds.data_source_id, workspace_id=wid)
        assert updated.source_name == "renamed"


# ─────────────────────────────────────────────────────────────────────────────
# REPO-05: archive and restore
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceRepositoryArchiveRestore:
    """REPO-05"""

    def test_archive_sets_status_to_archived(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="archive-me",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        ds_repo.archive(db, data_source_id=ds.data_source_id, workspace_id=wid, archived_by=actor)
        archived = ds_repo.find_by_id(db, data_source_id=ds.data_source_id, workspace_id=wid)
        assert archived.status == DataSourceStatus.archived
        assert archived.archived_at is not None

    def test_restore_sets_status_to_active(self, db, ds_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="restore-me",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        ds_repo.archive(db, data_source_id=ds.data_source_id, workspace_id=wid, archived_by=actor)
        ds_repo.restore(db, data_source_id=ds.data_source_id, workspace_id=wid, restored_by=actor)
        restored = ds_repo.find_by_id(db, data_source_id=ds.data_source_id, workspace_id=wid)
        assert restored.status == DataSourceStatus.active
        assert restored.archived_at is None


# ─────────────────────────────────────────────────────────────────────────────
# REPO-06: CredentialRepository.create
# ─────────────────────────────────────────────────────────────────────────────


class TestCredentialRepositoryCreate:
    """REPO-06"""

    def test_create_credential(self, db, ds_repo, cred_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="cred-test",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        cred = cred_repo.create(
            db,
            data_source_id=ds.data_source_id,
            source_type="postgresql",
            encrypted_payload=b"encrypted_bytes",
            created_by=actor,
        )
        assert cred.credential_id is not None
        assert cred.encrypted_payload == b"encrypted_bytes"
        assert cred.superseded_at is None


# ─────────────────────────────────────────────────────────────────────────────
# REPO-07: CredentialRepository.find_by_id
# ─────────────────────────────────────────────────────────────────────────────


class TestCredentialRepositoryFindById:
    """REPO-07"""

    def test_find_by_id(self, db, ds_repo, cred_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="find-cred",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        created = cred_repo.create(
            db,
            data_source_id=ds.data_source_id,
            source_type="postgresql",
            encrypted_payload=b"payload123",
            created_by=actor,
        )
        found = cred_repo.find_by_id(db, credential_id=created.credential_id)
        assert found.credential_id == created.credential_id
        assert bytes(found.encrypted_payload) == b"payload123"

    def test_not_found_raises_error(self, db, cred_repo):
        with pytest.raises(CredentialNotFoundError):
            cred_repo.find_by_id(db, credential_id=uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# REPO-08: CredentialRepository.supersede
# ─────────────────────────────────────────────────────────────────────────────


class TestCredentialRepositorySupersede:
    """REPO-08"""

    def test_supersede_sets_superseded_at(self, db, ds_repo, cred_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="supersede-test",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        cred = cred_repo.create(
            db,
            data_source_id=ds.data_source_id,
            source_type="postgresql",
            encrypted_payload=b"old_payload",
            created_by=actor,
        )
        cred_repo.supersede(db, credential_id=cred.credential_id)
        refreshed = cred_repo.find_by_id(db, credential_id=cred.credential_id)
        assert refreshed.superseded_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# REPO-09: cascade delete
# ─────────────────────────────────────────────────────────────────────────────


class TestCascadeDelete:
    """REPO-09"""

    def test_credentials_deleted_when_data_source_deleted(self, db, ds_repo, cred_repo):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="cascade-delete",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        cred = cred_repo.create(
            db,
            data_source_id=ds.data_source_id,
            source_type="postgresql",
            encrypted_payload=b"payload",
            created_by=actor,
        )
        # Delete the data source
        db.execute(
            text("DELETE FROM control.data_sources WHERE data_source_id = CAST(:id AS UUID)"),
            {"id": str(ds.data_source_id)},
        )
        # Credential should be gone via CASCADE
        with pytest.raises(CredentialNotFoundError):
            cred_repo.find_by_id(db, credential_id=cred.credential_id)


# ─────────────────────────────────────────────────────────────────────────────
# REPO-10: count_active_datasets returns 0 when datasets table absent
# ─────────────────────────────────────────────────────────────────────────────


class TestCountActiveDatasets:
    """REPO-10"""

    def test_returns_zero_when_no_datasets_exist(self, db, ds_repo):
        """
        Since F005 (datasets) is not yet built, count_active_datasets must
        return 0 rather than raising an exception.
        """
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        actor = uuid.uuid4()
        ds = ds_repo.create(
            db,
            workspace_id=wid,
            tenant_id=tid,
            source_name="count-test",
            source_type="postgresql",
            connection_mode="direct",
            environment="development",
            created_by=actor,
        )
        count = ds_repo.count_active_datasets(db, data_source_id=ds.data_source_id)
        assert count == 0
