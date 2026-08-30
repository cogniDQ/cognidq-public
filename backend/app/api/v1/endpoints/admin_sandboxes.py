"""
F134 P07 / P09 — Admin Sandboxes endpoint

Routes:
  GET    /admin/sandboxes                  — list sandboxes with optional status filter
  GET    /admin/sandboxes/{id}             — detail by sandbox ID
  POST   /admin/sandboxes/{id}/extend      — grant extension
  POST   /admin/sandboxes/{id}/suspend     — suspend sandbox
  POST   /admin/sandboxes/{id}/archive     — archive sandbox
  DELETE /admin/sandboxes/{id}             — soft-delete (force flag available)

All routes require platform_admin role.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import ActorContext, require_write_access
from app.models.database import get_db
from app.services.sandbox.sandbox_environment_repository import (
    SandboxEnvironmentRepository,
)
from app.services.sandbox.sandbox_service import (
    SandboxNotFoundError,
    SandboxService,
    SandboxStateError,
    SandboxValidationError,
)
from app.services.sandbox.usage_tracking_service import UsageTrackingService

router = APIRouter(tags=["demo-sandbox-admin"])


@router.get("/admin/sandboxes")
async def list_sandboxes(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    repo = SandboxEnvironmentRepository(db)
    rows, total = repo.list_all(status=status, limit=limit, offset=offset)
    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/admin/sandboxes/{sandbox_id}")
async def get_sandbox(
    sandbox_id: UUID,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    repo = SandboxEnvironmentRepository(db)
    row = repo.find_by_id(sandbox_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    return JSONResponse(status_code=200, content=_serialize(row))


def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# P09 — Lifecycle mutation endpoints
# ---------------------------------------------------------------------------


@router.post("/admin/sandboxes/{sandbox_id}/extend")
async def extend_sandbox(
    sandbox_id: UUID,
    note: str = Body(..., embed=True),
    extra_days: int = Body(default=7, embed=True),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = SandboxService(db)
    try:
        updated = svc.extend(
            sandbox_id=sandbox_id,
            note=note,
            admin_id=actor.actor_id,
            extra_days=extra_days,
        )
        db.commit()
        return JSONResponse(status_code=200, content=_serialize(updated))
    except SandboxNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    except SandboxValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": str(exc)}},
        )


@router.post("/admin/sandboxes/{sandbox_id}/suspend")
async def suspend_sandbox(
    sandbox_id: UUID,
    reason: str | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = SandboxService(db)
    try:
        updated = svc.suspend(
            sandbox_id=sandbox_id,
            admin_id=actor.actor_id,
            reason=reason,
        )
        db.commit()
        return JSONResponse(status_code=200, content=_serialize(updated))
    except SandboxNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    except SandboxStateError as exc:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "invalid_state", "message": str(exc)}},
        )


@router.post("/admin/sandboxes/{sandbox_id}/archive")
async def archive_sandbox(
    sandbox_id: UUID,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = SandboxService(db)
    try:
        updated = svc.archive(
            sandbox_id=sandbox_id,
            admin_id=actor.actor_id,
        )
        db.commit()
        return JSONResponse(status_code=200, content=_serialize(updated))
    except SandboxNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    except SandboxStateError as exc:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "invalid_state", "message": str(exc)}},
        )


@router.delete("/admin/sandboxes/{sandbox_id}")
async def delete_sandbox(
    sandbox_id: UUID,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    svc = SandboxService(db)
    try:
        svc.delete(
            sandbox_id=sandbox_id,
            admin_id=actor.actor_id,
            force=force,
        )
        db.commit()
        return JSONResponse(status_code=204, content=None)
    except SandboxNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    except SandboxStateError as exc:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "invalid_state", "message": str(exc)}},
        )


# ---------------------------------------------------------------------------
# P10 — Usage endpoint
# ---------------------------------------------------------------------------


@router.get("/admin/sandboxes/{sandbox_id}/usage")
async def get_sandbox_usage(
    sandbox_id: UUID,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(require_write_access()),
) -> JSONResponse:
    """Return usage summary + timeline + events-by-type for a sandbox."""
    env_repo = SandboxEnvironmentRepository(db)
    sandbox = env_repo.find_by_id(sandbox_id)
    if sandbox is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Sandbox not found."}},
        )
    svc = UsageTrackingService(db)
    summary = svc.get_usage_summary(sandbox_id=sandbox_id)
    return JSONResponse(status_code=200, content=summary)
