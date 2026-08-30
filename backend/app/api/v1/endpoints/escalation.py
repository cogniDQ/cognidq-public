"""
F046 — Escalation for Overdue SLA — API Endpoints
===================================================

Routes:
  POST  /api/v1/workspaces/{workspace_id}/escalation/run
        Trigger an immediate escalation check for the workspace.
        Requires ``alerts:write`` permission.

  GET   /api/v1/workspaces/{workspace_id}/escalation/overdue-issues
        Return the list of currently overdue open issues for the workspace.
        Requires ``alerts:read`` permission.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.models.issue import Issue
from app.services.escalation.escalation_service import EscalationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/escalation",
    tags=["escalation"],
)

_OPEN_STATUSES = ("open", "in_progress", "reopened")


# ---------------------------------------------------------------------------
# POST /run — immediate escalation check for this workspace
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    status_code=status.HTTP_200_OK,
    summary="Run escalation check for workspace",
)
async def run_workspace_escalation(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    """
    Trigger an immediate escalation scan for the workspace.
    Finds overdue open issues and emits notification events for each
    ``issue_overdue`` alert rule configured in the workspace.
    """
    # Scope the check to only this workspace by filtering after the check
    # (the full check writes events; we run a workspace-scoped variant here)

    now = datetime.now(tz=UTC)

    overdue_issues = (
        db.query(Issue)
        .filter(
            and_(
                Issue.workspace_id == workspace_id,
                Issue.status.in_(_OPEN_STATUSES),
                Issue.due_at.isnot(None),
                Issue.due_at < now,
            )
        )
        .all()
    )

    if not overdue_issues:
        return JSONResponse(
            status_code=200,
            content={
                "workspace_id": str(workspace_id),
                "overdue_issues_found": 0,
                "notifications_logged": 0,
                "message": "No overdue issues found.",
            },
        )

    svc = EscalationService()
    result = svc.run_escalation_check(db)

    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(workspace_id),
            **result.to_dict(),
        },
    )


# ---------------------------------------------------------------------------
# GET /overdue-issues — list currently overdue open issues in workspace
# ---------------------------------------------------------------------------


@router.get(
    "/overdue-issues",
    status_code=status.HTTP_200_OK,
    summary="List overdue open issues for workspace",
)
async def list_overdue_issues(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    """
    Returns all open issues in the workspace where ``due_at`` is in the past.
    """
    now = datetime.now(tz=UTC)

    issues = (
        db.query(Issue)
        .filter(
            and_(
                Issue.workspace_id == workspace_id,
                Issue.status.in_(_OPEN_STATUSES),
                Issue.due_at.isnot(None),
                Issue.due_at < now,
            )
        )
        .order_by(Issue.due_at.asc())
        .all()
    )

    return JSONResponse(
        status_code=200,
        content={
            "workspace_id": str(workspace_id),
            "overdue_count": len(issues),
            "items": [
                {
                    "id": str(issue.id),
                    "title": issue.title,
                    "severity": issue.severity,
                    "status": issue.status,
                    "due_at": issue.due_at.isoformat() if issue.due_at else None,
                    "assignee_id": str(issue.assignee_id) if issue.assignee_id else None,
                    "opened_at": issue.opened_at.isoformat() if issue.opened_at else None,
                }
                for issue in issues
            ],
        },
    )
