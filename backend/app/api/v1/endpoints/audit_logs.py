"""
F053 — Audit Log Search — API Endpoints
==========================================

Routes:
  GET /api/v1/workspaces/{workspace_id}/audit/logs        — paginated search
  GET /api/v1/workspaces/{workspace_id}/audit/logs/export  — CSV export

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
from app.services.audit.search_models import AuditLogQueryParams
from app.services.audit.search_service import AuditLogSearchService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/audit",
    tags=["audit-logs"],
)

_svc = AuditLogSearchService()


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


def _build_filter_error(exc: ValidationError) -> JSONResponse:
    """Convert a Pydantic ValidationError to HTTP 400."""
    errors = exc.errors()
    first = errors[0]
    loc = first.get("loc", ())
    field_name = str(loc[-1]) if loc else "unknown"
    msg: str = first.get("msg", "Invalid parameter")
    return _error("INVALID_PARAM", msg, 400, field_name)


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/audit/logs — paginated search
# ---------------------------------------------------------------------------


@router.get(
    "/logs",
    summary="Search audit log entries",
    status_code=200,
)
async def list_audit_logs(
    request: Request,
    workspace_id: UUID,
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
) -> JSONResponse:
    t0 = time.monotonic()

    try:
        filters = AuditLogQueryParams(
            action_type=action_type,
            entity_type=entity_type,
            actor_id=actor_id,
            from_date=from_date,
            to_date=to_date,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        return _build_filter_error(exc)

    result = _svc.get_page(db, actor.tenant_id, workspace_id, filters)
    duration_ms = (time.monotonic() - t0) * 1000

    logger.info(
        "audit_log_search",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "tenant_id": str(actor.tenant_id),
            "workspace_id": str(workspace_id),
            "actor_id": str(actor.actor_id),
            "endpoint": "audit_log_list",
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
# GET /workspaces/{workspace_id}/audit/logs/export — CSV export
# ---------------------------------------------------------------------------


@router.get(
    "/logs/export",
    summary="Export audit log entries as CSV",
    status_code=200,
)
async def export_audit_logs(
    request: Request,
    workspace_id: UUID,
    action_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
) -> Response:
    t0 = time.monotonic()

    try:
        filters = AuditLogQueryParams(
            action_type=action_type,
            entity_type=entity_type,
            actor_id=actor_id,
            from_date=from_date,
            to_date=to_date,
        )
    except ValidationError as exc:
        return _build_filter_error(exc)

    rows = _svc.build_export_rows(db, actor.tenant_id, workspace_id, filters)
    columns = _svc.export_columns()
    duration_ms = (time.monotonic() - t0) * 1000

    truncated = bool(rows) and rows[-1].get("log_id", "").startswith("# NOTE:")

    logger.info(
        "audit_log_export",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "tenant_id": str(actor.tenant_id),
            "workspace_id": str(workspace_id),
            "actor_id": str(actor.actor_id),
            "endpoint": "audit_log_export",
            "result": "ok",
            "export_row_count": len(rows) - (1 if truncated else 0),
            "truncated": truncated,
            "duration_ms": round(duration_ms, 1),
        },
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8-sig")

    ts = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H%M%SZ")
    filename = f"audit_logs_{ts}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
