"""
F031/F033/F035 — Issue API Endpoints
======================================

Routes:
  GET   /api/v1/workspaces/{workspace_id}/issues             — list issues
  GET   /api/v1/workspaces/{workspace_id}/issues/{issue_id}  — issue detail
  PATCH /api/v1/workspaces/{workspace_id}/issues/{issue_id}  — update issue

Auth:
  GET endpoints require ``issues:read``.
  PATCH requires ``issues:write``.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.issues.comment_models import CreateCommentRequest
from app.services.issues.comment_service import (
    CommentBodyError,
    IssueCommentService,
)
from app.services.issues.comment_service import (
    IssueNotFoundError as CommentIssueNotFoundError,
)
from app.services.issues.issue_detail_service import IssueDetailService
from app.services.issues.issue_lifecycle_service import (
    EmptyUpdateError,
    InvalidAssigneeError,
    InvalidStatusTransitionError,
    IssueLifecycleService,
    IssueNotFoundError,
    ResolutionSummaryRequiredError,
    ResolutionSummaryTooLongError,
)
from app.services.issues.issue_models import (
    VALID_SORT_COLUMNS,
    VALID_SORT_DIRECTIONS,
    IssueUpdateRequest,
)
from app.services.issues.issue_repository import IssueRepository
from app.services.issues.sample_repository import SampleRepository
from app.services.issues.timeline_service import TimelineService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/issues",
    tags=["issues"],
)

_repo = IssueRepository()
_detail_svc = IssueDetailService(repository=_repo)
_lifecycle_svc = IssueLifecycleService(repository=_repo, detail_service=_detail_svc)
_audit_svc = AuditService()
_comment_svc = IssueCommentService(issue_repo=_repo)
_timeline_svc = TimelineService()

# ---------------------------------------------------------------------------
# Validation allow-lists
# ---------------------------------------------------------------------------

VALID_STATUSES = frozenset({"open", "in_progress", "resolved", "closed", "reopened"})
VALID_SEVERITIES = frozenset({"critical", "major", "minor", "informational"})


# ---------------------------------------------------------------------------
# Metrics helpers (fire-and-forget stubs — TDD §12)
# ---------------------------------------------------------------------------


def _emit_list_duration(ms: float) -> None:
    try:
        logger.info("metric: issues_list_request_duration_ms value=%.1f", ms)
    except Exception:
        pass


def _emit_detail_duration(ms: float) -> None:
    try:
        logger.info("metric: issues_detail_request_duration_ms value=%.1f", ms)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_list_item(item) -> dict:
    return {
        "id": str(item.id),
        "workspace_id": str(item.workspace_id),
        "issue_type": item.issue_type,
        "severity": item.severity,
        "status": item.status,
        "title": item.title,
        "impact_summary": item.impact_summary,
        "failure_count": item.failure_count,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "opened_at": item.opened_at.isoformat() if item.opened_at else None,
        "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        "assignee_display_name": item.assignee_display_name,
        "dataset_name": item.dataset_name,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_detail(d) -> dict:
    return {
        "id": str(d.id),
        "workspace_id": str(d.workspace_id),
        "tenant_id": str(d.tenant_id),
        "flow_execution_id": str(d.flow_execution_id),
        "flow_node_result_id": str(d.flow_node_result_id) if d.flow_node_result_id else None,
        "rule_id": str(d.rule_id) if d.rule_id else None,
        "dataset_id": str(d.dataset_id) if d.dataset_id else None,
        "assignee_id": str(d.assignee_id) if d.assignee_id else None,
        "issue_type": d.issue_type,
        "severity": d.severity,
        "status": d.status,
        "title": d.title,
        "impact_summary": d.impact_summary,
        "resolution_summary": d.resolution_summary,
        "failure_count": d.failure_count,
        "rows_scanned": d.rows_scanned,
        "pass_rate": float(d.pass_rate) if d.pass_rate is not None else None,
        "due_at": d.due_at.isoformat() if d.due_at else None,
        "opened_at": d.opened_at.isoformat() if d.opened_at else None,
        "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _serialize_enriched_detail(d) -> dict:
    """Serialize an EnrichedIssueDetail including nested context objects."""
    base = _serialize_detail(d)
    base["rule"] = _serialize_rule_summary(d.rule) if d.rule else None
    base["dataset"] = _serialize_dataset_summary(d.dataset) if d.dataset else None
    base["assignee"] = _serialize_assignee_summary(d.assignee) if d.assignee else None
    base["flow_execution"] = (
        _serialize_execution_summary(d.flow_execution) if d.flow_execution else None
    )
    base["node_result"] = _serialize_node_result_summary(d.node_result) if d.node_result else None
    return base


def _serialize_rule_summary(r) -> dict:
    # `r` may be a RuleSummary pydantic model (already has .severity)
    # or a raw DQRule ORM where severity lives in canonical_rule JSON
    if hasattr(r, "canonical_rule"):
        _sev = None
        if r.canonical_rule and isinstance(r.canonical_rule, dict):
            _sev = r.canonical_rule.get("severity")
    else:
        _sev = getattr(r, "severity", None)
    return {
        "id": str(r.id),
        "name": r.name,
        "category": r.category,
        "severity": _sev,
        "status": r.status,
        "target_table": r.target_table,
        "target_columns": r.target_columns,
    }


def _serialize_dataset_summary(ds) -> dict:
    return {
        "dataset_id": str(ds.dataset_id),
        "dataset_name": ds.dataset_name,
        "business_domain": ds.business_domain,
        "criticality": ds.criticality,
        "status": ds.status,
    }


def _serialize_assignee_summary(a) -> dict:
    return {
        "id": str(a.id),
        "display_name": a.display_name,
        "email": a.email,
    }


def _serialize_execution_summary(ex) -> dict:
    return {
        "id": str(ex.id),
        "flow_name": ex.flow_name,
        "status": ex.status,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "nodes_total": ex.nodes_total,
        "nodes_passed": ex.nodes_passed,
        "nodes_failed": ex.nodes_failed,
    }


def _serialize_node_result_summary(nr) -> dict:
    return {
        "id": str(nr.id),
        "node_id": nr.node_id,
        "node_type": nr.node_type,
        "status": nr.status,
        "rows_scanned": nr.rows_scanned,
        "rows_passed": nr.rows_passed,
        "rows_failed": nr.rows_failed,
        "pass_rate": nr.pass_rate,
        # Sprint 4.2 — evidence fields
        "check_type": getattr(nr, "check_type", None),
        "dataset": getattr(nr, "dataset", None),
        "table_name": getattr(nr, "table_name", None),
        "schema_name": getattr(nr, "schema_name", None),
        "columns": getattr(nr, "columns", None),
        "threshold": getattr(nr, "threshold", None),
        "violations": getattr(nr, "violations", None),
        "sample_data": getattr(nr, "sample_data", None),
    }


def _validate_uuid(value: str, field_name: str) -> None:
    """Raise HTTP 400 if *value* is not a valid UUID."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} filter value.",
        )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/issues
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List Issues",
)
async def list_issues(
    workspace_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    assignee_id: str | None = Query(None),
    dataset_id: str | None = Query(None),
    overdue: bool = Query(False),
    sort_by: str = Query("opened_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
) -> JSONResponse:
    t0 = time.monotonic()

    # Validate filter values
    if status_filter is not None and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status filter value.",
        )
    if severity is not None and severity not in VALID_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid severity filter value.",
        )
    if assignee_id is not None and assignee_id != "unassigned":
        _validate_uuid(assignee_id, "assignee_id")
    if dataset_id is not None:
        _validate_uuid(dataset_id, "dataset_id")
    if sort_by not in VALID_SORT_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort column. Must be one of: {', '.join(sorted(VALID_SORT_COLUMNS))}",
        )
    if sort_dir not in VALID_SORT_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sort direction. Must be 'asc' or 'desc'.",
        )

    parsed_dataset_id = UUID(dataset_id) if dataset_id else None

    items, total = _repo.list_by_workspace(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        assignee_id=assignee_id,
        dataset_id=parsed_dataset_id,
        overdue=overdue,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )

    has_next = total > page * page_size

    _emit_list_duration((time.monotonic() - t0) * 1000)

    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize_list_item(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
        },
    )


# ---------------------------------------------------------------------------
# CSV helpers (F037)
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "id",
    "title",
    "severity",
    "status",
    "assignee_display_name",
    "dataset_name",
    "issue_type",
    "failure_count",
    "due_at",
    "opened_at",
    "resolved_at",
    "closed_at",
    "updated_at",
    "impact_summary",
]

_DANGEROUS_FIRST_CHARS = frozenset("=+-@")


def _safe_csv_value(value) -> str:
    """Escape values that could trigger formula injection in spreadsheets."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _DANGEROUS_FIRST_CHARS:
        return "'" + s
    return s


def _emit_export_duration(ms: float, row_count: int, truncated: bool) -> None:
    try:
        logger.info(
            "metric: issues_export_duration_ms value=%.1f row_count=%d truncated=%s",
            ms,
            row_count,
            truncated,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/issues/export  — F037
# ---------------------------------------------------------------------------


@router.get(
    "/export",
    status_code=status.HTTP_200_OK,
    summary="Export Issues CSV",
)
async def export_issues_csv(
    workspace_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    assignee_id: str | None = Query(None),
    dataset_id: str | None = Query(None),
    overdue: bool = Query(False),
    sort_by: str = Query("opened_at"),
    sort_dir: str = Query("desc"),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
) -> Response:
    t0 = time.monotonic()

    # Validate filters (same as list endpoint)
    if status_filter is not None and status_filter not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status filter value.")
    if severity is not None and severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail="Invalid severity filter value.")
    if assignee_id is not None and assignee_id != "unassigned":
        _validate_uuid(assignee_id, "assignee_id")
    if dataset_id is not None:
        _validate_uuid(dataset_id, "dataset_id")
    if sort_by not in VALID_SORT_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort column. Must be one of: {', '.join(sorted(VALID_SORT_COLUMNS))}",
        )
    if sort_dir not in VALID_SORT_DIRECTIONS:
        raise HTTPException(
            status_code=400, detail="Invalid sort direction. Must be 'asc' or 'desc'."
        )

    parsed_dataset_id = UUID(dataset_id) if dataset_id else None

    items, truncated = _repo.list_all_for_export(
        db,
        workspace_id,
        status=status_filter,
        severity=severity,
        assignee_id=assignee_id,
        dataset_id=parsed_dataset_id,
        overdue=overdue,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)

    for item in items:
        row = []
        for col in _CSV_COLUMNS:
            val = getattr(item, col, None)
            if isinstance(val, datetime):
                row.append(val.isoformat())
            elif val is None:
                row.append("")
            else:
                row.append(_safe_csv_value(val))
        writer.writerow(row)

    if truncated:
        writer.writerow(
            [
                "# NOTE: Export truncated at 10000 rows. Apply narrower filters for a complete export."
            ]
        )

    csv_content = buf.getvalue()

    # UTF-8 BOM for Excel compatibility
    body = b"\xef\xbb\xbf" + csv_content.encode("utf-8")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"issues_export_{ts}.csv"

    _emit_export_duration((time.monotonic() - t0) * 1000, len(items), truncated)

    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/issues/{issue_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{issue_id}",
    status_code=status.HTTP_200_OK,
    summary="Get Issue Detail",
)
async def get_issue(
    workspace_id: UUID,
    issue_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
) -> JSONResponse:
    t0 = time.monotonic()

    enriched = _detail_svc.get_enriched_detail(db, issue_id, workspace_id)
    if enriched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )

    _emit_detail_duration((time.monotonic() - t0) * 1000)

    return JSONResponse(
        status_code=200,
        content=_serialize_enriched_detail(enriched),
    )


# ---------------------------------------------------------------------------
# PATCH /workspaces/{workspace_id}/issues/{issue_id}  — F035
# ---------------------------------------------------------------------------


def _emit_update_duration(ms: float) -> None:
    try:
        logger.info("metric: issues_update_request_duration_ms value=%.1f", ms)
    except Exception:
        pass


@router.patch(
    "/{issue_id}",
    status_code=status.HTTP_200_OK,
    summary="Update Issue",
)
async def update_issue(
    workspace_id: UUID,
    issue_id: UUID,
    body: IssueUpdateRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:write")),
    db: Session = Depends(get_db),
) -> JSONResponse:
    t0 = time.monotonic()

    audit_ctx = AuditContext(
        tenant_id=actor.tenant_id,
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )

    try:
        enriched = _lifecycle_svc.update_issue(
            db,
            issue_id,
            workspace_id,
            fields_provided=body.model_fields_set,
            status=body.status,
            assignee_id=body.assignee_id,
            due_at=body.due_at,
            resolution_summary=body.resolution_summary,
            audit_ctx=audit_ctx,
            audit_service=_audit_svc,
        )
    except IssueNotFoundError:
        raise HTTPException(status_code=404, detail="Issue not found.")
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ResolutionSummaryRequiredError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ResolutionSummaryTooLongError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except InvalidAssigneeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except EmptyUpdateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _emit_update_duration((time.monotonic() - t0) * 1000)

    return JSONResponse(
        status_code=200,
        content=_serialize_enriched_detail(enriched),
    )


# ---------------------------------------------------------------------------
# Module-level service instances (F034)
# ---------------------------------------------------------------------------

_sample_repo = SampleRepository()


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/issues/{issue_id}/samples — F034
# ---------------------------------------------------------------------------


@router.get(
    "/{issue_id}/samples",
    status_code=status.HTTP_200_OK,
    summary="Get Issue Record Samples",
)
async def get_issue_samples(
    workspace_id: UUID,
    issue_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Return the masked failing-record sample captured at issue-creation time."""
    # Verify issue exists in workspace
    enriched = _detail_svc.get_enriched_detail(db, issue_id, workspace_id)
    if enriched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )

    # Fetch sample
    sample = _sample_repo.find_by_issue(db, issue_id, workspace_id)
    if sample is None:
        return JSONResponse(
            status_code=200,
            content={
                "issue_id": str(issue_id),
                "workspace_id": str(workspace_id),
                "captured_at": None,
                "sample_count": 0,
                "masking_applied": False,
                "masking_threshold": None,
                "rows": [],
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "issue_id": str(sample.issue_id),
            "workspace_id": str(sample.workspace_id),
            "captured_at": sample.captured_at.isoformat() if sample.captured_at else None,
            "sample_count": sample.sample_count,
            "masking_applied": sample.masking_applied,
            "masking_threshold": sample.masking_threshold,
            "rows": sample.rows,
        },
    )


# ---------------------------------------------------------------------------
# F036 — Issue Comments + Timeline
# ---------------------------------------------------------------------------


@router.post(
    "/{issue_id}/comments",
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    workspace_id: UUID,
    issue_id: UUID,
    body: CreateCommentRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:write")),
    db: Session = Depends(get_db),
):
    """Add an immutable comment to an issue."""
    audit_ctx = AuditContext.from_workspace_actor(actor)
    try:
        result = _comment_svc.add_comment(
            db,
            issue_id=issue_id,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            author_id=actor.actor_id,
            body=body.body,
            audit_ctx=audit_ctx,
        )
    except CommentIssueNotFoundError:
        raise HTTPException(status_code=404, detail="Issue not found.")
    except CommentBodyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db.commit()
    return JSONResponse(
        status_code=201,
        content={
            "id": str(result.id),
            "issue_id": str(result.issue_id),
            "author_id": str(result.author_id) if result.author_id else None,
            "author_name": result.author_name,
            "body": result.body,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        },
    )


@router.get("/{issue_id}/timeline")
async def get_timeline(
    workspace_id: UUID,
    issue_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("issues:read")),
    db: Session = Depends(get_db),
):
    """Return a unified timeline of comments and system events for an issue."""
    timeline = _timeline_svc.get_timeline(
        db,
        issue_id,
        workspace_id,
        page=page,
        page_size=page_size,
    )
    return JSONResponse(
        status_code=200,
        content={
            "items": [
                {
                    "entry_type": entry.entry_type,
                    "id": str(entry.id),
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "actor_id": str(entry.actor_id) if entry.actor_id else None,
                    "actor_name": entry.actor_name,
                    "content": entry.content,
                }
                for entry in timeline.items
            ],
            "total": timeline.total,
            "page": timeline.page,
            "page_size": timeline.page_size,
            "has_next": timeline.has_next,
        },
    )
