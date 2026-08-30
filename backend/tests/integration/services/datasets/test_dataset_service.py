"""
Integration tests — F005 P03: DatasetService Create, Get, List, Update

Tests the service layer with a live database.

Test IDs: SVC-01 through SVC-15
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
    DatasetAPIError,
    DatasetNotFoundError,
    DataSourceNotActiveError,
)
from app.services.datasets.models import (
    CreateDatasetPayload,
    DatasetListFilters,
    DatasetStatus,
    UpdateDatasetPayload,
)
from app.services.datasets.service import DatasetService

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    return create_engine(DATABASE_URL)


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    connection.execute(text("SAVEPOINT sp_svc_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    # Service methods may call db.rollback() on IntegrityError which
    # destroys the savepoint — fall back to rolling back the transaction.
    try:
        connection.execute(text("ROLLBACK TO SAVEPOINT sp_svc_test"))
    except Exception:
        pass
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture()
def svc():
    return DatasetService()


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


def _new_data_source(
    db: Session,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    source_status: str = "active",
) -> uuid.UUID:
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
                :status, 'untested',
                NOW(), NOW(), :actor
            )
        """),
        {
            "dsid": str(dsid),
            "wid": str(workspace_id),
            "tid": str(tenant_id),
            "name": f"DS {dsid}",
            "status": source_status,
            "actor": str(uuid.uuid4()),
        },
    )
    return dsid


def _make_create_payload(
    data_source_id: uuid.UUID,
    *,
    name: str = "orders_fact",
    physical_id: str = "public.orders",
    dtype: str = "table",
) -> CreateDatasetPayload:
    return CreateDatasetPayload(
        data_source_id=data_source_id,
        dataset_name=name,
        dataset_type=dtype,
        physical_identifier=physical_id,
        criticality="medium",
        business_domain="finance",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SVC-01: create_dataset — success
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetSuccess:
    """SVC-01"""

    def test_create_returns_draft(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        actor = uuid.uuid4()
        payload = _make_create_payload(dsid)

        result = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=actor,
            payload=payload,
        )

        assert result.dataset_id is not None
        assert result.dataset_name == "orders_fact"
        assert result.status == DatasetStatus.draft
        assert result.created_by == actor

    def test_create_with_optional_fields(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        payload = CreateDatasetPayload(
            data_source_id=dsid,
            dataset_name="users_dim",
            dataset_type="view",
            physical_identifier="analytics.users",
            schema_name="analytics",
            description="User dimension table",
            business_domain="people",
            criticality="high",
            freshness_expectation="hourly",
        )

        result = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=payload,
        )
        assert result.schema_name == "analytics"
        assert result.description == "User dimension table"


# ─────────────────────────────────────────────────────────────────────────────
# SVC-02: create_dataset — archived data source
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetArchivedSource:
    """SVC-02"""

    def test_archived_source_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid, source_status="archived")

        payload = _make_create_payload(dsid)
        with pytest.raises(DataSourceNotActiveError):
            svc.create_dataset(
                db,
                workspace_id=wid,
                tenant_id=tid,
                actor_id=uuid.uuid4(),
                payload=payload,
            )


# ─────────────────────────────────────────────────────────────────────────────
# SVC-03: create_dataset — duplicate name
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetDuplicateName:
    """SVC-03"""

    def test_duplicate_name_raises_conflict(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        payload1 = _make_create_payload(dsid, name="dup-ds", physical_id="t1")
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=payload1,
        )

        payload2 = _make_create_payload(dsid, name="DUP-DS", physical_id="t2")
        with pytest.raises(DatasetAPIError) as exc_info:
            svc.create_dataset(
                db,
                workspace_id=wid,
                tenant_id=tid,
                actor_id=uuid.uuid4(),
                payload=payload2,
            )
        assert exc_info.value.code == "DUPLICATE_DATASET_NAME"


# ─────────────────────────────────────────────────────────────────────────────
# SVC-04: create_dataset — duplicate physical_identifier
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetDuplicatePhysicalId:
    """SVC-04"""

    def test_duplicate_physical_id_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)

        payload1 = _make_create_payload(dsid, name="a1", physical_id="public.orders")
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=payload1,
        )

        payload2 = _make_create_payload(dsid, name="a2", physical_id="Public.Orders")
        with pytest.raises(DatasetAPIError) as exc_info:
            svc.create_dataset(
                db,
                workspace_id=wid,
                tenant_id=tid,
                actor_id=uuid.uuid4(),
                payload=payload2,
            )
        assert exc_info.value.code == "DUPLICATE_PHYSICAL_IDENTIFIER"


# ─────────────────────────────────────────────────────────────────────────────
# SVC-05: create_dataset — same physical_id as archived OK
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetArchivedPhysicalIdOk:
    """SVC-05"""

    def test_same_physical_id_after_archive_ok(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        actor = uuid.uuid4()

        payload1 = _make_create_payload(dsid, name="orig", physical_id="pub.data")
        created = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=actor,
            payload=payload1,
        )

        # Archive it directly via SQL
        now = datetime.now(UTC)
        db.execute(
            text("""
                UPDATE control.datasets
                SET status = 'archived', archived_at = :now, archived_by = :actor
                WHERE dataset_id = CAST(:did AS UUID)
            """),
            {"did": str(created.dataset_id), "now": now, "actor": str(actor)},
        )
        db.commit()

        payload2 = _make_create_payload(dsid, name="new-one", physical_id="pub.data")
        result = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=actor,
            payload=payload2,
        )
        assert result.dataset_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# SVC-06: create_dataset — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateDatasetAuditLog:
    """SVC-06"""

    def test_audit_log_created(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        actor = uuid.uuid4()

        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=actor,
            payload=_make_create_payload(dsid),
        )

        row = db.execute(
            text("""
                SELECT action_type, new_data FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_created'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None
        assert row[0] == "dataset_created"


# ─────────────────────────────────────────────────────────────────────────────
# SVC-07: get_dataset — success
# ─────────────────────────────────────────────────────────────────────────────


class TestGetDataset:
    """SVC-07"""

    def test_get_existing(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid),
        )

        found = svc.get_dataset(db, workspace_id=wid, dataset_id=created.dataset_id)
        assert found.dataset_name == "orders_fact"

    def test_get_not_found(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        with pytest.raises(DatasetNotFoundError):
            svc.get_dataset(db, workspace_id=wid, dataset_id=uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# SVC-08: list_datasets
# ─────────────────────────────────────────────────────────────────────────────


class TestListDatasets:
    """SVC-08"""

    def test_list_no_filter(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        for i in range(3):
            svc.create_dataset(
                db,
                workspace_id=wid,
                tenant_id=tid,
                actor_id=uuid.uuid4(),
                payload=_make_create_payload(dsid, name=f"ds-{i}", physical_id=f"t{i}"),
            )

        result = svc.list_datasets(db, workspace_id=wid, filters=DatasetListFilters())
        assert result.total_count == 3
        assert len(result.items) == 3

    def test_list_filter_status(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid),
        )

        result = svc.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(status="draft"),
        )
        assert result.total_count >= 1
        assert all(i.status == "draft" for i in result.items)

    def test_list_search(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid, name="orders_fact", physical_id="pub.orders"),
        )
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid, name="users_dim", physical_id="pub.users"),
        )

        result = svc.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(search="orders"),
        )
        assert result.total_count >= 1

    def test_list_pagination(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        for i in range(5):
            svc.create_dataset(
                db,
                workspace_id=wid,
                tenant_id=tid,
                actor_id=uuid.uuid4(),
                payload=_make_create_payload(dsid, name=f"pg-{i}", physical_id=f"pt{i}"),
            )

        page1 = svc.list_datasets(
            db,
            workspace_id=wid,
            filters=DatasetListFilters(limit=2, offset=0),
        )
        assert len(page1.items) == 2
        assert page1.total_count == 5


# ─────────────────────────────────────────────────────────────────────────────
# SVC-09: update_dataset — success
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateDataset:
    """SVC-09"""

    def test_update_mutable_fields(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid),
        )

        payload = UpdateDatasetPayload(
            dataset_name="updated_orders",
            description="Updated desc",
            criticality="high",
        )
        updated = svc.update_dataset(
            db,
            workspace_id=wid,
            dataset_id=created.dataset_id,
            actor_id=uuid.uuid4(),
            payload=payload,
        )
        assert updated.dataset_name == "updated_orders"
        assert updated.description == "Updated desc"
        assert updated.criticality == "high"

    def test_update_name_uniqueness(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid, name="taken-name", physical_id="t1"),
        )
        ds2 = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid, name="other-name", physical_id="t2"),
        )

        payload = UpdateDatasetPayload(dataset_name="taken-name")
        with pytest.raises(DatasetAPIError) as exc_info:
            svc.update_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds2.dataset_id,
                actor_id=uuid.uuid4(),
                payload=payload,
            )
        assert exc_info.value.code == "DUPLICATE_DATASET_NAME"

    def test_update_audit_log(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        created = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=_make_create_payload(dsid),
        )

        svc.update_dataset(
            db,
            workspace_id=wid,
            dataset_id=created.dataset_id,
            actor_id=uuid.uuid4(),
            payload=UpdateDatasetPayload(description="new desc"),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_updated'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None
