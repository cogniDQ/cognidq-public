"""
F134 P08 — Sandbox User Endpoints

Routes (all require authentication; sandbox_admin actors only):
  GET  /api/v1/sandbox/me
  GET  /api/v1/sandbox/onboarding
  POST /api/v1/sandbox/onboarding/{step_id}/complete
  POST /api/v1/sandbox/extension-request

These endpoints are consumed by the sandbox-user frontend surfaces
(SandboxBanner, SandboxOnboardingChecklist) — implemented in P12.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
)
from app.dependencies.sandbox_gate import (
    ONBOARDING_STEPS,
    SandboxContext,
    get_sandbox_context,
)
from app.models.database import get_db
from app.services.sandbox.sandbox_usage_event_repository import (
    SandboxUsageEventRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sandbox-user"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_sandbox(ctx: SandboxContext) -> None:
    """Raise 403 if the caller is not in a sandbox environment."""
    if not ctx.is_sandbox:
        raise TenantAPIError(
            status_code=403,
            code="not_a_sandbox_user",
            message="This endpoint is only available to sandbox users.",
        )


def _require_not_expired(ctx: SandboxContext) -> None:
    """Raise 403 with reason=trial_expired if the sandbox has expired."""
    if ctx.is_expired:
        raise TenantAPIError(
            status_code=403,
            code="sandbox_forbidden",
            message="Your demo sandbox has expired.",
            fields=[{"reason": "trial_expired"}],
        )


# ---------------------------------------------------------------------------
# Onboarding state helpers
# ---------------------------------------------------------------------------

_COMPLETED_STEPS_SQL = text("""
    SELECT DISTINCT
        event_payload->>'step_id' AS step_id
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
      AND event_type = 'onboarding_step_completed'
      AND event_payload->>'step_id' IS NOT NULL
""")


def _get_completed_steps(db: Session, sandbox_id: UUID) -> list[str]:
    rows = db.execute(_COMPLETED_STEPS_SQL, {"sandbox_id": str(sandbox_id)}).fetchall()
    return [r._mapping["step_id"] for r in rows if r._mapping["step_id"]]


# ---------------------------------------------------------------------------
# GET /api/v1/sandbox/me
# ---------------------------------------------------------------------------


@router.get("/sandbox/me")
async def get_sandbox_me(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_actor_context),
    sandbox: SandboxContext = Depends(get_sandbox_context),
) -> JSONResponse:
    """
    Return sandbox banner config, remaining days, and feature flags.
    Used by the frontend SandboxBanner and to populate SandboxContext.
    Returns 404 when the caller is not a sandbox user.
    """
    if not sandbox.is_sandbox:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "No sandbox environment found."}},
        )

    return JSONResponse(
        status_code=200,
        content={
            "sandbox_id": str(sandbox.sandbox_id),
            "tenant_id": str(sandbox.tenant_id),
            "workspace_id": str(sandbox.workspace_id),
            "status": sandbox.sandbox_status,
            "remaining_days": sandbox.remaining_days,
            "expires_at": sandbox.expires_at.isoformat() if sandbox.expires_at else None,
            "is_expired": sandbox.is_expired,
            "flags": sandbox.flags,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/sandbox/onboarding
# ---------------------------------------------------------------------------


@router.get("/sandbox/onboarding")
async def get_onboarding(
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_actor_context),
    sandbox: SandboxContext = Depends(get_sandbox_context),
) -> JSONResponse:
    """
    Return the onboarding checklist state.

    Steps (fixed order per TDD §4.14):
        view_dataset, view_rule, run_check, open_issue, view_dashboard, create_rule
    """
    _require_sandbox(sandbox)

    completed = set(_get_completed_steps(db, sandbox.sandbox_id))  # type: ignore[arg-type]
    steps = [{"step_id": s, "completed": s in completed} for s in ONBOARDING_STEPS]
    total = len(ONBOARDING_STEPS)
    done = len(completed.intersection(ONBOARDING_STEPS))

    return JSONResponse(
        status_code=200,
        content={
            "steps": steps,
            "progress": {"completed": done, "total": total},
        },
    )


# ---------------------------------------------------------------------------
# POST /api/v1/sandbox/onboarding/{step_id}/complete
# ---------------------------------------------------------------------------


@router.post("/sandbox/onboarding/{step_id}/complete")
async def complete_onboarding_step(
    step_id: str = Path(...),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_actor_context),
    sandbox: SandboxContext = Depends(get_sandbox_context),
) -> JSONResponse:
    """Mark an onboarding step as completed (idempotent)."""
    _require_sandbox(sandbox)

    if step_id not in ONBOARDING_STEPS:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_step",
                    "message": f"Unknown onboarding step '{step_id}'.",
                    "fields": [{"step_id": step_id}],
                }
            },
        )

    repo = SandboxUsageEventRepository(db)
    repo.insert(
        sandbox_id=sandbox.sandbox_id,  # type: ignore[arg-type]
        user_id=actor.actor_id,
        event_type="onboarding_step_completed",
        event_payload={"step_id": step_id},
        occurred_at=datetime.now(UTC),
    )
    db.commit()

    return JSONResponse(
        status_code=200,
        content={"step_id": step_id, "completed": True},
    )


# ---------------------------------------------------------------------------
# POST /api/v1/sandbox/extension-request
# ---------------------------------------------------------------------------


def _emit_admin_extension_notification(
    sandbox_id: UUID,
    actor_id: UUID,
    message: str,
) -> None:  # noqa: ARG001
    """Fire-and-forget stub. Will be wired to notification service in P09."""
    logger.info(
        "STUB: extension-request notification for sandbox %s from actor %s",
        sandbox_id,
        actor_id,
    )


@router.post("/sandbox/extension-request")
async def request_extension(
    message: str | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_actor_context),
    sandbox: SandboxContext = Depends(get_sandbox_context),
) -> JSONResponse:
    """
    Prospect-initiated extension request.

    Records a ``sandbox_usage_events`` row of type ``extension_requested``
    and emits an in-app admin notification stub.
    Admin approves via PATCH /admin/sandboxes/{id}/extend (P09).
    """
    _require_sandbox(sandbox)

    repo = SandboxUsageEventRepository(db)
    repo.insert(
        sandbox_id=sandbox.sandbox_id,  # type: ignore[arg-type]
        user_id=actor.actor_id,
        event_type="extension_requested",
        event_payload={"message": message or ""},
        occurred_at=datetime.now(UTC),
    )
    db.commit()

    _emit_admin_extension_notification(
        sandbox.sandbox_id,  # type: ignore[arg-type]
        actor.actor_id,
        message or "",
    )

    return JSONResponse(
        status_code=202,
        content={
            "status": "received",
            "message": "Your extension request has been submitted and will be reviewed by an admin.",
        },
    )
