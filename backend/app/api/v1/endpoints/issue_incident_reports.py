"""
F050 — Issue and Incident Report API Endpoints
================================================

Routes:
  GET /api/v1/workspaces/{workspace_id}/reports/issues/summary      — full issue dashboard
  GET /api/v1/workspaces/{workspace_id}/reports/issues/by-status     — issue counts by status
  GET /api/v1/workspaces/{workspace_id}/reports/issues/by-severity   — issue counts by severity
  GET /api/v1/workspaces/{workspace_id}/reports/incidents/summary    — full incident dashboard
  GET /api/v1/workspaces/{workspace_id}/reports/incidents/by-status  — incident counts by status
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.reporting.incident_report_service import IncidentReportService
from app.services.reporting.issue_report_service import IssueReportService
from app.services.reporting.report_csv_service import ReportCsvService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/reports",
    tags=["reports"],
)

_issue_svc = IssueReportService()
_incident_svc = IncidentReportService()
_csv_svc = ReportCsvService()


# ---------------------------------------------------------------------------
# Issue Reports
# ---------------------------------------------------------------------------


@router.get(
    "/issues/summary",
    dependencies=[Depends(require_workspace_permission("issues:read"))],
)
async def get_issue_summary(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
):
    summary = _issue_svc.dashboard_summary(db, workspace_id)
    return JSONResponse(
        status_code=200,
        content={
            "status_counts": summary.status_counts.dict(),
            "severity_counts": summary.severity_counts.dict(),
            "overdue_count": summary.overdue_count,
            "resolution_stats": summary.resolution_stats.dict(),
        },
    )


@router.get(
    "/issues/by-status",
    dependencies=[Depends(require_workspace_permission("issues:read"))],
)
async def get_issues_by_status(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
):
    counts = _issue_svc.count_by_status(db, workspace_id)
    return JSONResponse(status_code=200, content=counts.dict())


@router.get(
    "/issues/by-severity",
    dependencies=[Depends(require_workspace_permission("issues:read"))],
)
async def get_issues_by_severity(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
):
    counts = _issue_svc.count_by_severity(db, workspace_id)
    return JSONResponse(status_code=200, content=counts.dict())


# ---------------------------------------------------------------------------
# Incident Reports
# ---------------------------------------------------------------------------


@router.get(
    "/incidents/summary",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
)
async def get_incident_summary(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
):
    summary = _incident_svc.dashboard_summary(db, workspace_id)
    return JSONResponse(
        status_code=200,
        content={
            "status_counts": summary.status_counts.dict(),
            "severity_counts": summary.severity_counts.dict(),
            "priority_counts": summary.priority_counts.dict(),
            "sla_breach_count": summary.sla_breach_count,
            "resolution_stats": summary.resolution_stats.dict(),
        },
    )


@router.get(
    "/incidents/by-status",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
)
async def get_incidents_by_status(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
):
    counts = _incident_svc.count_by_status(db, workspace_id)
    return JSONResponse(status_code=200, content=counts.dict())


# ---------------------------------------------------------------------------
# CSV Exports (F051)
# ---------------------------------------------------------------------------


@router.get(
    "/issues/export",
    dependencies=[Depends(require_workspace_permission("issues:read"))],
    summary="Export Issue Summary CSV",
)
async def export_issue_summary_csv(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
) -> Response:
    summary = _issue_svc.dashboard_summary(db, workspace_id)
    body = _csv_svc.issue_summary_csv(summary)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"issue_summary_{ts}.csv"

    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/incidents/export",
    dependencies=[Depends(require_workspace_permission("incidents:read"))],
    summary="Export Incident Summary CSV",
)
async def export_incident_summary_csv(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("incidents:read")),
    db: Session = Depends(get_db),
) -> Response:
    summary = _incident_svc.dashboard_summary(db, workspace_id)
    body = _csv_svc.incident_summary_csv(summary)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"incident_summary_{ts}.csv"

    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
