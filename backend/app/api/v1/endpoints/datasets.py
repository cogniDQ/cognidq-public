"""
F005 — Dataset CRUD and Lifecycle Endpoints
=============================================

Routes:
  POST   /api/v1/workspaces/{workspace_id}/datasets
  GET    /api/v1/workspaces/{workspace_id}/datasets
  GET    /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}
  PATCH  /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/activate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/deactivate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/reactivate
  POST   /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/archive
  GET    /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/audit-logs

Auth:
  Write (POST/PATCH/activate): DATASET_WRITE_ROLES
  Read  (GET):                 DATASET_READ_ROLES
  Pause (deactivate):          DATASET_PAUSE_ROLES
  Archive:                     DATASET_ARCHIVE_ROLES
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.dataset_auth import (
    DatasetActorContext,
    verify_dataset_archive_actor,
    verify_dataset_pause_actor,
    verify_dataset_read_actor,
    verify_dataset_write_actor,
)
from app.models.database import get_db
from app.services.audit.hooks import build_dataset_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.datasets.errors import (
    DatasetAPIError,
    DatasetFieldNotFoundError,
    DatasetNotFoundError,
    DataSourceNotActiveError,
)
from app.services.datasets.metrics import (
    dataset_activate_count,
    dataset_archive_count,
    dataset_create_count,
    dataset_deactivate_count,
    dataset_field_add_count,
    dataset_field_bulk_import_count,
    dataset_reactivate_count,
    dataset_update_count,
)
from app.services.datasets.models import (
    CreateDatasetPayload,
    CreateFieldPayload,
    DatasetListFilters,
    UpdateDatasetPayload,
    UpdateFieldPayload,
)
from app.services.datasets.service import DatasetService
from app.services.datasources.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/datasets",
    tags=["datasets"],
)

_service = DatasetService()

_PLATFORM_ROLES = frozenset({"platform_admin", "platform_viewer"})


def _resolve_tenant_id(workspace_id: UUID, actor: DatasetActorContext, db: Session) -> UUID:
    """Return the workspace's tenant_id.

    Platform admins have no tenant_id on their user row, so look it up from
    the workspace record. Regular workspace actors already carry tenant_id.
    """
    is_platform_op = (actor.actor_role or "") in _PLATFORM_ROLES
    if not is_platform_op and actor.tenant_id:
        return actor.tenant_id
    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid LIMIT 1"),
        {"wid": str(workspace_id)},
    ).fetchone()
    if not row or not row.tenant_id:
        raise DatasetAPIError(
            status_code=404, code="WORKSPACE_NOT_FOUND", message="Workspace not found"
        )
    return row.tenant_id


_audit_svc = AuditService()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateDatasetRequest(BaseModel):
    data_source_id: str | None = Field(
        None, description="UUID of the parent data source. Optional only for dataset_type='file'."
    )
    dataset_name: str = Field(..., description="Human-readable name (3-200 chars).")
    dataset_type: str = Field(..., description="table, view, file, or logical.")
    physical_identifier: str = Field(
        ..., description="Physical table/view/file name (1-500 chars)."
    )
    schema_name: str | None = Field(None, description="Database schema name.")
    description: str | None = Field(None, description="Free-text description.")
    business_domain: str | None = Field(None, description="Business domain tag.")
    criticality: str = Field("low", description="low, medium, high, or critical.")
    owner_user_id: str | None = Field(None, description="UUID of the owner user.")
    freshness_expectation: str | None = Field(None, description="Free-text freshness expectation.")


class PatchDatasetRequest(BaseModel):
    dataset_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    criticality: str | None = None
    owner_user_id: str | None = None
    freshness_expectation: str | None = None
    schema_name: str | None = None
    # Immutable fields — captured to return 400
    dataset_type: str | None = None
    data_source_id: str | None = None
    physical_identifier: str | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_dataset(ds, *, data_source_name: str | None = None) -> dict:
    """Serialize a Dataset domain object to a JSON-ready dict."""
    return {
        "dataset_id": str(ds.dataset_id),
        "workspace_id": str(ds.workspace_id),
        "tenant_id": str(ds.tenant_id),
        "data_source_id": str(ds.data_source_id) if ds.data_source_id else None,
        "data_source_name": data_source_name,
        "dataset_name": ds.dataset_name,
        "dataset_type": ds.dataset_type,
        "physical_identifier": ds.physical_identifier,
        "schema_name": ds.schema_name,
        "description": ds.description,
        "business_domain": ds.business_domain,
        "criticality": ds.criticality,
        "owner_user_id": str(ds.owner_user_id) if ds.owner_user_id else None,
        "freshness_expectation": ds.freshness_expectation,
        "status": ds.status.value if hasattr(ds.status, "value") else ds.status,
        "field_count": 0,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        "created_by": str(ds.created_by) if ds.created_by else None,
        "updated_by": str(ds.updated_by) if ds.updated_by else None,
        "activated_at": ds.activated_at.isoformat() if ds.activated_at else None,
        "archived_at": ds.archived_at.isoformat() if ds.archived_at else None,
        "archived_by": str(ds.archived_by) if ds.archived_by else None,
    }


def _serialize_field(f) -> dict:
    # Sample-values columns may be missing on legacy field rows; tolerate that.
    sample_values = list(getattr(f, "sample_values", None) or [])
    sv_at = getattr(f, "sample_values_updated_at", None)
    return {
        "field_id": str(f.field_id),
        "field_name": f.field_name,
        "data_type": f.data_type,
        "nullable": f.nullable,
        "business_definition": f.business_definition,
        "sensitivity_classification": f.sensitivity_classification,
        "is_key_candidate": f.is_key_candidate,
        "ordinal_position": f.ordinal_position,
        # E2 — candidate enrichment with table preview
        "sample_values": sample_values,
        "sample_values_updated_at": sv_at.isoformat() if sv_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _serialize_list_item(item) -> dict:
    return {
        "dataset_id": str(item.dataset_id),
        "workspace_id": str(item.workspace_id),
        "dataset_name": item.dataset_name,
        "dataset_type": item.dataset_type,
        "data_source_id": str(item.data_source_id) if item.data_source_id else None,
        "data_source_name": item.data_source_name,
        "physical_identifier": item.physical_identifier,
        "business_domain": item.business_domain,
        "criticality": item.criticality,
        "owner_user_id": str(item.owner_user_id) if item.owner_user_id else None,
        "status": item.status,
        "field_count": item.field_count,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _get_data_source_name(db: Session, data_source_id: UUID | None) -> str | None:
    if data_source_id is None:
        return None
    row = db.execute(
        text(
            "SELECT source_name FROM control.data_sources WHERE data_source_id = CAST(:id AS UUID)"
        ),
        {"id": str(data_source_id)},
    ).fetchone()
    return row[0] if row else None


def _resolve_connector_config(
    db: Session, data_source_id: UUID, workspace_id: UUID
) -> tuple[str, dict] | None:
    """Resolve a control.data_sources row + decrypted credentials into a
    ``(source_type, connection_config)`` tuple suitable for
    ``ConnectionManager.get_connector``.

    Returns ``None`` only when the data source row does not exist at all.
    Raises :class:`DatasetAPIError` with a 403 ``DATA_SOURCE_FORBIDDEN`` code
    when the row exists but is not visible to ``workspace_id`` (so callers
    can surface an actionable permission error instead of a misleading 404).
    Raises 409 ``DATA_SOURCE_NOT_ACTIVE`` for inactive data sources.
    """
    from app.services.data_sources import credential_service as cred_svc

    row = db.execute(
        text(
            """
            SELECT ds.source_type, ds.status, ds.credential_reference,
                   creds.encrypted_payload
              FROM control.data_sources ds
         LEFT JOIN control.data_source_credentials creds
                ON creds.credential_id = ds.credential_reference
             WHERE ds.data_source_id = CAST(:id AS UUID)
               AND (
                     ds.workspace_id = CAST(:ws AS UUID)
                     OR (
                         ds.workspace_id IS NULL
                         AND ds.data_source_id IN (
                             SELECT connection_id
                               FROM control.workspace_connection_assignments
                              WHERE workspace_id = CAST(:ws AS UUID)
                         )
                     )
                   )
            """
        ),
        {"id": str(data_source_id), "ws": str(workspace_id)},
    ).fetchone()
    if not row:
        # F16 — distinguish "row missing" (404) from "row exists but not
        # accessible to this workspace" (403). The original implementation
        # collapsed both into a generic 404, which masked legitimate
        # permission errors during cross-workspace navigation.
        exists = db.execute(
            text("SELECT 1 FROM control.data_sources WHERE data_source_id = CAST(:id AS UUID)"),
            {"id": str(data_source_id)},
        ).fetchone()
        if exists:
            logger.warning(
                "data_source_forbidden data_source_id=%s workspace_id=%s",
                data_source_id,
                workspace_id,
            )
            raise DatasetAPIError(
                status_code=403,
                code="DATA_SOURCE_FORBIDDEN",
                message=(
                    f"Data source {data_source_id} is not accessible from workspace {workspace_id}."
                ),
            )
        return None
    source_type, status_val, _cred_ref, payload = row
    if (status_val or "active").lower() != "active":
        raise DatasetAPIError(
            status_code=409,
            code="DATA_SOURCE_NOT_ACTIVE",
            message=f"Data source {data_source_id} is not active (status={status_val}).",
        )
    creds: dict = {}
    if payload is not None:
        try:
            creds = cred_svc.decrypt(bytes(payload))
        except Exception as exc:  # pragma: no cover
            # F17 — enrich 5xx logging with workspace + data-source context
            # so on-call engineers can correlate failures without grepping.
            logger.exception(
                "credential_decryption_failed data_source_id=%s workspace_id=%s err=%s",
                data_source_id,
                workspace_id,
                exc,
            )
            raise DatasetAPIError(
                status_code=500,
                code="CREDENTIAL_DECRYPTION_FAILED",
                message="Could not decrypt data source credentials.",
            )
    return source_type, creds


def _get_field_count(db: Session, dataset_id: UUID) -> int:
    row = db.execute(
        text("SELECT COUNT(*) FROM control.dataset_fields WHERE dataset_id = CAST(:id AS UUID)"),
        {"id": str(dataset_id)},
    ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# POST — Create Dataset
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a Dataset",
)
async def create_dataset(
    workspace_id: UUID,
    body: CreateDatasetRequest,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        payload = CreateDatasetPayload(
            data_source_id=UUID(body.data_source_id) if body.data_source_id else None,
            dataset_name=body.dataset_name,
            dataset_type=body.dataset_type,
            physical_identifier=body.physical_identifier,
            schema_name=body.schema_name,
            description=body.description,
            business_domain=body.business_domain,
            criticality=body.criticality,
            owner_user_id=UUID(body.owner_user_id) if body.owner_user_id else None,
            freshness_expectation=body.freshness_expectation,
        )
        ds = _service.create_dataset(
            db,
            workspace_id=workspace_id,
            tenant_id=_resolve_tenant_id(workspace_id, actor, db),
            actor_id=actor.actor_id,
            payload=payload,
        )
        dataset_create_count.labels(
            workspace_id=wid,
            dataset_type=body.dataset_type,
            result="success",
        ).inc()
    except DataSourceNotActiveError as exc:
        dataset_create_count.labels(
            workspace_id=wid,
            dataset_type=body.dataset_type,
            result="error",
        ).inc()
        raise DatasetAPIError(status_code=409, code="DATA_SOURCE_NOT_ACTIVE", message=str(exc))
    except DatasetAPIError:
        dataset_create_count.labels(
            workspace_id=wid,
            dataset_type=body.dataset_type,
            result="error",
        ).inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = 0

    # F052 audit hook (best-effort — post-service transaction)
    try:
        _audit_svc.write(
            db,
            build_dataset_audit_entry(
                ctx=AuditContext(
                    tenant_id=_resolve_tenant_id(workspace_id, actor, db),
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role,
                    request_id=None,
                    source_ip=None,
                ),
                action="dataset_created",
                workspace_id=workspace_id,
                dataset_id=ds.dataset_id,
                after_state={
                    "dataset_name": ds.dataset_name,
                    "dataset_type": ds.dataset_type,
                    "criticality": ds.criticality,
                },
            ),
        )
        db.commit()
    except Exception:
        logger.warning(
            "audit_write_failed action_type=dataset_created dataset_id=%s", ds.dataset_id
        )

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=result)


# ---------------------------------------------------------------------------
# GET — List Datasets
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List Datasets",
)
async def list_datasets(
    workspace_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    data_source_id: str | None = Query(None),
    owner_user_id: str | None = Query(None),
    business_domain: str | None = Query(None),
    criticality: str | None = Query(None),
    dataset_type: str | None = Query(None),
    search: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    offset = (page - 1) * page_size
    filters = DatasetListFilters(
        status=status_filter,
        data_source_id=UUID(data_source_id) if data_source_id else None,
        owner_user_id=UUID(owner_user_id) if owner_user_id else None,
        business_domain=business_domain,
        criticality=criticality,
        dataset_type=dataset_type,
        search=search,
        sort_by=sort_by,
        sort_order=sort_dir,
        limit=page_size,
        offset=offset,
    )
    result = _service.list_datasets(db, workspace_id=workspace_id, filters=filters)
    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize_list_item(item) for item in result.items],
            "total": result.total_count,
            "page": page,
            "page_size": page_size,
        },
    )


# ---------------------------------------------------------------------------
# GET — Get Dataset Detail
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}",
    status_code=status.HTTP_200_OK,
    summary="Get Dataset Detail",
)
async def get_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        ds = _service.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    ds_name = _get_data_source_name(db, ds.data_source_id)
    fields = _service._field_repo.find_all_by_dataset(db, dataset_id=dataset_id)

    # Pull enrichment (last_profiled_at + per-field profile stats) directly so
    # we don't have to thread these columns through the repository layer.
    ds_meta = db.execute(
        text(
            """
            SELECT last_profiled_at, last_profile
              FROM control.datasets
             WHERE dataset_id = CAST(:id AS UUID)
            """
        ),
        {"id": str(dataset_id)},
    ).fetchone()
    field_rows = db.execute(
        text(
            """
            SELECT field_id, null_count, distinct_count, min_value, max_value,
                   profile_stats, profiled_at
              FROM control.dataset_fields
             WHERE dataset_id = CAST(:id AS UUID)
            """
        ),
        {"id": str(dataset_id)},
    ).fetchall()
    field_enrichment = {
        str(r[0]): {
            "null_count": r[1],
            "distinct_count": r[2],
            "min_value": r[3],
            "max_value": r[4],
            "profile_stats": r[5],
            "profiled_at": r[6].isoformat() if r[6] else None,
        }
        for r in field_rows
    }

    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = len(fields)
    if ds_meta:
        result["last_profiled_at"] = ds_meta[0].isoformat() if ds_meta[0] else None
        result["last_profile"] = ds_meta[1]
    result["fields"] = [
        {**_serialize_field(f), **field_enrichment.get(str(f.field_id), {})} for f in fields
    ]
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# GET — Preview Dataset Rows (spec §17.4 / §21.3)
# ---------------------------------------------------------------------------

#: Hard cap on rows returned by the preview endpoint, mirroring the
#: PREVIEW_ROW_HARD_CAP enforced inside each connector. Kept conservative
#: at the API layer so a misbehaving client can't request millions of rows
#: in a single browser-driven preview.
DATASET_PREVIEW_MAX_ROWS: int = 1000

#: Soft cap on individual cell payload size. Cells exceeding this are
#: replaced with a stable placeholder and their column added to
#: ``truncated_columns`` in the response.
DATASET_PREVIEW_MAX_CELL_BYTES: int = 8 * 1024  # 8 KiB


def _truncate_preview_rows(
    rows: list[dict[str, Any]],
    *,
    max_cell_bytes: int = DATASET_PREVIEW_MAX_CELL_BYTES,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Trim outsized cell payloads, returning the trimmed rows + the set of
    column names that contained at least one truncated value."""
    truncated: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        new_row: dict[str, Any] = {}
        for col, val in row.items():
            if isinstance(val, str) and len(val.encode("utf-8")) > max_cell_bytes:
                truncated.add(col)
                new_row[col] = (
                    val.encode("utf-8")[:max_cell_bytes].decode("utf-8", errors="ignore")
                    + "…[truncated]"
                )
            else:
                new_row[col] = val
        out.append(new_row)
    return out, sorted(truncated)


@router.get(
    "/{dataset_id}/preview",
    status_code=status.HTTP_200_OK,
    summary="Preview Dataset Rows",
)
async def preview_dataset_rows(
    workspace_id: UUID,
    dataset_id: UUID,
    limit: int = Query(
        100,
        ge=1,
        le=DATASET_PREVIEW_MAX_ROWS,
        description="Number of rows to fetch (1..1000).",
    ),
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Return a bounded preview of the dataset's underlying rows.

    Resolves the dataset → its parent data source → a connector instance,
    then calls :py:meth:`BaseConnector.preview_dataset` (which enforces the
    2M-row hard cap and, for SQL connectors, parameterised LIMIT + identifier
    validation per spec §17.4). Cells exceeding
    :data:`DATASET_PREVIEW_MAX_CELL_BYTES` are truncated and reported via
    ``truncated_columns``.
    """
    # 1. Resolve dataset (404 if not found in this workspace).
    try:
        ds = _service.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))

    # 2. Resolve underlying data source.
    if ds.data_source_id is None:
        raise DatasetAPIError(
            status_code=400,
            code="PREVIEW_UNSUPPORTED_FOR_FILE_DATASET",
            message="Preview is not yet supported for file-uploaded datasets.",
        )
    resolved = _resolve_connector_config(db, ds.data_source_id, workspace_id)
    if resolved is None:
        raise DatasetAPIError(
            status_code=404,
            code="DATA_SOURCE_NOT_FOUND",
            message=f"Data source {ds.data_source_id} for dataset {dataset_id} is missing.",
        )
    source_type, connection_config = resolved

    # 3. Build a connector and run the controlled preview.
    try:
        connector = await ConnectionManager.get_connector(source_type, connection_config)
    except Exception as exc:  # pragma: no cover - configuration errors
        # F17 — include workspace_id alongside dataset_id and data_source_id
        # for cross-tenant on-call diagnostics.
        logger.exception(
            "connector_build_failed dataset_id=%s data_source_id=%s workspace_id=%s",
            dataset_id,
            ds.data_source_id,
            workspace_id,
        )
        raise DatasetAPIError(
            status_code=500,
            code="CONNECTOR_BUILD_FAILED",
            message=f"Failed to initialise connector: {exc}",
        )

    try:
        async with connector:
            rows = await connector.preview_dataset(
                table_name=ds.physical_identifier,
                schema_name=ds.schema_name,
                limit=limit,
            )
    except ValueError as exc:
        # Identifier validation rejected — report as bad request, not 500.
        raise DatasetAPIError(
            status_code=400,
            code="DATASET_PREVIEW_INVALID",
            message=str(exc),
        )
    except Exception as exc:
        logger.exception(
            "dataset_preview_failed dataset_id=%s data_source_id=%s workspace_id=%s",
            dataset_id,
            ds.data_source_id,
            workspace_id,
        )
        normalized = (
            connector.normalize_error(exc) if hasattr(connector, "normalize_error") else None
        )
        code = (normalized or {}).get("code", "DATASET_PREVIEW_FAILED")
        message = (normalized or {}).get("message", str(exc))
        raise DatasetAPIError(status_code=502, code=code, message=message)

    # 4. Truncate oversized cells and build response payload.
    trimmed, truncated_columns = _truncate_preview_rows(rows)
    columns = list(trimmed[0].keys()) if trimmed else []

    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            {
                "dataset_id": str(dataset_id),
                "schema_name": ds.schema_name,
                "table_name": ds.physical_identifier,
                "row_limit": limit,
                "row_count": len(trimmed),
                "columns": columns,
                "rows": trimmed,
                "truncated_columns": truncated_columns,
            }
        ),
    )


# ---------------------------------------------------------------------------
# PATCH — Update Dataset
# ---------------------------------------------------------------------------


@router.patch(
    "/{dataset_id}",
    status_code=status.HTTP_200_OK,
    summary="Update Dataset",
)
async def update_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    body: PatchDatasetRequest,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)

    # Check immutable fields
    immutable_submitted = []
    if body.dataset_type is not None:
        immutable_submitted.append("dataset_type")
    if body.data_source_id is not None:
        immutable_submitted.append("data_source_id")
    if body.physical_identifier is not None:
        immutable_submitted.append("physical_identifier")
    if immutable_submitted:
        raise DatasetAPIError(
            status_code=400,
            code="IMMUTABLE_FIELD",
            message=f"Fields {immutable_submitted} cannot be changed after creation.",
        )

    try:
        payload = UpdateDatasetPayload(
            dataset_name=body.dataset_name,
            description=body.description,
            business_domain=body.business_domain,
            criticality=body.criticality,
            owner_user_id=UUID(body.owner_user_id) if body.owner_user_id else None,
            freshness_expectation=body.freshness_expectation,
            schema_name=body.schema_name,
        )
        ds = _service.update_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
            payload=payload,
        )
        dataset_update_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_update_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_update_count.labels(workspace_id=wid, result="error").inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    field_count = _get_field_count(db, ds.dataset_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = field_count

    # F052 audit hook (best-effort)
    try:
        _audit_svc.write(
            db,
            build_dataset_audit_entry(
                ctx=AuditContext(
                    tenant_id=_resolve_tenant_id(workspace_id, actor, db),
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role,
                    request_id=None,
                    source_ip=None,
                ),
                action="dataset_updated",
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                after_state={"dataset_id": str(dataset_id), "dataset_name": ds.dataset_name},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=dataset_updated dataset_id=%s", dataset_id)

    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# POST — Activate Dataset
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/activate",
    status_code=status.HTTP_200_OK,
    summary="Activate Dataset",
)
async def activate_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        ds = _service.activate_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
        )
        dataset_activate_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_activate_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_activate_count.labels(workspace_id=wid, result="error").inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    field_count = _get_field_count(db, ds.dataset_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = field_count

    # F052 audit hook (best-effort)
    try:
        _audit_svc.write(
            db,
            build_dataset_audit_entry(
                ctx=AuditContext(
                    tenant_id=_resolve_tenant_id(workspace_id, actor, db),
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role,
                    request_id=None,
                    source_ip=None,
                ),
                action="dataset_activated",
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                after_state={"status": "active"},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=dataset_activated dataset_id=%s", dataset_id)

    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# POST — Deactivate Dataset
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/deactivate",
    status_code=status.HTTP_200_OK,
    summary="Deactivate Dataset",
)
async def deactivate_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_pause_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        ds = _service.deactivate_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
        )
        dataset_deactivate_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_deactivate_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_deactivate_count.labels(workspace_id=wid, result="error").inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    field_count = _get_field_count(db, ds.dataset_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = field_count
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# POST — Reactivate Dataset
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/reactivate",
    status_code=status.HTTP_200_OK,
    summary="Reactivate Dataset",
)
async def reactivate_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        ds = _service.reactivate_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
        )
        dataset_reactivate_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_reactivate_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_reactivate_count.labels(workspace_id=wid, result="error").inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    field_count = _get_field_count(db, ds.dataset_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = field_count
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# POST — Archive Dataset
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="Archive Dataset",
)
async def archive_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_archive_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        ds = _service.archive_dataset(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
        )
        dataset_archive_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_archive_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_archive_count.labels(workspace_id=wid, result="error").inc()
        raise

    ds_name = _get_data_source_name(db, ds.data_source_id)
    field_count = _get_field_count(db, ds.dataset_id)
    result = _serialize_dataset(ds, data_source_name=ds_name)
    result["field_count"] = field_count

    # F052 audit hook (best-effort)
    try:
        _audit_svc.write(
            db,
            build_dataset_audit_entry(
                ctx=AuditContext(
                    tenant_id=_resolve_tenant_id(workspace_id, actor, db),
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role,
                    request_id=None,
                    source_ip=None,
                ),
                action="dataset_deleted",
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                before_state={
                    "status": ds.status.value if hasattr(ds.status, "value") else ds.status
                },
                after_state={"deleted": True},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=dataset_deleted dataset_id=%s", dataset_id)

    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# GET — Audit Logs
# ---------------------------------------------------------------------------

_AUDIT_LOG_SQL = """
SELECT log_id, action_type, actor_id, actor_role,
       new_data, occurred_at
FROM control.workspace_audit_logs
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND (new_data->>'dataset_id') = :dataset_id_str
"""

_AUDIT_LOG_COUNT_SQL = """
SELECT COUNT(*)
FROM control.workspace_audit_logs
WHERE workspace_id = CAST(:workspace_id AS UUID)
  AND (new_data->>'dataset_id') = :dataset_id_str
"""


@router.get(
    "/{dataset_id}/audit-logs",
    status_code=status.HTTP_200_OK,
    summary="Get Dataset Audit Logs",
)
async def get_dataset_audit_logs(
    workspace_id: UUID,
    dataset_id: UUID,
    action_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    # Verify dataset exists in this workspace
    try:
        _service.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))

    params: dict[str, Any] = {
        "workspace_id": str(workspace_id),
        "dataset_id_str": str(dataset_id),
    }

    where_extra = ""
    if action_type:
        where_extra += " AND action_type = :action_type"
        params["action_type"] = action_type

    count_sql = _AUDIT_LOG_COUNT_SQL + where_extra
    total = db.execute(text(count_sql), params).scalar() or 0

    offset = (page - 1) * page_size
    query_sql = (
        _AUDIT_LOG_SQL + where_extra + " ORDER BY occurred_at DESC LIMIT :limit OFFSET :offset"
    )
    params["limit"] = page_size
    params["offset"] = offset

    rows = db.execute(text(query_sql), params).fetchall()
    items = []
    for row in rows:
        new_data = row[4]
        if isinstance(new_data, str):
            import json

            new_data = json.loads(new_data)
        items.append(
            {
                "log_id": str(row[0]),
                "action_type": row[1],
                "actor_id": str(row[2]),
                "actor_role": row[3],
                "new_data": new_data,
                "occurred_at": row[5].isoformat() if row[5] else None,
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


# ===========================================================================
# P07 — Field CRUD and Bulk Import
# ===========================================================================

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AddFieldRequest(BaseModel):
    field_name: str
    data_type: str
    nullable: bool = True
    business_definition: str | None = None
    sensitivity_classification: str = "internal"
    is_key_candidate: bool = False


class PatchFieldRequest(BaseModel):
    data_type: str | None = None
    nullable: bool | None = None
    business_definition: str | None = None
    sensitivity_classification: str | None = None
    is_key_candidate: bool | None = None
    ordinal_position: int | None = None
    # Immutable — captured to return 400
    field_name: str | None = None


class FieldImportItem(BaseModel):
    field_name: str
    data_type: str
    nullable: bool = True
    business_definition: str | None = None
    sensitivity_classification: str = "internal"
    is_key_candidate: bool = False


class BulkImportFieldsRequest(BaseModel):
    mode: str  # "append" | "replace"
    fields: list[FieldImportItem]


# ---------------------------------------------------------------------------
# POST — Add Field
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/fields",
    status_code=status.HTTP_201_CREATED,
    summary="Add a Field to a Dataset",
)
async def add_field(
    workspace_id: UUID,
    dataset_id: UUID,
    body: AddFieldRequest,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    try:
        payload = CreateFieldPayload(
            field_name=body.field_name,
            data_type=body.data_type,
            nullable=body.nullable,
            business_definition=body.business_definition,
            sensitivity_classification=body.sensitivity_classification,
            is_key_candidate=body.is_key_candidate,
        )
        field = _service.add_field(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
            payload=payload,
        )
        dataset_field_add_count.labels(workspace_id=wid, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_field_add_count.labels(workspace_id=wid, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_field_add_count.labels(workspace_id=wid, result="error").inc()
        raise

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=_serialize_field(field))


# ---------------------------------------------------------------------------
# GET — List Fields
# ---------------------------------------------------------------------------


@router.get(
    "/{dataset_id}/fields",
    status_code=status.HTTP_200_OK,
    summary="List Fields for a Dataset",
)
async def list_fields(
    workspace_id: UUID,
    dataset_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        _service.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    fields = _service._field_repo.find_all_by_dataset(db, dataset_id=dataset_id)
    return JSONResponse(
        status_code=200,
        content=[_serialize_field(f) for f in fields],
    )


# ---------------------------------------------------------------------------
# POST — Bulk Import Fields
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/fields/bulk-import",
    status_code=status.HTTP_200_OK,
    summary="Bulk Import Fields for a Dataset",
)
async def bulk_import_fields(
    workspace_id: UUID,
    dataset_id: UUID,
    body: BulkImportFieldsRequest,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    wid = str(workspace_id)
    mode = body.mode
    try:
        field_payloads = [
            CreateFieldPayload(
                field_name=f.field_name,
                data_type=f.data_type,
                nullable=f.nullable,
                business_definition=f.business_definition,
                sensitivity_classification=f.sensitivity_classification,
                is_key_candidate=f.is_key_candidate,
            )
            for f in body.fields
        ]
        result = _service.bulk_import_fields(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            actor_id=actor.actor_id,
            mode=mode,
            fields=field_payloads,
        )
        dataset_field_bulk_import_count.labels(workspace_id=wid, mode=mode, result="success").inc()
    except DatasetNotFoundError as exc:
        dataset_field_bulk_import_count.labels(workspace_id=wid, mode=mode, result="error").inc()
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetAPIError:
        dataset_field_bulk_import_count.labels(workspace_id=wid, mode=mode, result="error").inc()
        raise

    fields = _service._field_repo.find_all_by_dataset(db, dataset_id=dataset_id)
    return JSONResponse(
        status_code=200,
        content={
            "imported_count": result.fields_added,
            "mode": result.mode,
            "fields": [_serialize_field(f) for f in fields],
        },
    )


# ---------------------------------------------------------------------------
# PATCH — Update Field
# ---------------------------------------------------------------------------


@router.patch(
    "/{dataset_id}/fields/{field_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a Dataset Field",
)
async def update_field(
    workspace_id: UUID,
    dataset_id: UUID,
    field_id: UUID,
    body: PatchFieldRequest,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if body.field_name is not None:
        raise DatasetAPIError(
            status_code=400,
            code="IMMUTABLE_FIELD",
            message="field_name cannot be changed after creation.",
        )

    try:
        payload = UpdateFieldPayload(
            data_type=body.data_type,
            nullable=body.nullable,
            business_definition=body.business_definition,
            sensitivity_classification=body.sensitivity_classification,
            is_key_candidate=body.is_key_candidate,
            ordinal_position=body.ordinal_position,
        )
        field = _service.update_field(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            field_id=field_id,
            actor_id=actor.actor_id,
            payload=payload,
        )
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetFieldNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="FIELD_NOT_FOUND", message=str(exc))

    return JSONResponse(status_code=200, content=_serialize_field(field))


# ---------------------------------------------------------------------------
# DELETE — Delete Field
# ---------------------------------------------------------------------------


@router.delete(
    "/{dataset_id}/fields/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Dataset Field",
)
async def delete_field(
    workspace_id: UUID,
    dataset_id: UUID,
    field_id: UUID,
    actor: DatasetActorContext = Depends(verify_dataset_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        _service.remove_field(
            db,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            field_id=field_id,
            actor_id=actor.actor_id,
        )
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))
    except DatasetFieldNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="FIELD_NOT_FOUND", message=str(exc))

    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# F121 — Dataset Profiling
# ---------------------------------------------------------------------------


@router.post(
    "/{dataset_id}/profile",
    status_code=status.HTTP_200_OK,
    summary="Profile a Dataset",
    description="Run column-level profiling against the dataset's underlying table. "
    "Samples up to 10,000 rows and returns statistics per column.",
)
async def profile_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    sample_size: int = Query(10000, ge=100, le=100000, description="Max rows to sample"),
    actor: DatasetActorContext = Depends(verify_dataset_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    import json

    import pandas as pd

    from app.services.datasources.connection_manager import ConnectionManager
    from app.services.ingestion.file_upload import FileUploadService
    from app.services.ingestion.profiler import DataProfiler

    # 1. Load dataset metadata
    try:
        ds = _service.get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    except DatasetNotFoundError as exc:
        raise DatasetAPIError(status_code=404, code="DATASET_NOT_FOUND", message=str(exc))

    # 2. Acquire data either from a connector (data-source backed) or from the
    #    uploaded file (file dataset).
    if ds.data_source_id is None:
        # File-backed dataset — read from MinIO/local via FileUploadService.
        if not ds.physical_identifier:
            raise DatasetAPIError(
                status_code=400,
                code="FILE_DATASET_MISSING_PATH",
                message="File dataset has no physical_identifier (file path).",
            )
        ext = (ds.physical_identifier.rsplit(".", 1)[-1] or "").lower()
        type_map = {
            "csv": "csv",
            "txt": "csv",
            "tsv": "csv",
            "xlsx": "excel",
            "xls": "excel",
            "json": "json",
            "jsonl": "json",
            "parquet": "parquet",
        }
        file_type = type_map.get(ext)
        if file_type is None:
            raise DatasetAPIError(
                status_code=400,
                code="FILE_DATASET_UNSUPPORTED_FORMAT",
                message=f"Cannot profile file with extension .{ext}",
            )
        try:
            file_service = FileUploadService()
            parse_result = file_service.parse_file(
                ds.physical_identifier,
                file_type,
                ds.physical_identifier.rsplit("/", 1)[-1],
            )
            df = parse_result.data
            total_rows = parse_result.row_count or len(df)
        except Exception as exc:
            logger.error("file profiling failed: %s", exc)
            raise DatasetAPIError(
                status_code=502,
                code="PROFILING_FETCH_FAILED",
                message=f"Could not read uploaded file: {exc}",
            )
        if df.empty:
            empty_payload = {
                "dataset_id": str(dataset_id),
                "total_rows": 0,
                "total_columns": 0,
                "columns": [],
                "profiled_at": None,
                "message": "File is empty",
            }
            return JSONResponse(status_code=200, content=empty_payload)
    else:
        resolved = _resolve_connector_config(db, ds.data_source_id, workspace_id)
        if resolved is None:
            raise DatasetAPIError(
                status_code=404,
                code="DATA_SOURCE_NOT_FOUND",
                message="Linked data source not found",
            )
        source_type, connection_config = resolved

        try:
            connector = await ConnectionManager.get_connector(source_type, connection_config)
            async with connector:
                table_name = ds.physical_identifier or ds.dataset_name
                schema_name = ds.schema_name
                rows = await connector.get_sample_data(table_name, schema_name, sample_size)
                total_rows = await connector.get_row_count(table_name, schema_name)
        except Exception as exc:
            logger.exception(
                "profiling_data_fetch_failed dataset_id=%s data_source_id=%s workspace_id=%s err=%s",
                dataset_id,
                ds.data_source_id,
                workspace_id,
                exc,
            )
            raise DatasetAPIError(
                status_code=502,
                code="PROFILING_FETCH_FAILED",
                message=f"Could not read from data source: {exc}",
            )

        if not rows:
            return JSONResponse(
                status_code=200,
                content={
                    "dataset_id": str(dataset_id),
                    "total_rows": 0,
                    "total_columns": 0,
                    "columns": [],
                    "profiled_at": None,
                    "message": "Table is empty or inaccessible",
                },
            )

        df = pd.DataFrame(rows)

    # 3. Profile with DataProfiler
    profiler = DataProfiler()
    profile = profiler.profile_dataframe(df, actual_row_count=total_rows)
    profile["dataset_id"] = str(dataset_id)

    # Coerce non-JSON-native types (Decimal, datetime, UUID, numpy scalars,
    # bytes, ...) into JSON-safe primitives so both the response and the
    # JSONB persistence below succeed.
    profile = jsonable_encoder(profile)

    # 4. Persist profile to enrich dataset metadata.
    try:
        db.execute(
            text(
                """
                UPDATE control.datasets
                   SET last_profile     = CAST(:profile AS JSONB),
                       last_profiled_at = now(),
                       updated_at       = now()
                 WHERE dataset_id = CAST(:dataset_id AS UUID)
                """
            ),
            {"profile": json.dumps(profile), "dataset_id": str(dataset_id)},
        )

        for col in profile.get("columns", []):
            min_v = col.get("min_value")
            max_v = col.get("max_value")
            null_count = int(col.get("null_count") or 0)
            db.execute(
                text(
                    """
                    UPDATE control.dataset_fields
                       SET null_count     = :null_count,
                           distinct_count = :distinct_count,
                           min_value      = :min_value,
                           max_value      = :max_value,
                           profile_stats  = CAST(:stats AS JSONB),
                           profiled_at    = now(),
                           nullable       = CASE WHEN :null_count > 0 THEN true ELSE nullable END,
                           updated_at     = now()
                     WHERE dataset_id = CAST(:dataset_id AS UUID)
                       AND lower(field_name) = lower(:field_name)
                    """
                ),
                {
                    "null_count": null_count,
                    "distinct_count": int(col.get("unique_count") or 0),
                    "min_value": None if min_v is None else str(min_v),
                    "max_value": None if max_v is None else str(max_v),
                    "stats": json.dumps(col),
                    "dataset_id": str(dataset_id),
                    "field_name": col.get("name"),
                },
            )
        db.commit()
    except Exception as exc:  # pragma: no cover — persistence is best-effort
        logger.warning("Failed to persist profile enrichment: %s", exc)
        db.rollback()

    return JSONResponse(status_code=200, content=profile)
