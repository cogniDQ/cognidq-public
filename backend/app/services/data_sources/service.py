"""
F004 — DataSourceService
=========================

Orchestrates creation (and future mutations) of data sources.
All multi-step writes execute inside one transaction; the commit is
performed by the service so repositories never commit themselves.

Create flow
-----------
1. Validate payload (raises DataSourceAPIError on failure)
2. Verify workspace belongs to the actor's tenant
3. INSERT data source row (credential_reference=NULL initially)
4. Encrypt credentials → INSERT credential row (data_source_id resolved)
5. UPDATE data source with credential_reference
6. Commit transaction
7. Fire-and-forget audit event (POST-commit, never inside transaction)

Security notes
--------------
* Plaintext/ciphertext credentials are never returned to callers.
* The credential_reference UUID (not secrets) is the only artifact surfaced.
* tenant_id is taken exclusively from the actor JWT; request body cannot
  override it.
* Workspace ownership is verified before any write (cross-tenant isolation).
"""

from __future__ import annotations

import json as _json
import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy.exc import IntegrityError as _IntegrityError
from sqlalchemy.orm import Session

from app.services.data_sources import credential_service as cred_svc
from app.services.data_sources import metrics as ds_metrics
from app.services.data_sources.credential_repository import (
    CredentialRepository,
)
from app.services.data_sources.errors import DataSourceAPIError
from app.services.data_sources.models import DataSource
from app.services.data_sources.repository import (
    DataSourceNotFoundError,
    DataSourceRepository,
    DuplicateSourceNameError,
)
from app.services.data_sources.validation import validate_create_payload

logger = logging.getLogger(__name__)

_WORKSPACE_LOOKUP_SQL = """
SELECT workspace_id, tenant_id
FROM control.workspaces
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND tenant_id    = CAST(:tenant_id    AS UUID)
"""

_WORKSPACE_EXISTENCE_SQL = """
SELECT workspace_id, tenant_id
FROM control.workspaces
WHERE workspace_id = CAST(:workspace_id AS UUID)
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

_AUDIT_LOG_QUERY_SQL = """
SELECT
    log_id, tenant_id, workspace_id, action_type, actor_id, actor_role,
    previous_data, new_data, occurred_at
FROM control.workspace_audit_logs
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND tenant_id    = CAST(:tenant_id    AS UUID)
  AND new_data->>'data_source_id' = :data_source_id
ORDER BY occurred_at DESC
LIMIT :limit OFFSET :offset
"""

_AUDIT_LOG_COUNT_SQL = """
SELECT COUNT(*)
FROM control.workspace_audit_logs
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND tenant_id    = CAST(:tenant_id    AS UUID)
  AND new_data->>'data_source_id' = :data_source_id
"""


class DataSourceService:
    """
    Orchestrates data source lifecycle operations.

    Dependencies are injected at construction time, making the service
    independently testable with mock repositories.
    """

    def __init__(
        self,
        ds_repo: DataSourceRepository | None = None,
        cred_repo: CredentialRepository | None = None,
    ) -> None:
        self._ds_repo = ds_repo or DataSourceRepository()
        self._cred_repo = cred_repo or CredentialRepository()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def create(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        actor_role: str = "unknown",
        tenant_id: UUID,
        source_name: str,
        source_type: str,
        connection_mode: str,
        environment: str,
        credentials: dict[str, Any],
        description: str | None = None,
    ) -> DataSource:
        """
        Create a new data source.

        Raises:
            DataSourceAPIError(400): validation failure.
            DataSourceAPIError(404): workspace not found / not in tenant.
            DataSourceAPIError(409): duplicate source_name in workspace.
        """
        # ── 1. Validate payload ──────────────────────────────────────────────
        try:
            self._validate(
                source_name=source_name,
                source_type=source_type,
                connection_mode=connection_mode,
                environment=environment,
                credentials=credentials,
                description=description,
            )
        except DataSourceAPIError:
            try:
                ds_metrics.data_source_create_count.labels(
                    workspace_id=str(workspace_id),
                    source_type=source_type,
                    result="validation_error",
                ).inc()
            except Exception:
                pass
            raise

        # ── 2. Verify workspace belongs to actor's tenant ────────────────────
        # Use the workspace's real tenant_id for the INSERT so that platform_admin
        # writes records with the correct tenant (not the admin's own platform tenant).
        effective_tenant_id = self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        try:
            # ── 3. INSERT data source (credential_reference=NULL) ────────────
            data_source = self._ds_repo.create(
                db,
                workspace_id=workspace_id,
                tenant_id=effective_tenant_id,
                source_name=source_name,
                source_type=source_type,
                connection_mode=connection_mode,
                environment=environment,
                description=description,
                credential_reference=None,
                created_by=actor_id,
            )

            # ── 4. Encrypt credentials → INSERT credential row ───────────────
            encrypted = cred_svc.encrypt(credentials)
            credential = self._cred_repo.create(
                db,
                data_source_id=data_source.data_source_id,
                source_type=source_type,
                encrypted_payload=encrypted,
                created_by=actor_id,
            )

            # ── 5. UPDATE data source with credential_reference ──────────────
            self._ds_repo.update_credential_reference(
                db,
                data_source_id=data_source.data_source_id,
                workspace_id=workspace_id,
                credential_reference=credential.credential_id,
                updated_by=actor_id,
            )

            # ── 6. Commit ────────────────────────────────────────────────────
            db.commit()

            data_source = self._ds_repo.find_by_id(
                db,
                data_source_id=data_source.data_source_id,
                workspace_id=workspace_id,
            )

        except DuplicateSourceNameError as exc:
            db.rollback()
            try:
                ds_metrics.data_source_create_count.labels(
                    workspace_id=str(workspace_id),
                    source_type=source_type,
                    result="conflict",
                ).inc()
            except Exception:
                pass
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DUPLICATE_SOURCE_NAME",
                message=str(exc),
            ) from exc
        except DataSourceAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # ── 7. Fire-and-forget audit (POST-commit) ───────────────────────────
        self._emit_audit(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=effective_tenant_id,
            data_source_id=data_source.data_source_id,
            workspace_id=workspace_id,
            event_type="data_source.created",
            new_data={"source_name": source_name, "source_type": source_type},
        )
        try:
            ds_metrics.data_source_create_count.labels(
                workspace_id=str(workspace_id),
                source_type=source_type,
                result="success",
            ).inc()
        except Exception:
            pass

        return data_source

    def list_sources(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_role: str = "unknown",
        status_filter: str | None = None,
        source_type_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DataSource], int]:
        """
        Return a paginated list of data sources in a workspace.

        Raises:
            DataSourceAPIError(404): workspace not found / not in tenant.
            DataSourceAPIError(400): invalid status_filter.
        """
        if status_filter is not None and status_filter not in ("active", "archived"):
            raise DataSourceAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_FILTER",
                message=f"Invalid status filter '{status_filter}'. Must be 'active' or 'archived'.",
            )
        if page < 1:
            page = 1
        page_size = min(max(page_size, 1), 100)

        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        offset = (page - 1) * page_size
        return self._ds_repo.list(
            db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            status_filter=status_filter,
            source_type_filter=source_type_filter,
            limit=page_size,
            offset=offset,
        )

    def get_by_id(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        data_source_id: UUID,
        actor_role: str = "unknown",
    ) -> DataSource:
        """
        Return a single data source by ID.

        Raises:
            DataSourceAPIError(404): workspace or data source not found.
        """
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )
        try:
            return self._ds_repo.find_by_id(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

    def update(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        actor_role: str = "unknown",
        tenant_id: UUID,
        data_source_id: UUID,
        source_name: str | None = None,
        environment: str | None = None,
        description: str | None = None,
        credentials: dict[str, Any] | None = None,
        # Explicitly rejected immutable fields (raise 400 if provided)
        source_type: str | None = None,
        connection_mode: str | None = None,
    ) -> DataSource:
        """
        Update a data source (metadata-only or with credential rotation).

        Raises:
            DataSourceAPIError(400): immutable field in payload.
            DataSourceAPIError(404): workspace or data source not found.
            DataSourceAPIError(409): duplicate source_name.
        """
        # ── 1. Reject immutable fields ───────────────────────────────────────
        immutable = {}
        if source_type is not None:
            immutable["source_type"] = source_type
        if connection_mode is not None:
            immutable["connection_mode"] = connection_mode
        if immutable:
            raise DataSourceAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="IMMUTABLE_FIELD",
                message=(
                    f"The following fields cannot be changed after creation: "
                    f"{', '.join(sorted(immutable))}."
                ),
                fields=[{"field": k, "message": "immutable"} for k in sorted(immutable)],
            )

        # ── 2. Verify workspace ──────────────────────────────────────────────
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        # ── 3. Fetch current data source (lock row) ──────────────────────────
        try:
            current = self._ds_repo.find_by_id(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
                for_update=True,
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

        try:
            changed_fields: dict[str, Any] = {}

            # ── 4. Metadata update ───────────────────────────────────────────
            if any(f is not None for f in (source_name, environment, description)):
                self._ds_repo.update_metadata(
                    db,
                    data_source_id=data_source_id,
                    workspace_id=workspace_id,
                    updated_by=actor_id,
                    source_name=source_name,
                    environment=environment,
                    description=description,
                )
                if source_name is not None:
                    changed_fields["source_name"] = source_name
                if environment is not None:
                    changed_fields["environment"] = environment
                if description is not None:
                    changed_fields["description"] = description

            # ── 5. Credential rotation ───────────────────────────────────────
            if credentials is not None:
                old_ref = current.credential_reference
                encrypted = cred_svc.encrypt(credentials)
                new_cred = self._cred_repo.create(
                    db,
                    data_source_id=data_source_id,
                    source_type=current.source_type,
                    encrypted_payload=encrypted,
                    created_by=actor_id,
                )
                self._ds_repo.update_credential_reference(
                    db,
                    data_source_id=data_source_id,
                    workspace_id=workspace_id,
                    credential_reference=new_cred.credential_id,
                    updated_by=actor_id,
                )
                # Supersede the old credential
                if old_ref is not None:
                    self._cred_repo.supersede(db, credential_id=old_ref)
                changed_fields["credential_reference"] = str(new_cred.credential_id)

            # ── 6. Commit ────────────────────────────────────────────────────
            db.commit()

            updated = self._ds_repo.find_by_id(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
            )

        except (_IntegrityError, DuplicateSourceNameError) as exc:
            db.rollback()
            orig = getattr(exc, "orig", exc)
            if "uq_data_source_name_workspace" in str(orig) or isinstance(
                exc, DuplicateSourceNameError
            ):
                raise DataSourceAPIError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="DUPLICATE_SOURCE_NAME",
                    message=f"A data source named '{source_name}' already exists in this workspace.",
                ) from exc
            raise
        except DataSourceAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # ── 7. Audit (POST-commit) ───────────────────────────────────────────
        self._emit_audit(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            event_type="data_source.updated",
            new_data={k: v for k, v in changed_fields.items() if k != "credential_reference"},
        )
        try:
            ds_metrics.data_source_update_count.labels(
                workspace_id=str(workspace_id),
                result="success",
            ).inc()
        except Exception:
            pass

        return updated

    def test_connection(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        actor_role: str = "unknown",
        tenant_id: UUID,
        data_source_id: UUID,
    ) -> dict:
        """
        Test connectivity to a data source.

        Returns a dict with keys: status, tested_at, error_summary.

        Raises:
            DataSourceAPIError(404): workspace or data source not found.
            DataSourceAPIError(409): data source is archived.
        """
        # ── 1. Verify workspace ──────────────────────────────────────────────
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        # ── 2. Fetch data source ─────────────────────────────────────────────
        try:
            current = self._ds_repo.find_by_id(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

        # ── 3. Reject archived sources ───────────────────────────────────────
        if current.status.value == "archived":
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATA_SOURCE_ARCHIVED",
                message="Cannot test an archived data source.",
            )

        # ── 4. Decrypt credentials ───────────────────────────────────────────
        creds: dict[str, Any] = {}
        if current.credential_reference is not None:
            cred_row = self._cred_repo.find_by_id(db, credential_id=current.credential_reference)
            creds = cred_svc.decrypt(bytes(cred_row.encrypted_payload))

        # ── 5. Perform connection test (non-transactional I/O) ───────────────
        result = self._perform_connection_test(
            source_type=current.source_type,
            connection_mode=current.connection_mode,
            credentials=creds,
        )

        # ── 6. UPDATE last_test_status + last_tested_at (transactional) ──────
        self._ds_repo.update_test_status(
            db,
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            last_test_status=result["status"],
            last_tested_at=result["tested_at"],
        )
        db.commit()

        # ── 7. Emit audit (POST-commit) ──────────────────────────────────────
        self._emit_audit(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            event_type="data_source_connection_tested",
            new_data={"outcome": result["status"]},
        )
        try:
            ds_metrics.data_source_test_connection_count.labels(
                workspace_id=str(workspace_id),
                source_type=current.source_type,
                result=result["status"],
            ).inc()
        except Exception:
            pass

        return result

    def archive(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        actor_role: str = "unknown",
        tenant_id: UUID,
        data_source_id: UUID,
    ) -> DataSource:
        """
        Archive a data source.

        Raises:
            DataSourceAPIError(404): workspace or data source not found.
            DataSourceAPIError(409): source is already archived or has active datasets.
        """
        # ── 1. Verify workspace ──────────────────────────────────────────────
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        # ── 2. Fetch current data source ─────────────────────────────────────
        try:
            current = self._ds_repo.find_by_id(
                db, data_source_id=data_source_id, workspace_id=workspace_id
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

        # ── 3. Reject already-archived sources ───────────────────────────────
        if current.status.value == "archived":
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATA_SOURCE_ALREADY_ARCHIVED",
                message="This data source is already archived.",
            )

        # ── 4. Check blocking active datasets ───────────────────────────────
        active_count = self._ds_repo.count_active_datasets(db, data_source_id=data_source_id)
        if active_count > 0:
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="ACTIVE_DATASETS_BLOCKING_ARCHIVE",
                message=(
                    f"Cannot archive this data source: {active_count} active "
                    f"dataset(s) are still referencing it."
                ),
            )

        # ── 5. Archive ───────────────────────────────────────────────────────
        try:
            from app.services.data_sources.repository import DataSourceArchivedError

            self._ds_repo.archive(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
                archived_by=actor_id,
            )
            db.commit()
        except DataSourceArchivedError as exc:
            db.rollback()
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATA_SOURCE_ALREADY_ARCHIVED",
                message="This data source is already archived.",
            ) from exc
        except DataSourceAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # ── 6. Emit audit (POST-commit) ──────────────────────────────────────
        archived_ds = self._ds_repo.find_by_id(
            db, data_source_id=data_source_id, workspace_id=workspace_id
        )
        self._emit_audit(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            event_type="data_source_archived",
            new_data={"status": "archived"},
        )
        try:
            ds_metrics.data_source_archive_count.labels(
                workspace_id=str(workspace_id),
                result="success",
            ).inc()
        except Exception:
            pass

        return archived_ds

    def restore(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        actor_role: str = "unknown",
        tenant_id: UUID,
        data_source_id: UUID,
    ) -> DataSource:
        """
        Restore an archived data source to active status.

        Raises:
            DataSourceAPIError(404): workspace or data source not found.
            DataSourceAPIError(409): source is already active (not archived).
        """
        # ── 1. Verify workspace ──────────────────────────────────────────────
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        # ── 2. Fetch current data source ─────────────────────────────────────
        try:
            current = self._ds_repo.find_by_id(
                db, data_source_id=data_source_id, workspace_id=workspace_id
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

        # ── 3. Reject non-archived sources ───────────────────────────────────
        if current.status.value != "archived":
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATA_SOURCE_NOT_ARCHIVED",
                message="This data source is not archived and cannot be restored.",
            )

        # ── 4. Restore ───────────────────────────────────────────────────────
        try:
            self._ds_repo.restore(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
                restored_by=actor_id,
            )
            db.commit()
        except DataSourceAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        # ── 5. Emit audit (POST-commit) ──────────────────────────────────────
        restored_ds = self._ds_repo.find_by_id(
            db, data_source_id=data_source_id, workspace_id=workspace_id
        )
        self._emit_audit(
            db,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            event_type="data_source_restored",
            new_data={"status": "active"},
        )
        try:
            ds_metrics.data_source_restore_count.labels(
                workspace_id=str(workspace_id),
                result="success",
            ).inc()
        except Exception:
            pass

        return restored_ds

    def get_audit_logs(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        data_source_id: UUID,
        actor_role: str = "unknown",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """
        Return paginated audit log entries for a data source.

        Raises:
            DataSourceAPIError(404): workspace not found / not in tenant.
        """
        from sqlalchemy import text as _text

        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        if page < 1:
            page = 1
        page_size = min(max(page_size, 1), 100)
        offset = (page - 1) * page_size

        params = {
            "workspace_id": str(workspace_id),
            "tenant_id": str(tenant_id),
            "data_source_id": str(data_source_id),
            "limit": page_size,
            "offset": offset,
        }

        rows = db.execute(_text(_AUDIT_LOG_QUERY_SQL), params).fetchall()
        total = db.execute(
            _text(_AUDIT_LOG_COUNT_SQL),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        ).scalar()

        items = [
            {
                "log_id": str(row.log_id),
                "action_type": row.action_type,
                "actor_id": str(row.actor_id),
                "actor_role": row.actor_role,
                "previous_data": row.previous_data,
                "new_data": row.new_data,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            }
            for row in rows
        ]
        return items, total

    def browse_schema(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        data_source_id: UUID,
        actor_role: str = "unknown",
    ) -> dict:
        """
        Introspect the data source and return its schemas, tables, and views.

        Uses the legacy connector infrastructure (``BaseConnector``) to query
        ``INFORMATION_SCHEMA`` (or equivalent) for metadata.

        Returns::

            {
                "data_source_id": str,
                "source_type": str,
                "schemas": [
                    {
                        "schema_name": str,
                        "objects": [
                            {
                                "object_name": str,
                                "object_type": "table" | "view",
                                "schema_name": str,
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }

        Raises:
            DataSourceAPIError(404): workspace or data source not found.
            DataSourceAPIError(409): data source is archived.
            DataSourceAPIError(502): introspection failed (connectivity / driver error).
        """
        # ── 1. Verify workspace ──────────────────────────────────────────────
        self._verify_workspace(
            db, workspace_id=workspace_id, tenant_id=tenant_id, actor_role=actor_role
        )

        # ── 2. Fetch data source ─────────────────────────────────────────────
        try:
            current = self._ds_repo.find_by_id(
                db,
                data_source_id=data_source_id,
                workspace_id=workspace_id,
            )
        except DataSourceNotFoundError as exc:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="DATA_SOURCE_NOT_FOUND",
                message=str(exc),
            ) from exc

        # ── 3. Reject archived sources ───────────────────────────────────────
        if current.status.value == "archived":
            raise DataSourceAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code="DATA_SOURCE_ARCHIVED",
                message="Cannot browse an archived data source.",
            )

        # ── 4. Decrypt credentials ───────────────────────────────────────────
        creds: dict[str, Any] = {}
        if current.credential_reference is not None:
            cred_row = self._cred_repo.find_by_id(db, credential_id=current.credential_reference)
            creds = cred_svc.decrypt(bytes(cred_row.encrypted_payload))

        # ── 5. Introspect via connector ──────────────────────────────────────
        return self._introspect_source(
            source_type=current.source_type,
            credentials=creds,
            data_source_id=data_source_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _introspect_source(
        self,
        *,
        source_type: str,
        credentials: dict[str, Any],
        data_source_id: UUID,
    ) -> dict:
        """
        Connect to the source and return schema metadata.

        Supports all JDBC-style sources (host/port/database/username/password)
        via direct SQL against ``INFORMATION_SCHEMA``.

        For unsupported source types a 502 error is raised.
        """
        import psycopg2  # type: ignore

        # Collect credential values for error sanitisation
        cred_values = [str(v) for v in credentials.values() if v and isinstance(v, str)]

        schemas_result: list = []

        try:
            if source_type == "postgresql":
                conn = psycopg2.connect(
                    host=credentials.get("host"),
                    port=int(credentials.get("port", 5432)),
                    database=credentials.get("database"),
                    user=credentials.get("username"),
                    password=credentials.get("password"),
                    connect_timeout=15,
                )
                try:
                    schemas_result = self._pg_introspect(conn)
                finally:
                    conn.close()

            elif source_type == "mysql":
                import pymysql  # type: ignore

                conn = pymysql.connect(
                    host=credentials.get("host"),
                    port=int(credentials.get("port", 3306)),
                    database=credentials.get("database"),
                    user=credentials.get("username"),
                    password=credentials.get("password"),
                    connect_timeout=15,
                )
                try:
                    schemas_result = self._mysql_introspect(conn, credentials.get("database", ""))
                finally:
                    conn.close()

            elif source_type == "mssql":
                import pymssql  # type: ignore

                conn = pymssql.connect(
                    server=credentials.get("host"),
                    port=int(credentials.get("port", 1433)),
                    database=credentials.get("database"),
                    user=credentials.get("username"),
                    password=credentials.get("password"),
                    login_timeout=15,
                )
                try:
                    schemas_result = self._mssql_introspect(conn)
                finally:
                    conn.close()

            elif source_type == "oracle":
                import oracledb  # type: ignore

                conn = oracledb.connect(
                    user=credentials.get("username"),
                    password=credentials.get("password"),
                    dsn=f"{credentials.get('host')}:{int(credentials.get('port', 1521))}/{credentials.get('database')}",
                )
                try:
                    schemas_result = self._oracle_introspect(conn, credentials.get("username", ""))
                finally:
                    conn.close()

            else:
                if source_type == "csv":
                    schemas_result = self._csv_introspect(credentials)
                else:
                    raise DataSourceAPIError(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        code="BROWSE_NOT_SUPPORTED",
                        message=f"Schema browsing is not yet supported for source type '{source_type}'.",
                    )

        except DataSourceAPIError:
            raise
        except Exception as exc:
            safe_msg = cred_svc.sanitize_error_message(str(exc), cred_values)
            logger.error("Schema introspection failed for %s: %s", data_source_id, safe_msg)
            raise DataSourceAPIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="INTROSPECTION_FAILED",
                message=f"Failed to introspect data source: {safe_msg}",
            ) from exc

        return {
            "data_source_id": str(data_source_id),
            "source_type": source_type,
            "schemas": schemas_result,
        }

    # -- Connector-specific introspection helpers ----------------------------

    @staticmethod
    def _csv_introspect(credentials: dict[str, Any]) -> list:
        """CSV: read a single header row and infer column types from a sample.

        Produces one synthetic schema ``default`` and one synthetic object whose
        name is the file's basename (without extension). Type inference is a
        best-effort scan of the first 100 data rows: int → float → date → string.
        """
        import csv as _csv
        import os as _os
        import re as _re
        from datetime import datetime as _dt

        file_path = str(credentials.get("file_path") or "").strip()
        if not file_path:
            raise DataSourceAPIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="INTROSPECTION_FAILED",
                message="CSV connection has no file_path credential.",
            )
        if not _os.path.isfile(file_path):
            raise DataSourceAPIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="INTROSPECTION_FAILED",
                message=f"CSV file not found at '{file_path}'.",
            )

        delimiter = str(credentials.get("delimiter") or ",")
        encoding = str(credentials.get("encoding") or "utf-8")
        has_header_raw = credentials.get("has_header", True)
        has_header = (
            has_header_raw
            if isinstance(has_header_raw, bool)
            else str(has_header_raw).lower() in ("1", "true", "yes")
        )
        quote_char = str(credentials.get("quote_char") or '"')

        with open(file_path, encoding=encoding, newline="") as fh:
            reader = _csv.reader(fh, delimiter=delimiter, quotechar=quote_char)
            try:
                first = next(reader)
            except StopIteration:
                first = []
            if has_header:
                headers = [(h.strip() or f"col_{i + 1}") for i, h in enumerate(first)]
                sample_rows: list[list[str]] = []
            else:
                headers = [f"col_{i + 1}" for i in range(len(first))]
                sample_rows = [first]
            for _ in range(100):
                try:
                    sample_rows.append(next(reader))
                except StopIteration:
                    break

        # Type inference per column
        date_re = _re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")
        nullable_flags = [False] * len(headers)
        types: list[str] = []
        for col_idx in range(len(headers)):
            values = [(row[col_idx] if col_idx < len(row) else "") for row in sample_rows]
            non_empty = [v for v in values if v is not None and str(v).strip() != ""]
            if len(non_empty) < len(values):
                nullable_flags[col_idx] = True
            if not non_empty:
                types.append("string")
                continue
            inferred = "integer"
            for v in non_empty:
                s = str(v).strip()
                if inferred == "integer":
                    try:
                        int(s)
                        continue
                    except ValueError:
                        inferred = "float"
                if inferred == "float":
                    try:
                        float(s)
                        continue
                    except ValueError:
                        inferred = "date" if date_re.match(s) else "string"
                if inferred == "date" and not date_re.match(s):
                    inferred = "string"
                if inferred == "string":
                    break
            try:
                # Verify date inference holds for all values
                if inferred == "date":
                    for v in non_empty:
                        s = str(v).strip()
                        if date_re.match(s):
                            try:
                                _dt.fromisoformat(s.replace(" ", "T"))
                            except ValueError:
                                inferred = "string"
                                break
                        else:
                            inferred = "string"
                            break
            except Exception:
                inferred = "string"
            types.append(inferred)

        object_name = _os.path.splitext(_os.path.basename(file_path))[0] or "csv"
        columns = [
            {
                "column_name": name,
                "data_type": types[i],
                "ordinal_position": i + 1,
                "nullable": nullable_flags[i],
                "is_primary_key": False,
            }
            for i, name in enumerate(headers)
        ]
        return [
            {
                "schema_name": "default",
                "objects": [
                    {
                        "object_name": object_name,
                        "object_type": "table",
                        "schema_name": "default",
                        "columns": columns,
                    }
                ],
            }
        ]

    @staticmethod
    def _pg_introspect(conn) -> list:
        """PostgreSQL: query information_schema for schemas, tables + views + columns."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY table_schema, table_name
            """
        )
        rows = cur.fetchall()

        # Build object map
        schema_map: dict[str, list] = {}
        obj_lookup: dict[tuple, dict] = {}
        for schema_name, table_name, table_type in rows:
            obj_type = "view" if table_type == "VIEW" else "table"
            obj = {
                "object_name": table_name,
                "object_type": obj_type,
                "schema_name": schema_name,
                "columns": [],
            }
            schema_map.setdefault(schema_name, []).append(obj)
            obj_lookup[(schema_name, table_name)] = obj

        # Fetch columns for all discovered objects
        cur.execute(
            """
            SELECT c.table_schema, c.table_name,
                   c.column_name, c.data_type, c.ordinal_position,
                   CASE WHEN c.is_nullable = 'YES' THEN true ELSE false END AS nullable,
                   CASE WHEN kcu.column_name IS NOT NULL THEN true ELSE false END AS is_primary_key
            FROM information_schema.columns c
            LEFT JOIN information_schema.table_constraints tc
                ON tc.table_schema = c.table_schema
               AND tc.table_name = c.table_name
               AND tc.constraint_type = 'PRIMARY KEY'
            LEFT JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = tc.constraint_name
               AND kcu.table_schema = tc.table_schema
               AND kcu.table_name = tc.table_name
               AND kcu.column_name = c.column_name
            WHERE c.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
            """
        )
        col_rows = cur.fetchall()
        cur.close()

        for schema_name, table_name, col_name, data_type, ordinal, nullable, is_pk in col_rows:
            obj = obj_lookup.get((schema_name, table_name))
            if obj is not None:
                obj["columns"].append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "ordinal_position": ordinal,
                        "nullable": nullable,
                        "is_primary_key": is_pk,
                    }
                )

        return [{"schema_name": s, "objects": objs} for s, objs in sorted(schema_map.items())]

    @staticmethod
    def _mysql_introspect(conn, database: str) -> list:
        """MySQL: query information_schema scoped to the connected database."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """,
            (database,),
        )
        rows = cur.fetchall()

        schema_map: dict[str, list] = {}
        obj_lookup: dict[tuple, dict] = {}
        for schema_name, table_name, table_type in rows:
            obj_type = "view" if table_type == "VIEW" else "table"
            obj = {
                "object_name": table_name,
                "object_type": obj_type,
                "schema_name": schema_name,
                "columns": [],
            }
            schema_map.setdefault(schema_name, []).append(obj)
            obj_lookup[(schema_name, table_name)] = obj

        # Fetch columns
        cur.execute(
            """
            SELECT c.TABLE_SCHEMA, c.TABLE_NAME,
                   c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION,
                   CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS nullable,
                   CASE WHEN c.COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END AS is_primary_key
            FROM information_schema.COLUMNS c
            WHERE c.TABLE_SCHEMA = %s
            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
            """,
            (database,),
        )
        col_rows = cur.fetchall()
        cur.close()

        for schema_name, table_name, col_name, data_type, ordinal, nullable, is_pk in col_rows:
            obj = obj_lookup.get((schema_name, table_name))
            if obj is not None:
                obj["columns"].append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "ordinal_position": ordinal,
                        "nullable": bool(nullable),
                        "is_primary_key": bool(is_pk),
                    }
                )

        return [{"schema_name": s, "objects": objs} for s, objs in sorted(schema_map.items())]

    @staticmethod
    def _mssql_introspect(conn) -> list:
        """MSSQL: query information_schema for schemas, tables + views + columns."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
        )
        rows = cur.fetchall()

        schema_map: dict[str, list] = {}
        obj_lookup: dict[tuple, dict] = {}
        for schema_name, table_name, table_type in rows:
            obj_type = "view" if table_type == "VIEW" else "table"
            obj = {
                "object_name": table_name,
                "object_type": obj_type,
                "schema_name": schema_name,
                "columns": [],
            }
            schema_map.setdefault(schema_name, []).append(obj)
            obj_lookup[(schema_name, table_name)] = obj

        # Fetch columns with primary key info
        cur.execute(
            """
            SELECT c.TABLE_SCHEMA, c.TABLE_NAME,
                   c.COLUMN_NAME, c.DATA_TYPE, c.ORDINAL_POSITION,
                   CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS nullable,
                   CASE WHEN kcu.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                ON tc.TABLE_SCHEMA = c.TABLE_SCHEMA
               AND tc.TABLE_NAME = c.TABLE_NAME
               AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
               AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
               AND kcu.TABLE_NAME = tc.TABLE_NAME
               AND kcu.COLUMN_NAME = c.COLUMN_NAME
            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
            """
        )
        col_rows = cur.fetchall()
        cur.close()

        for schema_name, table_name, col_name, data_type, ordinal, nullable, is_pk in col_rows:
            obj = obj_lookup.get((schema_name, table_name))
            if obj is not None:
                obj["columns"].append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "ordinal_position": ordinal,
                        "nullable": bool(nullable),
                        "is_primary_key": bool(is_pk),
                    }
                )

        return [{"schema_name": s, "objects": objs} for s, objs in sorted(schema_map.items())]

    @staticmethod
    def _oracle_introspect(conn, username: str) -> list:
        """Oracle: query ALL_TABLES + ALL_VIEWS + ALL_TAB_COLUMNS for the connected user's schema."""
        cur = conn.cursor()
        owner = username.upper()
        cur.execute(
            """
            SELECT OWNER, TABLE_NAME, 'TABLE' AS OBJECT_TYPE
            FROM ALL_TABLES WHERE OWNER = :owner
            UNION ALL
            SELECT OWNER, VIEW_NAME, 'VIEW' AS OBJECT_TYPE
            FROM ALL_VIEWS WHERE OWNER = :owner
            ORDER BY 1, 2
            """,
            {"owner": owner},
        )
        rows = cur.fetchall()

        schema_map: dict[str, list] = {}
        obj_lookup: dict[tuple, dict] = {}
        for schema_name, obj_name, obj_type in rows:
            obj = {
                "object_name": obj_name,
                "object_type": obj_type.lower(),
                "schema_name": schema_name,
                "columns": [],
            }
            schema_map.setdefault(schema_name, []).append(obj)
            obj_lookup[(schema_name, obj_name)] = obj

        # Fetch columns with primary key info
        cur.execute(
            """
            SELECT c.OWNER, c.TABLE_NAME,
                   c.COLUMN_NAME, c.DATA_TYPE, c.COLUMN_ID,
                   CASE WHEN c.NULLABLE = 'Y' THEN 1 ELSE 0 END AS nullable,
                   CASE WHEN cc.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key
            FROM ALL_TAB_COLUMNS c
            LEFT JOIN ALL_CONSTRAINTS ac
                ON ac.OWNER = c.OWNER
               AND ac.TABLE_NAME = c.TABLE_NAME
               AND ac.CONSTRAINT_TYPE = 'P'
            LEFT JOIN ALL_CONS_COLUMNS cc
                ON cc.CONSTRAINT_NAME = ac.CONSTRAINT_NAME
               AND cc.OWNER = ac.OWNER
               AND cc.TABLE_NAME = ac.TABLE_NAME
               AND cc.COLUMN_NAME = c.COLUMN_NAME
            WHERE c.OWNER = :owner
            ORDER BY c.OWNER, c.TABLE_NAME, c.COLUMN_ID
            """,
            {"owner": owner},
        )
        col_rows = cur.fetchall()
        cur.close()

        for schema_name, table_name, col_name, data_type, ordinal, nullable, is_pk in col_rows:
            obj = obj_lookup.get((schema_name, table_name))
            if obj is not None:
                obj["columns"].append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "ordinal_position": ordinal,
                        "nullable": bool(nullable),
                        "is_primary_key": bool(is_pk),
                    }
                )

        return [{"schema_name": s, "objects": objs} for s, objs in sorted(schema_map.items())]

    def _perform_connection_test(
        self,
        *,
        source_type: str,
        connection_mode: str,
        credentials: dict[str, Any],
    ) -> dict:
        """
        Perform a connection test and return a result dict.

        Never raises — all exceptions are caught and converted to a
        test_failed / unreachable result.
        """
        tested_at = datetime.now(UTC)

        # Agent mode is not supported
        if connection_mode == "agent":
            return {
                "status": "test_failed",
                "tested_at": tested_at,
                "error_summary": "AGENT_MODE_NOT_SUPPORTED",
            }

        # Collect credential values for sanitization
        cred_values = [str(v) for v in credentials.values() if v and isinstance(v, str)]

        # Inside Docker, 'localhost'/'127.0.0.1' refers to the container itself.
        # Map to host.docker.internal so the backend can reach the host machine.
        host_raw = credentials.get("host", "")
        if host_raw in ("localhost", "127.0.0.1"):
            credentials = {**credentials, "host": "host.docker.internal"}

        try:
            if source_type == "postgresql":
                import psycopg2  # type: ignore

                conn = psycopg2.connect(
                    host=credentials.get("host"),
                    port=int(credentials.get("port", 5432)),
                    database=credentials.get("database"),
                    user=credentials.get("username"),
                    password=credentials.get("password"),
                    connect_timeout=10,
                )
                conn.close()
                return {"status": "reachable", "tested_at": tested_at, "error_summary": None}

            elif source_type in ("mysql", "mssql", "oracle"):
                import socket

                default_ports = {"mysql": 3306, "mssql": 1433, "oracle": 1521}
                host = credentials.get("host", "")
                port = int(credentials.get("port", default_ports.get(source_type, 3306)))
                with socket.create_connection((host, port), timeout=10):
                    pass
                return {"status": "reachable", "tested_at": tested_at, "error_summary": None}

            elif source_type == "snowflake":
                import socket

                account = credentials.get("account_identifier", "")
                host = f"{account}.snowflakecomputing.com"
                with socket.create_connection((host, 443), timeout=10):
                    pass
                return {"status": "reachable", "tested_at": tested_at, "error_summary": None}

            elif source_type == "bigquery":
                import socket

                with socket.create_connection(("bigquery.googleapis.com", 443), timeout=10):
                    pass
                return {"status": "reachable", "tested_at": tested_at, "error_summary": None}

            else:
                import socket

                host = credentials.get("host", "")
                port = int(credentials.get("port", 443))
                with socket.create_connection((host, port), timeout=10):
                    pass
                return {"status": "reachable", "tested_at": tested_at, "error_summary": None}

        except Exception as exc:
            raw_msg = str(exc)
            safe_msg = cred_svc.sanitize_error_message(raw_msg, cred_values)
            msg_lower = raw_msg.lower()

            if "timed out" in msg_lower or "timeout" in msg_lower:
                return {
                    "status": "test_failed",
                    "tested_at": tested_at,
                    "error_summary": f"CONNECTION_TIMEOUT: {safe_msg}",
                }

            # psycopg2 OperationalError = postgres-level connection failure → unreachable
            try:
                import psycopg2  # type: ignore

                if isinstance(exc, psycopg2.OperationalError):
                    return {
                        "status": "unreachable",
                        "tested_at": tested_at,
                        "error_summary": safe_msg,
                    }
            except ImportError:
                pass

            return {
                "status": "test_failed",
                "tested_at": tested_at,
                "error_summary": safe_msg,
            }

    def _validate(
        self,
        *,
        source_name: str,
        source_type: str,
        connection_mode: str,
        environment: str,
        credentials: Any,
        description: Any,
    ) -> None:
        """Raise DataSourceAPIError(400) if payload does not pass validation."""
        result = validate_create_payload(
            {
                "source_name": source_name,
                "source_type": source_type,
                "connection_mode": connection_mode,
                "environment": environment,
                "credentials": credentials,
                "description": description,
            }
        )
        if not result.is_valid:
            raise DataSourceAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Request payload failed validation.",
                fields=result.errors,
            )

    def _verify_workspace(
        self, db: Session, *, workspace_id: UUID, tenant_id: UUID, actor_role: str = "unknown"
    ) -> UUID:
        """
        Confirm workspace_id exists (and belongs to the actor's tenant for non-platform roles).

        Returns the workspace's actual tenant_id (needed when platform_admin writes
        records that must carry the workspace's tenant, not the admin's own).
        Raises DataSourceAPIError(404) if not found.
        """
        from sqlalchemy import text as _text

        if actor_role == "platform_admin":
            row = db.execute(
                _text(_WORKSPACE_EXISTENCE_SQL),
                {"workspace_id": str(workspace_id)},
            ).fetchone()
        else:
            row = db.execute(
                _text(_WORKSPACE_LOOKUP_SQL),
                {
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                },
            ).fetchone()
        if row is None:
            raise DataSourceAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message=(
                    f"Workspace {workspace_id} not found or does not belong to the actor's tenant."
                ),
            )
        return UUID(str(row.tenant_id))

    def _emit_audit(
        self,
        db: Session,
        *,
        actor_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        data_source_id: UUID,
        workspace_id: UUID,
        event_type: str,
        new_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Persist an audit event into workspace_audit_logs (POST-commit).
        Failures are logged but never re-raised so the HTTP response is
        never affected by audit subsystem issues.
        """
        from sqlalchemy import text as _text

        try:
            audit_payload = {"data_source_id": str(data_source_id)}
            if new_data:
                audit_payload.update(new_data)

            db.execute(
                _text(_AUDIT_LOG_INSERT_SQL),
                {
                    "log_id": str(_uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                    "action_type": event_type,
                    "actor_id": str(actor_id),
                    "actor_role": actor_role,
                    "new_data": _json.dumps(audit_payload),
                    "occurred_at": datetime.now(UTC),
                },
            )
            db.commit()
            logger.info(
                "audit event=%s data_source_id=%s workspace_id=%s actor_id=%s",
                event_type,
                data_source_id,
                workspace_id,
                actor_id,
            )
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.exception("Failed to emit audit event; continuing.")
