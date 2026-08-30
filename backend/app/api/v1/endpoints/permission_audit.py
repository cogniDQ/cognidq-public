"""
F008 — Permission Audit Visibility — API Endpoints
====================================================

Routes:
  GET /api/v1/workspaces/{workspace_id}/audit/permissions        — paginated list
  GET /api/v1/workspaces/{workspace_id}/audit/permissions/export — CSV export

Auth: Bearer JWT
Permission required: view_audit_logs on the target workspace
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.schemas.permission_audit import (
    ACCESS_CONTROL_ACTION_TYPES,
    PermissionAuditExportQueryParams,
    PermissionAuditQueryParams,
)
from app.services.permission_audit import metrics as pa_metrics
from app.services.permission_audit.service import PermissionAuditService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/audit",
    tags=["permission-audit"],
)

_svc = PermissionAuditService()
_SORTED_ACTION_TYPES: list[str] = sorted(ACCESS_CONTROL_ACTION_TYPES)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error(
    code: str,
    message: str,
    http_status: int,
    field: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message, "field": field}},
    )


def _build_filter_error(exc: ValidationError, action_type_raw: str | None) -> JSONResponse:
    """Convert a Pydantic ValidationError from filter construction to HTTP 400."""
    errors = exc.errors()
    first = errors[0]
    loc = first.get("loc", ())
    field_name = str(loc[-1]) if loc else "unknown"
    msg: str = first.get("msg", "Invalid parameter")

    if "action_type" in field_name:
        msg = (
            f"Invalid action_type '{action_type_raw}'. "
            f"Must be one of: {', '.join(_SORTED_ACTION_TYPES)}"
        )
    elif "to_date" in field_name or "date_range" in field_name.lower():
        msg = "to_date must not be earlier than from_date"
    elif "actor_id" in field_name or "target_entity_id" in field_name:
        msg = f"Invalid UUID value for '{field_name}'"
    elif "from_date" in field_name or "to_date" in field_name:
        msg = f"Unparseable datetime value for '{field_name}'"

    return _error("INVALID_PARAM", msg, 400, field_name)


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/audit/permissions — list
# ---------------------------------------------------------------------------


@router.get(
    "/permissions",
    summary="List permission audit entries",
    status_code=200,
)
async def list_permission_audit(
    request: Request,
    workspace_id: UUID,
    # Filter params declared as Optional[str] so Pydantic handles UUID/datetime
    # parsing and we can return 400 (not 422) on validation failure.
    actor_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    target_entity_id: str | None = Query(default=None),
    target_entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
) -> JSONResponse:
    t0 = time.monotonic()

    try:
        filters = PermissionAuditQueryParams(
            actor_id=actor_id,
            action_type=action_type,
            target_entity_id=target_entity_id,
            target_entity_type=target_entity_type,
            from_date=from_date,
            to_date=to_date,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        pa_metrics.list_requests_total.labels(workspace_id=str(workspace_id), result="error").inc()
        return _build_filter_error(exc, action_type)

    result = _svc.get_page(db, actor.tenant_id, workspace_id, filters)
    duration_ms = (time.monotonic() - t0) * 1000

    pa_metrics.list_requests_total.labels(workspace_id=str(workspace_id), result="ok").inc()
    pa_metrics.query_duration_ms.labels(endpoint="list").observe(duration_ms)

    logger.info(
        "permission_audit_list",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "tenant_id": str(actor.tenant_id),
            "workspace_id": str(workspace_id),
            "actor_id": str(actor.actor_id),
            "endpoint": "permission_audit_list",
            "result": "ok",
            "total_records": result.total,
            "page": filters.page,
            "page_size": filters.page_size,
            "duration_ms": round(duration_ms, 1),
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "items": [
                {
                    "log_id": str(item.log_id),
                    "occurred_at": item.occurred_at.isoformat(),
                    "action_type": item.action_type,
                    "actor_id": str(item.actor_id) if item.actor_id else None,
                    "actor_display_name": item.actor_display_name,
                    "actor_role": item.actor_role,
                    "actor_type": item.actor_type,
                    "target_entity_type": item.target_entity_type,
                    "target_entity_id": (
                        str(item.target_entity_id) if item.target_entity_id else None
                    ),
                    "target_display_name": item.target_display_name,
                    "workspace_id": (str(item.workspace_id) if item.workspace_id else None),
                    "request_id": (str(item.request_id) if item.request_id else None),
                }
                for item in result.items
            ],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "has_next": result.has_next,
        },
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/audit/permissions/export — CSV export
# ---------------------------------------------------------------------------


@router.get(
    "/permissions/export",
    summary="Export permission audit entries as CSV",
    status_code=200,
)
async def export_permission_audit(
    request: Request,
    workspace_id: UUID,
    actor_id: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    target_entity_id: str | None = Query(default=None),
    target_entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
) -> Response:
    t0 = time.monotonic()

    try:
        filters = PermissionAuditExportQueryParams(
            actor_id=actor_id,
            action_type=action_type,
            target_entity_id=target_entity_id,
            target_entity_type=target_entity_type,
            from_date=from_date,
            to_date=to_date,
        )
    except ValidationError as exc:
        pa_metrics.export_requests_total.labels(
            workspace_id=str(workspace_id), result="error", truncated="false"
        ).inc()
        return _build_filter_error(exc, action_type)

    rows = _svc.build_export_rows(db, actor.tenant_id, workspace_id, filters)
    columns = _svc.export_columns()
    duration_ms = (time.monotonic() - t0) * 1000

    # Detect truncation (last row is the notice row if present)
    truncated = bool(rows) and rows[-1].get("log_id", "").startswith("# NOTE:")
    export_row_count = len(rows) - (1 if truncated else 0)

    pa_metrics.export_requests_total.labels(
        workspace_id=str(workspace_id),
        result="ok",
        truncated=str(truncated).lower(),
    ).inc()
    pa_metrics.query_duration_ms.labels(endpoint="export").observe(duration_ms)

    logger.info(
        "permission_audit_export",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "tenant_id": str(actor.tenant_id),
            "workspace_id": str(workspace_id),
            "actor_id": str(actor.actor_id),
            "endpoint": "permission_audit_export",
            "result": "ok",
            "export_row_count": export_row_count,
            "truncated": truncated,
            "duration_ms": round(duration_ms, 1),
        },
    )

    # Build CSV in memory; encode as utf-8-sig to prepend BOM bytes (\xef\xbb\xbf)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8-sig")

    ts = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H%M%SZ")
    filename = f"permission_audit_{ts}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
