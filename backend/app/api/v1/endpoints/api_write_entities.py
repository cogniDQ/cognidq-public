"""
F058 — Write APIs for Selected Workflows (Token-Authenticated)
===============================================================

Provides write endpoints for core entities, authenticated via
Personal Access Tokens (F056/F057) with write scope enforcement.

Routes:
  POST  /api/v1/api/workspaces/{workspace_id}/datasets          — write:datasets
  POST  /api/v1/api/workspaces/{workspace_id}/rules       — write:rules
  POST  /api/v1/api/workspaces/{workspace_id}/rules/{rule_id}/execute  — write:executions
  PATCH /api/v1/api/workspaces/{workspace_id}/issues/{issue_id}  — write:issues
"""

from __future__ import annotations

import logging
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.access_token import AccessToken
from app.models.database import get_db
from app.schemas.rule import CreateRuleRequest, ExecuteRuleRequest
from app.services.auth.api_token_auth import ScopeChecker, get_api_token
from app.services.datasets.models import CreateDatasetPayload
from app.services.datasets.service import DatasetService
from app.services.issues.issue_lifecycle_service import (
    EmptyUpdateError,
    InvalidAssigneeError,
    InvalidStatusTransitionError,
    IssueLifecycleService,
    IssueNotFoundError,
    ResolutionSummaryRequiredError,
    ResolutionSummaryTooLongError,
)
from app.services.rules.service import RuleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api-write-entities"])

# Shared service instances
_dataset_svc = DatasetService()
_issue_lifecycle_svc = IssueLifecycleService()


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateDatasetBody(BaseModel):
    data_source_id: UUID
    dataset_name: str
    dataset_type: str
    physical_identifier: str
    schema_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    criticality: str = "low"
    owner_user_id: UUID | None = None
    freshness_expectation: str | None = None


class PatchIssueBody(BaseModel):
    status: str | None = None
    assignee_id: UUID | None = None
    due_at: str | None = None
    resolution_summary: str | None = None


# ---------------------------------------------------------------------------
# Datasets — write:datasets
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/datasets",
    summary="Create dataset (token auth)",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ScopeChecker("write:datasets"))],
)
async def create_dataset(
    workspace_id: UUID,
    body: CreateDatasetBody,
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = CreateDatasetPayload(
        data_source_id=body.data_source_id,
        dataset_name=body.dataset_name,
        dataset_type=body.dataset_type,
        physical_identifier=body.physical_identifier,
        schema_name=body.schema_name,
        description=body.description,
        business_domain=body.business_domain,
        criticality=body.criticality,
        owner_user_id=body.owner_user_id,
        freshness_expectation=body.freshness_expectation,
    )

    # Resolve tenant_id from the workspace row
    tenant_id = _resolve_workspace_tenant(db, workspace_id)
    actor_id = token.user_id or UUID("00000000-0000-0000-0000-000000000001")

    from app.services.datasets.service import DatasetAPIError

    try:
        dataset = _dataset_svc.create_dataset(
            db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            payload=payload,
        )
    except DatasetAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "id": str(dataset.dataset_id),
            "name": dataset.dataset_name,
            "dataset_type": dataset.dataset_type,
            "status": dataset.status,
            "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        },
    )


# ---------------------------------------------------------------------------
# Rules — write:rules
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/rules",
    summary="Create rule (token auth)",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ScopeChecker("write:rules"))],
)
async def create_rule(
    workspace_id: UUID,
    body: CreateRuleRequest,
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
):
    actor_id = token.user_id or UUID("00000000-0000-0000-0000-000000000001")
    service = RuleService(db)
    try:
        rule = await service.create_rule(
            request=body,
            created_by=actor_id,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=rule.dict() if hasattr(rule, "dict") else rule,
    )


# ---------------------------------------------------------------------------
# Executions — write:executions
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/rules/{rule_id}/execute",
    summary="Execute rule (token auth)",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(ScopeChecker("write:executions"))],
)
async def execute_rule(
    workspace_id: UUID,
    rule_id: UUID,
    body: ExecuteRuleRequest,
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    rule = await service.get_rule(rule_id=rule_id, workspace_id=workspace_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found in organization {workspace_id}",
        )

    try:
        execution = await service.execute_rule(
            rule_id=rule_id,
            workspace_id=workspace_id,
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=execution.dict() if hasattr(execution, "dict") else execution,
    )


# ---------------------------------------------------------------------------
# Issues — write:issues
# ---------------------------------------------------------------------------


@router.patch(
    "/workspaces/{workspace_id}/issues/{issue_id}",
    summary="Update issue (token auth)",
    dependencies=[Depends(ScopeChecker("write:issues"))],
)
async def patch_issue(
    workspace_id: UUID,
    issue_id: UUID,
    body: PatchIssueBody,
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    from datetime import datetime

    fields_provided: set[str] = body.model_fields_set

    due_at_parsed: datetime | None = None
    if body.due_at is not None:
        try:
            due_at_parsed = datetime.fromisoformat(body.due_at)
            if due_at_parsed.tzinfo is None:
                due_at_parsed = due_at_parsed.replace(tzinfo=UTC)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="due_at must be a valid ISO-8601 datetime string",
            )

    try:
        enriched = _issue_lifecycle_svc.update_issue(
            db,
            issue_id=issue_id,
            workspace_id=workspace_id,
            fields_provided=fields_provided,
            status=body.status,
            assignee_id=body.assignee_id,
            due_at=due_at_parsed,
            resolution_summary=body.resolution_summary,
        )
    except IssueNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    except (
        InvalidStatusTransitionError,
        ResolutionSummaryRequiredError,
        ResolutionSummaryTooLongError,
        InvalidAssigneeError,
        EmptyUpdateError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "id": str(enriched.id),
            "status": enriched.status,
            "assignee_id": str(enriched.assignee_id) if enriched.assignee_id else None,
            "due_at": enriched.due_at.isoformat() if enriched.due_at else None,
            "title": enriched.title,
        },
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _resolve_workspace_tenant(db: Session, workspace_id: UUID) -> UUID:
    """Fetch tenant_id for a workspace; raise 404 if not found."""
    from sqlalchemy import text

    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid"),
        {"wid": workspace_id},
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    return row[0]
