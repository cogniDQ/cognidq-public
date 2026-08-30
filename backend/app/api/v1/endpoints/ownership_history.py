"""
F055 — Ownership History and Accountability Trace — API Endpoints
=================================================================

Routes:
  GET /api/v1/workspaces/{workspace_id}/ownership-history
      Return paginated audit-log events that represent ownership or
      accountability changes (issue assignments, incident owner changes,
      workspace role grants / revocations).

Query parameters:
  entity_type  — filter to a specific entity type (e.g. "issue", "incident")
  entity_id    — filter to a specific entity UUID
  action_type  — further narrow to one ownership action type
  page         — 1-based page number (default 1)
  page_size    — items per page (default 25, max 100)

Auth: Bearer JWT
Permission required: ``view_audit_logs`` on the target workspace
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.ownership.ownership_history_models import OwnershipHistoryQueryParams
from app.services.ownership.ownership_history_service import OwnershipHistoryService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["ownership-history"],
)

_svc = OwnershipHistoryService()

_MAX_PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/ownership-history
# ---------------------------------------------------------------------------


@router.get(
    "/ownership-history",
    summary="List ownership and accountability history",
    status_code=200,
)
async def list_ownership_history(
    workspace_id: UUID,
    entity_type: str | None = Query(
        default=None, description="Filter by entity type (e.g. issue, incident)"
    ),
    entity_id: UUID | None = Query(default=None, description="Filter by specific entity UUID"),
    action_type: str | None = Query(default=None, description="Filter by action type"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=25, ge=1, le=_MAX_PAGE_SIZE, description="Items per page"),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Return a paginated list of ownership and accountability events for the
    workspace: issue assignments, incident owner changes, and workspace role
    grants / revocations.

    All events come from the immutable ``workspace_audit_logs`` table (F052).
    """
    try:
        filters = OwnershipHistoryQueryParams(
            entity_type=entity_type,
            entity_id=entity_id,
            action_type=action_type,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        errors = exc.errors()
        first = errors[0]
        loc = first.get("loc", ())
        field = str(loc[-1]) if loc else "unknown"
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_PARAM",
                    "message": first.get("msg", "Invalid parameter"),
                    "field": field,
                }
            },
        )

    page_result = _svc.get_page(
        db,
        tenant_id=actor.tenant_id,
        workspace_id=workspace_id,
        filters=filters,
    )

    return JSONResponse(
        status_code=200,
        content={
            "items": [
                {
                    "log_id": str(ev.log_id),
                    "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                    "action_type": ev.action_type,
                    "target_entity_type": ev.target_entity_type,
                    "target_entity_id": str(ev.target_entity_id) if ev.target_entity_id else None,
                    "actor_id": str(ev.actor_id) if ev.actor_id else None,
                    "actor_role": ev.actor_role,
                    "actor_type": ev.actor_type,
                    "actor_display_name": ev.actor_display_name,
                    "previous_data": ev.previous_data,
                    "new_data": ev.new_data,
                    "request_id": str(ev.request_id) if ev.request_id else None,
                }
                for ev in page_result.items
            ],
            "total": page_result.total,
            "page": page_result.page,
            "page_size": page_result.page_size,
            "has_next": page_result.has_next,
        },
    )
