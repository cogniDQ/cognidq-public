"""
Integration tests — F005 P04: DatasetService Field Operations

Tests add_field, update_field, remove_field, bulk_import_fields.

Test IDs: FSVC-01 through FSVC-20
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

from app.services.datasets.errors import (
    DatasetAPIError,
    DatasetFieldNotFoundError,
)
from app.services.datasets.models import (
    CreateDatasetPayload,
    CreateFieldPayload,
    UpdateFieldPayload,
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
    connection.execute(text("SAVEPOINT sp_fsvc_test"))
    session = Session(bind=connection)
    yield session
    session.close()
    try:
        connection.execute(text("ROLLBACK TO SAVEPOINT sp_fsvc_test"))
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


def _create_dataset(db, svc, wid, tid, dsid, *, name=None, physical_id=None):
    """Helper: create a draft dataset and return it."""
    name = name or f"ds-{uuid.uuid4()}"
    physical_id = physical_id or f"pub.{uuid.uuid4()}"
    return svc.create_dataset(
        db,
        workspace_id=wid,
        tenant_id=tid,
        actor_id=uuid.uuid4(),
        payload=CreateDatasetPayload(
            data_source_id=dsid,
            dataset_name=name,
            dataset_type="table",
            physical_identifier=physical_id,
            criticality="medium",
            business_domain="test",
        ),
    )


def _archive_dataset(db, dataset_id, actor_id):
    """Archive a dataset directly via SQL."""
    db.execute(
        text("""
            UPDATE control.datasets
            SET status = 'archived', archived_at = NOW(), archived_by = :actor
            WHERE dataset_id = CAST(:did AS UUID)
        """),
        {"did": str(dataset_id), "actor": str(actor_id)},
    )
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-01: add_field — success
# ─────────────────────────────────────────────────────────────────────────────


class TestAddFieldSuccess:
    """FSVC-01"""

    def test_add_field_returns_field_with_ordinal(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="user_id", data_type="integer"),
        )
        assert field.field_id is not None
        assert field.field_name == "user_id"
        assert field.ordinal_position == 1


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-02: add_field — archived dataset
# ─────────────────────────────────────────────────────────────────────────────


class TestAddFieldArchived:
    """FSVC-02"""

    def test_add_field_to_archived_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        _archive_dataset(db, ds.dataset_id, uuid.uuid4())

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.add_field(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
                payload=CreateFieldPayload(field_name="col_a", data_type="text"),
            )
        assert exc_info.value.code == "DATASET_ARCHIVED"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-03: add_field — duplicate name
# ─────────────────────────────────────────────────────────────────────────────


class TestAddFieldDuplicate:
    """FSVC-03"""

    def test_duplicate_field_name_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="email", data_type="text"),
        )
        with pytest.raises(DatasetAPIError) as exc_info:
            svc.add_field(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
                payload=CreateFieldPayload(field_name="email", data_type="varchar"),
            )
        assert exc_info.value.code == "DUPLICATE_FIELD_NAME"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-04: add_field — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestAddFieldAudit:
    """FSVC-04"""

    def test_audit_entry_created(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="status", data_type="text"),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_field_added'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-05: update_field — success
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateFieldSuccess:
    """FSVC-05"""

    def test_update_mutable_attrs(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="amount", data_type="numeric"),
        )

        updated = svc.update_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            field_id=field.field_id,
            actor_id=uuid.uuid4(),
            payload=UpdateFieldPayload(
                data_type="decimal",
                nullable=False,
                business_definition="Transaction amount",
            ),
        )
        assert updated.data_type == "decimal"
        assert updated.nullable is False
        assert updated.business_definition == "Transaction amount"
        # Field name unchanged
        assert updated.field_name == "amount"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-06: update_field — immutable field_name (AC-P04-006)
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateFieldImmutableName:
    """FSVC-06: UpdateFieldPayload has no field_name so rename is impossible."""

    def test_field_name_not_in_update_payload(self):
        """UpdateFieldPayload does not accept field_name."""
        payload = UpdateFieldPayload(data_type="text")
        assert not hasattr(payload, "field_name") or getattr(payload, "field_name", None) is None


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-07: update_field — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateFieldAudit:
    """FSVC-07"""

    def test_audit_entry_created(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="price", data_type="numeric"),
        )

        svc.update_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            field_id=field.field_id,
            actor_id=uuid.uuid4(),
            payload=UpdateFieldPayload(data_type="float"),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_field_updated'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-08: remove_field — success
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveFieldSuccess:
    """FSVC-08"""

    def test_remove_field(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="col_x", data_type="text"),
        )

        svc.remove_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            field_id=field.field_id,
            actor_id=uuid.uuid4(),
        )

        # Confirm gone
        from app.services.datasets.field_repository import DatasetFieldRepository

        repo = DatasetFieldRepository()
        assert repo.find_by_id(db, dataset_id=ds.dataset_id, field_id=field.field_id) is None


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-09: remove_field — archived dataset
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveFieldArchived:
    """FSVC-09"""

    def test_remove_from_archived_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="col_a", data_type="text"),
        )
        _archive_dataset(db, ds.dataset_id, uuid.uuid4())

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.remove_field(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                field_id=field.field_id,
                actor_id=uuid.uuid4(),
            )
        assert exc_info.value.code == "DATASET_ARCHIVED"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-10: remove_field — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveFieldAudit:
    """FSVC-10"""

    def test_audit_entry_created(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)
        field = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="fld_a", data_type="text"),
        )

        svc.remove_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            field_id=field.field_id,
            actor_id=uuid.uuid4(),
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_field_removed'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-11: bulk_import — append success
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportAppend:
    """FSVC-11"""

    def test_append_adds_all(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        result = svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="append",
            fields=[
                CreateFieldPayload(field_name="a", data_type="int"),
                CreateFieldPayload(field_name="b", data_type="text"),
                CreateFieldPayload(field_name="c", data_type="bool"),
            ],
        )
        assert result.fields_added == 3
        assert result.fields_removed == 0
        assert result.mode == "append"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-12: bulk_import — append collision
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportAppendCollision:
    """FSVC-12"""

    def test_collision_fails_entire_batch(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="existing_col", data_type="text"),
        )

        with pytest.raises(DatasetAPIError) as exc_info:
            svc.bulk_import_fields(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                actor_id=uuid.uuid4(),
                mode="append",
                fields=[
                    CreateFieldPayload(field_name="new_col", data_type="int"),
                    CreateFieldPayload(field_name="existing_col", data_type="varchar"),
                ],
            )
        assert exc_info.value.code == "FIELD_NAME_COLLISION"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-13: bulk_import — replace success
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportReplace:
    """FSVC-13"""

    def test_replace_removes_existing_and_adds_new(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        # Add existing fields
        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="old_a", data_type="text"),
        )
        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="old_b", data_type="text"),
        )

        result = svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="replace",
            fields=[
                CreateFieldPayload(field_name="new_x", data_type="int"),
            ],
        )
        assert result.fields_added == 1
        assert result.fields_removed == 2

        # Verify only new fields exist
        from app.services.datasets.field_repository import DatasetFieldRepository

        repo = DatasetFieldRepository()
        all_fields = repo.find_all_by_dataset(db, dataset_id=ds.dataset_id)
        assert len(all_fields) == 1
        assert all_fields[0].field_name == "new_x"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-14: bulk_import — replace with no existing
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportReplaceEmpty:
    """FSVC-14"""

    def test_replace_with_no_existing_fields(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        result = svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="replace",
            fields=[
                CreateFieldPayload(field_name="col1", data_type="text"),
            ],
        )
        assert result.fields_removed == 0
        assert result.fields_added == 1


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-15: bulk_import — audit log
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportAudit:
    """FSVC-15"""

    def test_audit_entry_created(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="append",
            fields=[CreateFieldPayload(field_name="f1", data_type="int")],
        )

        row = db.execute(
            text("""
                SELECT action_type, new_data FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_fields_bulk_imported'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None
        assert row[0] == "dataset_fields_bulk_imported"


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-16: ordinal auto-increment
# ─────────────────────────────────────────────────────────────────────────────


class TestOrdinalAutoIncrement:
    """FSVC-16"""

    def test_sequential_ordinals(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        f1 = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="col1", data_type="int"),
        )
        f2 = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="col2", data_type="int"),
        )
        f3 = svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="col3", data_type="int"),
        )
        assert f1.ordinal_position == 1
        assert f2.ordinal_position == 2
        assert f3.ordinal_position == 3


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-17: bulk_import append — ordinal continuation
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportOrdinalContinuation:
    """FSVC-17"""

    def test_append_continues_from_max_ordinal(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        # Add 2 fields first
        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="a", data_type="int"),
        )
        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="b", data_type="int"),
        )

        svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="append",
            fields=[
                CreateFieldPayload(field_name="c", data_type="text"),
                CreateFieldPayload(field_name="d", data_type="text"),
            ],
        )

        from app.services.datasets.field_repository import DatasetFieldRepository

        repo = DatasetFieldRepository()
        all_fields = repo.find_all_by_dataset(db, dataset_id=ds.dataset_id)
        ordinals = [f.ordinal_position for f in all_fields]
        assert ordinals == [1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-18: remove_field — not found
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveFieldNotFound:
    """FSVC-18"""

    def test_remove_nonexistent_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetFieldNotFoundError):
            svc.remove_field(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                field_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
            )


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-19: update_field — not found
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateFieldNotFound:
    """FSVC-19"""

    def test_update_nonexistent_raises(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        with pytest.raises(DatasetFieldNotFoundError):
            svc.update_field(
                db,
                workspace_id=wid,
                dataset_id=ds.dataset_id,
                field_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                payload=UpdateFieldPayload(data_type="text"),
            )


# ─────────────────────────────────────────────────────────────────────────────
# FSVC-20: bulk_import replace — audit
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkImportReplaceAudit:
    """FSVC-20"""

    def test_replace_mode_audit(self, db, svc):
        tid = _new_tenant(db)
        wid = _new_workspace(db, tid)
        dsid = _new_data_source(db, wid, tid)
        ds = _create_dataset(db, svc, wid, tid, dsid)

        svc.add_field(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            payload=CreateFieldPayload(field_name="old", data_type="text"),
        )

        svc.bulk_import_fields(
            db,
            workspace_id=wid,
            dataset_id=ds.dataset_id,
            actor_id=uuid.uuid4(),
            mode="replace",
            fields=[CreateFieldPayload(field_name="new", data_type="int")],
        )

        row = db.execute(
            text("""
                SELECT action_type FROM control.workspace_audit_logs
                WHERE workspace_id = CAST(:wid AS UUID)
                  AND action_type = 'dataset_fields_bulk_imported'
                ORDER BY occurred_at DESC LIMIT 1
            """),
            {"wid": str(wid)},
        ).fetchone()
        assert row is not None
