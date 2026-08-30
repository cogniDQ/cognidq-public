"""
F118 — Unified Executions API
================================

Provides workspace-scoped cross-entity execution history (rules + flows).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.models.rule import DQRule, RuleExecution, RuleViolation

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/executions",
    tags=["executions"],
)


@router.get("")
async def list_executions(
    workspace_id: UUID,
    execution_type: str | None = Query(None, description="Filter: manual, scheduled, triggered"),
    execution_status: str | None = Query(
        None, alias="status", description="Filter: pending, running, completed, failed"
    ),
    rule_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
) -> dict[str, Any]:
    """List rule executions for the workspace with filtering and pagination."""
    # Join to DQRule to filter by workspace
    query = (
        db.query(RuleExecution)
        .join(DQRule)
        .filter(
            DQRule.workspace_id == workspace_id,
        )
    )

    if rule_id:
        query = query.filter(RuleExecution.rule_id == rule_id)
    if execution_type:
        query = query.filter(RuleExecution.execution_type == execution_type)
    if execution_status:
        query = query.filter(RuleExecution.status == execution_status)

    total = query.count()
    executions = (
        query.order_by(desc(RuleExecution.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "executions": [_serialize_execution(e) for e in executions],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{execution_id}")
async def get_execution(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
) -> dict[str, Any]:
    """Get a single execution with full details."""
    execution = (
        db.query(RuleExecution)
        .join(DQRule)
        .filter(
            RuleExecution.id == execution_id,
            DQRule.workspace_id == workspace_id,
        )
        .first()
    )
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    data = _serialize_execution(execution)
    data["result_details"] = execution.result_details
    data["execution_params"] = execution.execution_params
    data["violations_count"] = (
        db.query(RuleViolation).filter(RuleViolation.execution_id == execution_id).count()
    )
    return data


@router.get("/{execution_id}/download")
async def download_violations(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Download violation report as CSV."""
    # Verify execution belongs to workspace
    execution = (
        db.query(RuleExecution)
        .join(DQRule)
        .filter(
            RuleExecution.id == execution_id,
            DQRule.workspace_id == workspace_id,
        )
        .first()
    )
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    violations = db.query(RuleViolation).filter(RuleViolation.execution_id == execution_id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "violation_id",
            "row_identifier",
            "row_number",
            "severity",
            "category",
            "violation_details",
        ]
    )
    for v in violations:
        writer.writerow(
            [
                str(v.id),
                v.row_identifier,
                v.row_number,
                v.severity,
                v.category,
                str(v.violation_details or {}),
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=violations-{execution_id}.csv"},
    )


def _serialize_execution(e: RuleExecution) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "rule_id": str(e.rule_id),
        "rule_name": e.rule.name if e.rule else None,
        "execution_type": e.execution_type,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "duration_seconds": e.duration_seconds,
        "rows_scanned": e.rows_scanned,
        "rows_passed": e.rows_passed,
        "rows_failed": e.rows_failed,
        "pass_rate": float(e.pass_rate) if e.pass_rate is not None else None,
        "error_message": e.error_message,
        "executed_by": str(e.executed_by) if e.executed_by else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
