"""
F005 — DatasetService
======================

Orchestrates dataset lifecycle operations — create, read, update, and
status transitions.

Transaction boundaries
----------------------
* Repositories never commit — the service commits once all writes succeed.
* Audit log entries are emitted POST-commit in fire-and-forget fashion so
  an audit table failure never blocks the HTTP response.

Security
--------
* ``workspace_id`` scoping on every query guarantees cross-tenant isolation.
* Data source status is verified prior to dataset creation.
"""

from __future__ import annotations

import json as _json
import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.datasets.errors import (
    DatasetAPIError,
    DatasetFieldNotFoundError,
    DatasetNotFoundError,
    DataSourceNotActiveError,
    DuplicateDatasetNameError,
    DuplicateFieldNameError,
    DuplicatePhysicalIdentifierError,
)
from app.services.datasets.field_repository import DatasetFieldRepository
from app.services.datasets.models import (
    BulkImportResult,
    CreateDatasetPayload,
    CreateFieldPayload,
    Dataset,
    DatasetField,
    DatasetListFilters,
    DatasetListResult,
    DatasetStatus,
    UpdateDatasetPayload,
    UpdateFieldPayload,
)
from app.services.datasets.repository import DatasetRepository
from app.services.datasets.validation import (
    validate_bulk_import_fields,
    validate_create_dataset_payload,
    validate_create_field_payload,
    validate_update_dataset_payload,
    validate_update_field_payload,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SQL helpers
# ─────────────────────────────────────────────────────────────────────────────

_DATA_SOURCE_STATUS_SQL = """
SELECT status FROM control.data_sources
WHERE data_source_id = CAST(:data_source_id AS UUID)
"""

_AUDIT_LOG_INSERT_SQL = """
INSERT INTO control.workspace_audit_logs
    (log_id, tenant_id, workspace_id, action_type, actor_id, actor_role,
     previous_data, new_data, occurred_at)
VALUES
    (CAST(:log_id AS UUID), CAST(:tenant_id AS UUID), CAST(:workspace_id AS UUID),
     :action_type, CAST(:actor_id AS UUID), :actor_role,
     NULL, CAST(:new_data AS JSONB), :occurred_at)
"""


class DatasetService:
    """Orchestrates dataset CRUD and lifecycle operations."""

    def __init__(
        self,
        repo: DatasetRepository | None = None,
        field_repo: DatasetFieldRepository | None = None,
    ) -> None:
        self._repo = repo or DatasetRepository()
        self._field_repo = field_repo or DatasetFieldRepository()

    # ─────────────────────────────────────────────────────────────────────────
    # Create
    # ─────────────────────────────────────────────────────────────────────────

    def create_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        payload: CreateDatasetPayload,
    ) -> Dataset:
        # 1. Validate payload
        result = validate_create_dataset_payload(
            {
                "dataset_name": payload.dataset_name,
                "dataset_type": payload.dataset_type,
                "physical_identifier": payload.physical_identifier,
                "schema_name": payload.schema_name,
                "description": payload.description,
                "business_domain": payload.business_domain,
                "criticality": payload.criticality,
                "freshness_expectation": payload.freshness_expectation,
            }
        )
        if not result.is_valid:
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Request payload failed validation.",
                fields=result.errors,
            )

        # 2. Verify data source exists and is active.
        # File-typed datasets (e.g. CSV uploads) are allowed to omit data_source_id;
        # they don't have a backing connection record.
        if payload.dataset_type == "file" and payload.data_source_id is None:
            pass
        else:
            if payload.data_source_id is None:
                raise DatasetAPIError(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="VALIDATION_ERROR",
                    message="data_source_id is required for non-file datasets.",
                )
            self._verify_data_source_active(db, data_source_id=payload.data_source_id)

        now = datetime.now(UTC)
        ds = Dataset(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            data_source_id=payload.data_source_id,
            dataset_name=payload.dataset_name.strip(),
            dataset_type=payload.dataset_type,
            physical_identifier=payload.physical_identifier.strip(),
            schema_name=payload.schema_name.strip() if payload.schema_name else None,
            description=payload.description,
            business_domain=payload.business_domain,
            criticality=payload.criticality,
            owner_user_id=payload.owner_user_id,
            freshness_expectation=payload.freshness_expectation,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )

        try:
            created = self._repo.insert(db, ds)
            db.commit()
        except DuplicateDatasetNameError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_DATASET_NAME",
                message=str(exc),
            ) from exc
        except DuplicatePhysicalIdentifierError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_PHYSICAL_IDENTIFIER",
                message=str(exc),
            ) from exc
        except DatasetAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # Audit (post-commit, fire-and-forget)
        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_created",
            new_data={
                "dataset_id": str(created.dataset_id),
                "dataset_name": created.dataset_name,
                "dataset_type": created.dataset_type,
            },
        )

        return created

    # ─────────────────────────────────────────────────────────────────────────
    # Get
    # ─────────────────────────────────────────────────────────────────────────

    def get_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        return ds

    # ─────────────────────────────────────────────────────────────────────────
    # List
    # ─────────────────────────────────────────────────────────────────────────

    def list_datasets(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        filters: DatasetListFilters,
    ) -> DatasetListResult:
        return self._repo.list_datasets(db, workspace_id=workspace_id, filters=filters)

    # ─────────────────────────────────────────────────────────────────────────
    # Update
    # ─────────────────────────────────────────────────────────────────────────

    def update_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
        payload: UpdateDatasetPayload,
    ) -> Dataset:
        # 1. Build dict of non-None fields
        changes: dict[str, Any] = {}
        for field_name in (
            "dataset_name",
            "description",
            "business_domain",
            "criticality",
            "owner_user_id",
            "freshness_expectation",
            "schema_name",
        ):
            val = getattr(payload, field_name, None)
            if val is not None:
                changes[field_name] = val

        if not changes:
            # Nothing to update — return current
            return self.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)

        # 2. Validate
        result = validate_update_dataset_payload(changes)
        if not result.is_valid:
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Request payload failed validation.",
                fields=result.errors,
            )

        # 3. Fetch current (lock row)
        current = self._repo.find_by_id_for_update(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
        )
        if current is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )

        # 4. Apply changes to current model
        for k, v in changes.items():
            if k == "dataset_name":
                current.dataset_name = v.strip() if isinstance(v, str) else v
            elif k == "owner_user_id":
                current.owner_user_id = v
            else:
                setattr(current, k, v)
        current.updated_by = actor_id

        try:
            updated = self._repo.update(db, current)
            db.commit()
        except DuplicateDatasetNameError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_DATASET_NAME",
                message=str(exc),
            ) from exc
        except DatasetNotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # Audit (post-commit)
        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=current.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_updated",
            new_data={
                "dataset_id": str(dataset_id),
                "changed_fields": list(changes.keys()),
            },
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Add field
    # ─────────────────────────────────────────────────────────────────────────

    def add_field(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
        payload: CreateFieldPayload,
    ) -> DatasetField:
        # 1. Validate payload
        result = validate_create_field_payload(
            {
                "field_name": payload.field_name,
                "data_type": payload.data_type,
                "business_definition": payload.business_definition,
                "sensitivity_classification": payload.sensitivity_classification,
            }
        )
        if not result.is_valid:
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Field payload failed validation.",
                fields=result.errors,
            )

        # 2. Verify dataset exists and is not archived
        ds = self._require_non_archived_dataset(
            db, workspace_id=workspace_id, dataset_id=dataset_id
        )

        # 3. Auto-assign ordinal
        ordinal = self._field_repo.max_ordinal(db, dataset_id=dataset_id) + 1
        now = datetime.now(UTC)

        field = DatasetField(
            dataset_id=dataset_id,
            field_name=payload.field_name.strip(),
            data_type=payload.data_type.strip(),
            ordinal_position=ordinal,
            created_at=now,
            updated_at=now,
            nullable=payload.nullable,
            business_definition=payload.business_definition,
            sensitivity_classification=payload.sensitivity_classification,
            is_key_candidate=payload.is_key_candidate,
        )

        try:
            created = self._field_repo.insert(db, field)
            db.commit()
        except DuplicateFieldNameError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_FIELD_NAME",
                message=str(exc),
            ) from exc

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_field_added",
            new_data={
                "dataset_id": str(dataset_id),
                "field_id": str(created.field_id),
                "field_name": created.field_name,
            },
        )

        return created

    # ─────────────────────────────────────────────────────────────────────────
    # Update field
    # ─────────────────────────────────────────────────────────────────────────

    def update_field(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        field_id: UUID,
        actor_id: UUID,
        payload: UpdateFieldPayload,
    ) -> DatasetField:
        # 1. Validate payload
        changes: dict[str, Any] = {}
        for attr in (
            "data_type",
            "nullable",
            "business_definition",
            "sensitivity_classification",
            "is_key_candidate",
            "ordinal_position",
        ):
            val = getattr(payload, attr, None)
            if val is not None:
                changes[attr] = val

        if not changes:
            # Nothing to update — return current
            field = self._field_repo.find_by_id(db, dataset_id=dataset_id, field_id=field_id)
            if field is None:
                raise DatasetFieldNotFoundError(
                    f"Field {field_id} not found in dataset {dataset_id}."
                )
            return field

        result = validate_update_field_payload(changes)
        if not result.is_valid:
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Field payload failed validation.",
                fields=result.errors,
            )

        # 2. Verify dataset exists
        ds = self._repo.find_by_id(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )

        # 3. Find field
        field = self._field_repo.find_by_id(db, dataset_id=dataset_id, field_id=field_id)
        if field is None:
            raise DatasetFieldNotFoundError(f"Field {field_id} not found in dataset {dataset_id}.")

        # 4. Apply changes
        for k, v in changes.items():
            setattr(field, k, v)

        try:
            updated = self._field_repo.update(db, field)
            db.commit()
        except DuplicateFieldNameError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_FIELD_NAME",
                message=str(exc),
            ) from exc

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_field_updated",
            new_data={
                "dataset_id": str(dataset_id),
                "field_id": str(field_id),
                "changed_fields": list(changes.keys()),
            },
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Remove field
    # ─────────────────────────────────────────────────────────────────────────

    def remove_field(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        field_id: UUID,
        actor_id: UUID,
    ) -> None:
        # 1. Verify dataset not archived
        ds = self._require_non_archived_dataset(
            db, workspace_id=workspace_id, dataset_id=dataset_id
        )

        # 2. Delete field
        deleted = self._field_repo.delete(db, dataset_id=dataset_id, field_id=field_id)
        if not deleted:
            raise DatasetFieldNotFoundError(f"Field {field_id} not found in dataset {dataset_id}.")
        db.commit()

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_field_removed",
            new_data={
                "dataset_id": str(dataset_id),
                "field_id": str(field_id),
            },
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Bulk import fields
    # ─────────────────────────────────────────────────────────────────────────

    def bulk_import_fields(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
        mode: str,
        fields: list,
    ) -> BulkImportResult:
        if mode not in ("append", "replace"):
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_MODE",
                message=f"Invalid mode '{mode}'. Must be 'append' or 'replace'.",
            )

        # 1. Validate all payloads
        raw = [
            {
                "field_name": f.field_name,
                "data_type": f.data_type,
                "business_definition": f.business_definition,
                "sensitivity_classification": f.sensitivity_classification,
            }
            for f in fields
        ]
        result = validate_bulk_import_fields(raw, mode)
        if not result.is_valid:
            raise DatasetAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Bulk import validation failed.",
                fields=result.errors,
            )

        # 2. Verify dataset not archived
        ds = self._require_non_archived_dataset(
            db, workspace_id=workspace_id, dataset_id=dataset_id
        )

        fields_removed = 0

        if mode == "replace":
            fields_removed = self._field_repo.delete_all_by_dataset(db, dataset_id=dataset_id)
            start_ordinal = 0
        else:
            # append — check for collisions
            existing = self._field_repo.find_all_by_dataset(db, dataset_id=dataset_id)
            existing_names = {f.field_name.lower() for f in existing}
            collisions = [f.field_name for f in fields if f.field_name.lower() in existing_names]
            if collisions:
                db.rollback()
                raise DatasetAPIError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="FIELD_NAME_COLLISION",
                    message=f"Field names already exist: {', '.join(collisions)}",
                )
            start_ordinal = self._field_repo.max_ordinal(db, dataset_id=dataset_id)

        # 3. Build DatasetField objects
        now = datetime.now(UTC)
        to_insert = []
        for idx, fp in enumerate(fields):
            to_insert.append(
                DatasetField(
                    dataset_id=dataset_id,
                    field_name=fp.field_name.strip(),
                    data_type=fp.data_type.strip(),
                    ordinal_position=start_ordinal + idx + 1,
                    created_at=now,
                    updated_at=now,
                    nullable=fp.nullable,
                    business_definition=fp.business_definition,
                    sensitivity_classification=fp.sensitivity_classification,
                    is_key_candidate=fp.is_key_candidate,
                )
            )

        try:
            self._field_repo.bulk_insert(db, to_insert)
            db.commit()
        except DuplicateFieldNameError as exc:
            db.rollback()
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_FIELD_NAME",
                message=str(exc),
            ) from exc

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_fields_bulk_imported",
            new_data={
                "dataset_id": str(dataset_id),
                "mode": mode,
                "fields_added": len(fields),
                "fields_removed": fields_removed,
            },
        )

        return BulkImportResult(
            mode=mode,
            fields_added=len(fields),
            fields_removed=fields_removed,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Activate
    # ─────────────────────────────────────────────────────────────────────────

    def activate_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id_for_update(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        if ds.status != DatasetStatus.draft:
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot activate dataset in '{ds.status}' status. Must be 'draft'.",
            )

        field_count = self._field_repo.count_by_dataset(db, dataset_id=dataset_id)
        if field_count < 1:
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="NO_FIELDS",
                message="Cannot activate a dataset with zero fields.",
            )

        now = datetime.now(UTC)
        updated = self._repo.update_status(
            db,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            new_status=DatasetStatus.active,
            actor_id=actor_id,
            activated_at=now,
        )
        db.commit()

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_activated",
            new_data={"dataset_id": str(dataset_id)},
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Deactivate
    # ─────────────────────────────────────────────────────────────────────────

    def deactivate_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id_for_update(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        if ds.status != DatasetStatus.active:
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot deactivate dataset in '{ds.status}' status. Must be 'active'.",
            )

        updated = self._repo.update_status(
            db,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            new_status=DatasetStatus.inactive,
            actor_id=actor_id,
        )
        db.commit()

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_deactivated",
            new_data={"dataset_id": str(dataset_id)},
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Reactivate
    # ─────────────────────────────────────────────────────────────────────────

    def reactivate_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id_for_update(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        if ds.status != DatasetStatus.inactive:
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot reactivate dataset in '{ds.status}' status. Must be 'inactive'.",
            )

        updated = self._repo.update_status(
            db,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            new_status=DatasetStatus.active,
            actor_id=actor_id,
        )
        db.commit()

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_reactivated",
            new_data={"dataset_id": str(dataset_id)},
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Archive
    # ─────────────────────────────────────────────────────────────────────────

    def archive_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
        actor_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id_for_update(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        if ds.status not in (DatasetStatus.active, DatasetStatus.inactive):
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot archive dataset in '{ds.status}' status. Must be 'active' or 'inactive'.",
            )

        now = datetime.now(UTC)
        updated = self._repo.update_status(
            db,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            new_status=DatasetStatus.archived,
            actor_id=actor_id,
            archived_at=now,
            archived_by=actor_id,
        )
        db.commit()

        self._emit_audit(
            db,
            actor_id=actor_id,
            tenant_id=ds.tenant_id,
            workspace_id=workspace_id,
            event_type="dataset_archived",
            new_data={"dataset_id": str(dataset_id)},
        )

        return updated

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _require_non_archived_dataset(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        dataset_id: UUID,
    ) -> Dataset:
        ds = self._repo.find_by_id(db, workspace_id=workspace_id, dataset_id=dataset_id)
        if ds is None:
            raise DatasetNotFoundError(
                f"Dataset {dataset_id} not found in workspace {workspace_id}."
            )
        if ds.status == DatasetStatus.archived:
            raise DatasetAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATASET_ARCHIVED",
                message=f"Dataset {dataset_id} is archived. Cannot modify fields.",
            )
        return ds

    def _verify_data_source_active(self, db: Session, *, data_source_id: UUID) -> None:
        row = db.execute(
            text(_DATA_SOURCE_STATUS_SQL),
            {"data_source_id": str(data_source_id)},
        ).fetchone()
        if row is None:
            raise DatasetAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=f"Data source {data_source_id} not found.",
            )
        if row[0] != "active":
            raise DataSourceNotActiveError(
                f"Data source {data_source_id} is not active (status: {row[0]})."
            )

    def _emit_audit(
        self,
        db: Session,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        event_type: str,
        new_data: dict[str, Any] | None = None,
    ) -> None:
        try:
            db.execute(
                text(_AUDIT_LOG_INSERT_SQL),
                {
                    "log_id": str(_uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                    "action_type": event_type,
                    "actor_id": str(actor_id),
                    "actor_role": "workspace_admin",
                    "new_data": _json.dumps(new_data or {}),
                    "occurred_at": datetime.now(UTC),
                },
            )
            db.commit()
        except Exception:
            logger.exception("Failed to emit audit event: %s", event_type)
