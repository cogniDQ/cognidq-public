"""
Integration tests — F005 P05: DatasetService Lifecycle Transitions

Tests activate, deactivate, reactivate, archive.

Test IDs: LC-01 through LC-15
"""

import os
import uuid

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

from app.services.datasets.errors import DatasetAPIError
from app.services.datasets.models import (
    CreateDatasetPayload,
    CreateFieldPayload,
    DatasetStatus,
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
    connection.execute(text("SAVEPOINT sp_lc_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    try:
        connection.execute(text("ROLLBACK TO SAVEPOINT sp_lc_test"))
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


def _draft_dataset_with_field(db, svc, wid, tid, dsid):
    """Create a draft dataset with one field (ready to activate)."""
    ds = svc.create_dataset(
        db,
        workspace_id=wid,
        tenant_id=tid,
        actor_id=uuid.uuid4(),
        payload=CreateDatasetPayload(
            data_source_id=dsid,
            dataset_name=f"ds-{uuid.uuid4()}",
            dataset_type="table",
            physical_identifier=f"pub.{uuid.uuid4()}",
            criticality="medium",
            business_domain="test",
        ),
    )
    svc.add_field(
        db,
        workspace_id=wid,
        dataset_id=ds.dataset_id,
        actor_id=uuid.uuid4(),
        payload=CreateFieldPayload(field_name="id", data_type="integer"),
    )
    return ds


def _active_dataset(db, svc, wid, tid, dsid, actor=None):
    """Create and activate a dataset."""
    actor = actor or uuid.uuid4()
    ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)
    return svc.activate_dataset(
        db,
        workspace_id=wid,
        dataset_id=ds.dataset_id,
        actor_id=actor,
    )


def _inactive_dataset(db, svc, wid, tid, dsid):
    """Create, activate, and deactivate a dataset."""
    ds = _active_dataset(db, svc, wid, tid, dsid)
    return svc.deactivate_dataset(
        db,
        workspace_id=wid,
        dataset_id=ds.dataset_id,
        actor_id=uuid.uuid4(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# LC-01: activate — draft with fields → ACTIVE
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateSuccess:
    """LC-01"""

    def test_activate_draft_with_fields(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)

        result = svc.activate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.status == DatasetStatus.active


# ─────────────────────────────────────────────────────────────────────────────
# LC-02: activate — draft with no fields → error
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateNoFields:
    """LC-02"""

    def test_activate_no_fields_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = svc.create_dataset(
            db,
            workspace_id=wid,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            payload=CreateDatasetPayload(
                data_source_id=dsid,
                dataset_name="empty-ds",
                dataset_type="table",
                physical_identifier="pub.empty",
                criticality="low",
                business_domain="test",
            ),
        )

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.activate_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "NO_FIELDS"


# ─────────────────────────────────────────────────────────────────────────────
# LC-03: activate — non-draft → error
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateNonDraft:
    """LC-03"""

    def test_activate_active_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.activate_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


# ─────────────────────────────────────────────────────────────────────────────
# LC-04: activate — sets activated_at
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateSetsTimestamp:
    """LC-04"""

    def test_activated_at_populated(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)

        result = svc.activate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.activated_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# LC-05: deactivate — ACTIVE → INACTIVE
# ─────────────────────────────────────────────────────────────────────────────


class TestDeactivateSuccess:
    """LC-05"""

    def test_deactivate_active(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        result = svc.deactivate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.status == DatasetStatus.inactive


# ─────────────────────────────────────────────────────────────────────────────
# LC-06: deactivate — non-active → error
# ─────────────────────────────────────────────────────────────────────────────


class TestDeactivateNonActive:
    """LC-06"""

    def test_deactivate_draft_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.deactivate_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


# ─────────────────────────────────────────────────────────────────────────────
# LC-07: reactivate — INACTIVE → ACTIVE
# ─────────────────────────────────────────────────────────────────────────────


class TestReactivateSuccess:
    """LC-07"""

    def test_reactivate_inactive(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _inactive_dataset(db, svc, wid, tid, dsid)

        result = svc.reactivate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.status == DatasetStatus.active


# ─────────────────────────────────────────────────────────────────────────────
# LC-08: reactivate — non-inactive → error
# ─────────────────────────────────────────────────────────────────────────────


class TestReactivateNonInactive:
    """LC-08"""

    def test_reactivate_active_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.reactivate_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


# ─────────────────────────────────────────────────────────────────────────────
# LC-09: archive — ACTIVE → ARCHIVED
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveActive:
    """LC-09"""

    def test_archive_active(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        result = svc.archive_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.status == DatasetStatus.archived


# ─────────────────────────────────────────────────────────────────────────────
# LC-10: archive — INACTIVE → ARCHIVED
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveInactive:
    """LC-10"""

    def test_archive_inactive(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _inactive_dataset(db, svc, wid, tid, dsid)

        result = svc.archive_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )
        assert result.status == DatasetStatus.archived


# ─────────────────────────────────────────────────────────────────────────────
# LC-11: archive — DRAFT → error
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveDraft:
    """LC-11"""

    def test_archive_draft_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.archive_dataset(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


# ─────────────────────────────────────────────────────────────────────────────
# LC-12: archive — sets timestamps
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveTimestamps:
    """LC-12"""

    def test_archive_sets_archived_at_and_by(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        actor = uuid.uuid4()
        ds = _active_dataset(db, svc, wid, tid, dsid)

        result = svc.archive_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=actor,
        )
        assert result.archived_at is not None
        assert result.archived_by == actor


# ─────────────────────────────────────────────────────────────────────────────
# LC-13: activate — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestActivateAudit:
    """LC-13"""

    def test_activate_audit(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _draft_dataset_with_field(db, svc, wid, tid, dsid)

        svc.activate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID) AND action_type = 'dataset_activated'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# LC-14: deactivate — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestDeactivateAudit:
    """LC-14"""

    def test_deactivate_audit(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        svc.deactivate_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID) AND action_type = 'dataset_deactivated'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# LC-15: archive — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveAudit:
    """LC-15"""

    def test_archive_audit(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _active_dataset(db, svc, wid, tid, dsid)

        svc.archive_dataset(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID) AND action_type = 'dataset_archived'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None
