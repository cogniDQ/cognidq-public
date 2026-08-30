"""
F038/F040/F041/F042 — Incident API Endpoints
===============================================

Routes:
  GET    /api/v1/workspaces/{workspace_id}/incidents                       — list incidents
  POST   /api/v1/workspaces/{workspace_id}/incidents                       — create incident
  PATCH  /api/v1/workspaces/{workspace_id}/incidents/{incident_id}         — update incident
  POST   /api/v1/workspaces/{workspace_id}/incidents/{incident_id}/links   — add issue links
  DELETE /api/v1/workspaces/{workspace_id}/incidents/{incident_id}/links   — remove issue links

Auth:
  Write endpoints require ``incidents:write``.
  Read endpoints require ``incidents:read``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.audit.models import AuditContext
from app.services.incidents.incident_csv_service import IncidentCsvService
from app.services.incidents.incident_lifecycle_service import (
    EmptyUpdateError,
    IncidentLifecycleService,
    IncidentNotFoundError,
    InvalidStatusTransitionError,
    ResolutionSummaryRequiredError,
)
from app.services.incidents.incident_link_service import (
    IncidentLinkService,
    MinimumLinkError,
)
from app.services.incidents.incident_link_service import (
    IncidentNotFoundError as LinkNotFoundError,
)
from app.services.incidents.incident_link_service import (
    IssueNotFoundError as LinkIssueNotFoundError,
)
from app.services.incidents.incident_list_service import IncidentListService
from app.services.incidents.incident_models import (
    CreateIncidentRequest,
    LinkIssuesRequest,
    UpdateIncidentRequest,
)
from app.services.incidents.incident_repository import IncidentRepository
from app.services.incidents.incident_service import (
    IncidentService,
    IncidentValidationError,
    IssueNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/incidents",
    tags=["incidents"],
)

_svc = IncidentService()
_lifecycle_svc = IncidentLifecycleService()
_link_svc = IncidentLinkService()
_list_svc = IncidentListService()
_csv_svc = IncidentCsvService()
_repo = IncidentRepository()

_PLATFORM_ROLES = frozenset({"platform_admin", "platform_viewer"})


def _resolve_tenant_id(workspace_id: UUID, actor: WorkspaceActorContext, db: Session) -> UUID:
    """Return the workspace's tenant_id.

    Platform admins have no tenant_id on their user row, so we always look up
    the owning tenant from the workspace record.  Regular workspace actors
    already carry their tenant_id in the JWT.
    """
    is_platform_op = (actor.actor_role or "") in _PLATFORM_ROLES
    if not is_platform_op and actor.tenant_id:
        return actor.tenant_id
    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid LIMIT 1"),
        {"wid": str(workspace_id)},
    ).fetchone()
    if not row or not row.tenant_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return row.tenant_id


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/incidents
# ---------------------------------------------------------------------------


@router.get(
    "",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
)
async def list_incidents(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    priority: str | None = Query(None),
    owner_id: UUID | None = Query(None),
):
    """List incidents in a workspace with optional filters and SLA info."""
    result = _list_svc.list_incidents(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        priority=priority,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )
    return JSONResponse(status_code=200, content=_serialize_page(result))


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/incidents/export  — F051
# ---------------------------------------------------------------------------


@router.get(
    "/export",
    status_code=status.HTTP_200_OK,
    summary="Export Incidents CSV",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
)
async def export_incidents_csv(
    workspace_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    priority: str | None = Query(None),
    owner_id: UUID | None = Query(None),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
) -> Response:
    items, truncated = _repo.list_all_for_export(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        priority=priority,
        owner_id=owner_id,
    )

    body = _csv_svc.generate_csv(items, truncated=truncated)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"incidents_export_{ts}.csv"

    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/incidents
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_workspace_permission("incidents:write"))],
)
async def create_incident(
    workspace_id: UUID,
    body: CreateIncidentRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:write")),
    db: Session = Depends(get_db),
):
    """Create a new incident from one or more existing issues."""
    # Resolve tenant_id once — platform admins have no tenant on their user row.
    resolved_tenant_id = _resolve_tenant_id(workspace_id, actor, db)
    audit_ctx = AuditContext(
        tenant_id=resolved_tenant_id,
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )

    try:
        resp = _svc.create_incident(
            db,
            workspace_id=workspace_id,
            tenant_id=resolved_tenant_id,
            created_by_user_id=actor.actor_id,
            title=body.title,
            severity=body.severity,
            priority=body.priority,
            impact_summary=body.impact_summary,
            owner_id=body.owner_id,
            issue_ids=body.issue_ids,
            audit_ctx=audit_ctx,
        )
        db.commit()
    except IssueNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except IncidentValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(
        status_code=201,
        content=_serialize_response(resp),
    )


# ---------------------------------------------------------------------------
# PATCH /workspaces/{workspace_id}/incidents/{incident_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{incident_id}",
    dependencies=[Depends(require_workspace_permission("incidents:write"))],
)
async def update_incident(
    workspace_id: UUID,
    incident_id: UUID,
    body: UpdateIncidentRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:write")),
    db: Session = Depends(get_db),
):
    """Update an existing incident (status transition, owner change, etc.)."""
    audit_ctx = AuditContext(
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )

    try:
        resp = _lifecycle_svc.update_incident(
            db,
            incident_id,
            workspace_id,
            fields_provided=body.model_fields_set,
            status=body.status,
            owner_id=body.owner_id,
            impact_summary=body.impact_summary,
            resolution_summary=body.resolution_summary,
            audit_ctx=audit_ctx,
        )
        db.commit()
    except IncidentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidStatusTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except (ResolutionSummaryRequiredError, EmptyUpdateError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(status_code=200, content=_serialize_response(resp))


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/incidents/{incident_id}  — C2 detail drawer
# ---------------------------------------------------------------------------


@router.get(
    "/{incident_id}",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
)
async def get_incident_detail(
    workspace_id: UUID,
    incident_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
):
    """Return full incident details: metadata, linked issues, activity timeline."""
    from sqlalchemy import text

    inc = _repo.get_by_id_and_workspace(db, incident_id, workspace_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    # Owner / creator display names
    owner_name = None
    creator_name = None
    if inc.owner_id is not None or inc.created_by_user_id is not None:
        ids = [str(uid) for uid in (inc.owner_id, inc.created_by_user_id) if uid]
        if ids:
            rows = db.execute(
                text("SELECT id, full_name, email FROM users WHERE id = ANY(CAST(:ids AS UUID[]))"),
                {"ids": "{" + ",".join(ids) + "}"},
            ).fetchall()
            by_id = {str(r[0]): (r[1] or r[2]) for r in rows}
            if inc.owner_id is not None:
                owner_name = by_id.get(str(inc.owner_id))
            if inc.created_by_user_id is not None:
                creator_name = by_id.get(str(inc.created_by_user_id))

    # Linked issues — title + status + severity + dataset/rule context
    issue_rows = db.execute(
        text(
            """
            SELECT i.id, i.title, i.status, i.severity,
                   d.dataset_name, r.name AS rule_name,
                   i.opened_at, i.due_at, i.assignee_id
            FROM incident_issues ii
            JOIN issues i ON i.id = ii.issue_id
            LEFT JOIN control.datasets d ON d.dataset_id = i.dataset_id
            LEFT JOIN dq_rules r ON r.id = i.rule_id
            WHERE ii.incident_id = :iid
            ORDER BY i.opened_at DESC
            """
        ),
        {"iid": str(incident_id)},
    ).fetchall()
    linked_issues = [
        {
            "id": str(r[0]),
            "title": r[1],
            "status": r[2],
            "severity": r[3],
            "dataset_name": r[4],
            "rule_name": r[5],
            "opened_at": r[6].isoformat() if r[6] else None,
            "due_at": r[7].isoformat() if r[7] else None,
            "assignee_id": str(r[8]) if r[8] else None,
        }
        for r in issue_rows
    ]

    # Activity timeline — audit_logs filtered to this incident
    timeline_rows = db.execute(
        text(
            """
            SELECT log_id, occurred_at, action_type, actor_id, actor_role
            FROM control.workspace_audit_logs
            WHERE target_entity_type = 'incident'
              AND target_entity_id = CAST(:iid AS UUID)
              AND tenant_id = CAST(:tid AS UUID)
            ORDER BY occurred_at DESC
            LIMIT 200
            """
        ),
        {"iid": str(incident_id), "tid": str(inc.tenant_id)},
    ).fetchall()

    actor_ids = list({str(r[3]) for r in timeline_rows if r[3]})
    actor_names: dict[str, str] = {}
    if actor_ids:
        rows = db.execute(
            text("SELECT id, full_name, email FROM users WHERE id = ANY(CAST(:ids AS UUID[]))"),
            {"ids": "{" + ",".join(actor_ids) + "}"},
        ).fetchall()
        actor_names = {str(r[0]): (r[1] or r[2]) for r in rows}

    activity = [
        {
            "log_id": str(r[0]),
            "occurred_at": r[1].isoformat() if r[1] else None,
            "action_type": r[2],
            "actor_id": str(r[3]) if r[3] else None,
            "actor_name": actor_names.get(str(r[3])) if r[3] else None,
            "actor_role": r[4],
        }
        for r in timeline_rows
    ]

    return JSONResponse(
        status_code=200,
        content={
            "id": str(inc.id),
            "workspace_id": str(inc.workspace_id),
            "tenant_id": str(inc.tenant_id),
            "title": inc.title,
            "severity": inc.severity,
            "priority": inc.priority,
            "status": inc.status,
            "impact_summary": inc.impact_summary,
            "resolution_summary": inc.resolution_summary,
            "owner_id": str(inc.owner_id) if inc.owner_id else None,
            "owner_name": owner_name,
            "created_by_user_id": str(inc.created_by_user_id) if inc.created_by_user_id else None,
            "created_by_name": creator_name,
            "external_ticket_id": inc.external_ticket_id,
            "external_ticket_url": inc.external_ticket_url,
            "opened_at": inc.opened_at.isoformat() if inc.opened_at else None,
            "acknowledged_at": inc.acknowledged_at.isoformat() if inc.acknowledged_at else None,
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            "closed_at": inc.closed_at.isoformat() if inc.closed_at else None,
            "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
            "linked_issues": linked_issues,
            "activity": activity,
        },
    )


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/incidents/{incident_id}/links
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}/links",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_workspace_permission("incidents:write"))],
)
async def add_incident_links(
    workspace_id: UUID,
    incident_id: UUID,
    body: LinkIssuesRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:write")),
    db: Session = Depends(get_db),
):
    """Add issue links to an existing incident."""
    audit_ctx = AuditContext(
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )

    try:
        resp = _link_svc.add_links(
            db,
            incident_id,
            workspace_id,
            issue_ids=body.issue_ids,
            actor_id=actor.actor_id,
            audit_ctx=audit_ctx,
        )
        db.commit()
    except LinkNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except LinkIssueNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))

    return JSONResponse(status_code=201, content=_serialize_link_response(resp))


# ---------------------------------------------------------------------------
# DELETE /workspaces/{workspace_id}/incidents/{incident_id}/links
# ---------------------------------------------------------------------------


@router.delete(
    "/{incident_id}/links",
    dependencies=[Depends(require_workspace_permission("incidents:write"))],
)
async def remove_incident_links(
    workspace_id: UUID,
    incident_id: UUID,
    body: LinkIssuesRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:write")),
    db: Session = Depends(get_db),
):
    """Remove issue links from an existing incident."""
    audit_ctx = AuditContext(
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )

    try:
        resp = _link_svc.remove_links(
            db,
            incident_id,
            workspace_id,
            issue_ids=body.issue_ids,
            audit_ctx=audit_ctx,
        )
        db.commit()
    except LinkNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except MinimumLinkError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))

    return JSONResponse(status_code=200, content=_serialize_link_response(resp))


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def _serialize_response(resp):
    return {
        "id": str(resp.id),
        "workspace_id": str(resp.workspace_id),
        "title": resp.title,
        "severity": resp.severity,
        "priority": resp.priority,
        "status": resp.status,
        "impact_summary": resp.impact_summary,
        "resolution_summary": resp.resolution_summary,
        "owner_id": str(resp.owner_id) if resp.owner_id else None,
        "owner_name": resp.owner_name,
        "created_by_user_id": str(resp.created_by_user_id) if resp.created_by_user_id else None,
        "created_by_name": resp.created_by_name,
        "issue_count": resp.issue_count,
        "opened_at": resp.opened_at.isoformat(),
    }


def _serialize_link_response(resp):
    return {
        "incident_id": str(resp.incident_id),
        "issue_count": resp.issue_count,
        "linked_issue_ids": [str(i) for i in resp.linked_issue_ids],
    }


def _serialize_page(page):
    return {
        "items": [_serialize_list_item(i) for i in page.items],
        "total": page.total,
        "page": page.page,
        "page_size": page.page_size,
        "has_next": page.has_next,
    }


def _serialize_list_item(item):
    return {
        "id": str(item.id),
        "title": item.title,
        "severity": item.severity,
        "priority": item.priority,
        "status": item.status,
        "impact_summary": item.impact_summary,
        "owner_id": str(item.owner_id) if item.owner_id else None,
        "owner_name": item.owner_name,
        "created_by_name": item.created_by_name,
        "issue_count": item.issue_count,
        "has_sla_breach": item.has_sla_breach,
        "earliest_due_at": item.earliest_due_at.isoformat() if item.earliest_due_at else None,
        "opened_at": item.opened_at.isoformat(),
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "closed_at": item.closed_at.isoformat() if item.closed_at else None,
    }
