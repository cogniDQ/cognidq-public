"""
F134 P05 — Admin Demo Request API

Routes:
  GET  /admin/demo-requests               — list with optional status filter
  GET  /admin/demo-requests/{id}          — detail by ID
  POST /admin/demo-requests/{id}/approve  — approve (enqueue job stub)
  POST /admin/demo-requests/{id}/reject   — reject (email stub)

All routes require platform_admin role.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import ActorContext, require_write_access
from app.models.database import get_db
from app.schemas.sandbox.admin import ApproveRequestBody, RejectRequestBody
from app.services.sandbox.access_profile_repository import AccessProfileRepository
from app.services.sandbox.admin_demo_request_service import AdminDemoRequestService
from app.services.sandbox.demo_template_repository import DemoTemplateRepository
from app.services.sandbox.validation.approval_validation import validate_approval

router = APIRouter(tags=["demo-sandbox-admin"])


# ---------------------------------------------------------------------------
# GET /admin/demo-requests
# ---------------------------------------------------------------------------


@router.get("/admin/demo-requests")
async def list_demo_requests(
    status: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = AdminDemoRequestService(db)
    rows, total = svc.list_requests(
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/demo-requests/{id}
# ---------------------------------------------------------------------------


@router.get("/admin/demo-requests/{request_id}")
async def get_demo_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = AdminDemoRequestService(db)
    row = svc.get_request(request_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Demo request not found."}},
        )
    return JSONResponse(status_code=200, content=_serialize(row))


# ---------------------------------------------------------------------------
# POST /admin/demo-requests/{id}/approve
# ---------------------------------------------------------------------------


@router.post("/admin/demo-requests/{request_id}/approve")
async def approve_demo_request(
    request_id: UUID,
    body: ApproveRequestBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    # Validate with callable existence hooks
    template_repo = DemoTemplateRepository(db)
    profile_repo = AccessProfileRepository(db)

    errors = validate_approval(
        template_id=body.template_id,
        duration_days=body.duration_days,
        access_profile_code=body.access_profile_code,
        tags=body.tags or [],
        internal_note=body.internal_note,
        template_id_exists=lambda tid: template_repo.find_by_id(tid) is not None,
        access_profile_code_exists=lambda code: profile_repo.find_by_code(code) is not None,
    )
    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed.",
                    "fields": [{"field": f, "message": m} for f, m in errors],
                }
            },
        )

    svc = AdminDemoRequestService(db)
    row = svc.get_request(request_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Demo request not found."}},
        )

    updated = svc.approve_request(
        request_id=request_id,
        decided_by=actor.actor_id,
        template_id=body.template_id,
        duration_days=body.duration_days,
        access_profile_code=body.access_profile_code,
        tags=body.tags,
        internal_note=body.internal_note,
    )
    return JSONResponse(status_code=200, content=_serialize(updated))


# ---------------------------------------------------------------------------
# POST /admin/demo-requests/{id}/reject
# ---------------------------------------------------------------------------


@router.post("/admin/demo-requests/{request_id}/reject")
async def reject_demo_request(
    request_id: UUID,
    body: RejectRequestBody,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = AdminDemoRequestService(db)
    row = svc.get_request(request_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Demo request not found."}},
        )

    updated = svc.reject_request(
        request_id=request_id,
        decided_by=actor.actor_id,
        reason=body.reason,
        internal_note=getattr(body, "internal_note", None),
    )
    return JSONResponse(status_code=200, content=_serialize(updated))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(row: dict) -> dict:
    """Convert a repo result row to a JSON-safe dict."""
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
