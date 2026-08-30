"""
F057 — Read-Only Entity API Endpoints (Token-Authenticated)
=============================================================

Provides read-only list endpoints for core entities, authenticated via
Personal Access Tokens (F056) with scope enforcement.

Routes:
  GET /api/v1/api/workspaces/{workspace_id}/datasets     — read:datasets
  GET /api/v1/api/workspaces/{workspace_id}/rules   — read:rules
  GET /api/v1/api/workspaces/{workspace_id}/executions — read:executions
  GET /api/v1/api/workspaces/{workspace_id}/issues        — read:issues
  GET /api/v1/api/workspaces/{workspace_id}/incidents      — read:incidents
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.access_token import AccessToken
from app.models.database import get_db
from app.services.auth.api_token_auth import ScopeChecker, get_api_token
from app.services.datasets.models import DatasetListFilters
from app.services.datasets.service import DatasetService
from app.services.incidents.incident_list_service import IncidentListService
from app.services.issues.issue_repository import IssueRepository
from app.services.rules.service import RuleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api-entities"])

# Shared service instances
_dataset_svc = DatasetService()
_issue_repo = IssueRepository()
_incident_svc = IncidentListService()


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/datasets",
    summary="List datasets (token auth)",
    dependencies=[Depends(ScopeChecker("read:datasets"))],
)
async def list_datasets(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    offset = (page - 1) * page_size
    filters = DatasetListFilters(
        status=status_filter,
        search=search,
        limit=page_size,
        offset=offset,
    )
    result = _dataset_svc.list_datasets(db, workspace_id=workspace_id, filters=filters)
    items = []
    for item in result.items:
        items.append(
            {
                "id": str(item.id),
                "name": item.name,
                "status": item.status,
                "dataset_type": getattr(item, "dataset_type", None),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )
    return JSONResponse(
        status_code=200,
        content={
            "items": items,
            "total": result.total_count,
            "page": page,
            "page_size": page_size,
        },
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/rules",
    summary="List rules (token auth)",
    dependencies=[Depends(ScopeChecker("read:rules"))],
)
async def list_rules(
    workspace_id: UUID,
    category: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    rules = await service.list_rules(
        workspace_id=workspace_id,
        category=category,
        search=search,
        skip=skip,
        limit=limit,
    )
    return rules


# ---------------------------------------------------------------------------
# Executions (rule executions)
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/rules/{rule_id}/executions",
    summary="List rule executions (token auth)",
    dependencies=[Depends(ScopeChecker("read:executions"))],
)
async def list_executions(
    workspace_id: UUID,
    rule_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    executions = await service.get_execution_history(
        rule_id=rule_id,
        workspace_id=workspace_id,
        skip=skip,
        limit=limit,
    )
    return executions


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/issues",
    summary="List issues (token auth)",
    dependencies=[Depends(ScopeChecker("read:issues"))],
)
async def list_issues(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    items, total = _issue_repo.list_by_workspace(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        page=page,
        page_size=page_size,
    )

    return JSONResponse(
        status_code=200,
        content={
            "items": [
                {
                    "id": str(i.id),
                    "severity": i.severity,
                    "status": i.status,
                    "title": i.title,
                    "opened_at": i.opened_at.isoformat() if i.opened_at else None,
                }
                for i in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": total > page * page_size,
        },
    )


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/incidents",
    summary="List incidents (token auth)",
    dependencies=[Depends(ScopeChecker("read:incidents"))],
)
async def list_incidents(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = _incident_svc.list_incidents(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    items = []
    for i in result.items:
        items.append(
            {
                "id": str(i.id),
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "priority": i.priority,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
        )
    return JSONResponse(
        status_code=200,
        content={
            "items": items,
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "has_next": result.has_next,
        },
    )
