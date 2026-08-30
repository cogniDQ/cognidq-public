"""
D4 — Workspace Demo Data Bootstrap

Routes:
  GET  /api/v1/workspaces/{workspace_id}/demo-data         — status (already seeded?)
  POST /api/v1/workspaces/{workspace_id}/demo-data/load    — populate sample data

The bootstrap delegates to the existing F134 ``general_dq`` template seeder,
which is idempotent (deterministic UUID5 + ON CONFLICT DO NOTHING).

Auth:
  ``workspaces:write`` — typically workspace_administrator only.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.demo.template_seeder_service import SeedingError, TemplateSeederService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/demo-data",
    tags=["workspace-demo-data"],
)

DEFAULT_TEMPLATE_ID = "general_dq"
SEED_SOURCE_PREFIX = "template:"


# ---------------------------------------------------------------------------
# GET /demo-data — status
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
def get_demo_data_status(
    workspace_id: UUID = Path(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasets:read")),
) -> JSONResponse:
    """Return whether sample data has been loaded into this workspace."""

    row = db.execute(
        text(
            "SELECT seed_source, COUNT(*) AS n "
            "FROM control.datasets "
            "WHERE workspace_id = :wid AND seed_source IS NOT NULL "
            "GROUP BY seed_source"
        ),
        {"wid": str(workspace_id)},
    ).fetchall()

    sources = {r[0]: int(r[1]) for r in row}
    seeded = bool(sources)

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "workspace_id": str(workspace_id),
                "seeded": seeded,
                "sources": sources,
                "template_id": DEFAULT_TEMPLATE_ID,
            }
        },
    )


# ---------------------------------------------------------------------------
# POST /demo-data/load — bootstrap sample data
# ---------------------------------------------------------------------------


@router.post("/load", status_code=200)
def load_demo_data(
    workspace_id: UUID = Path(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("workspaces:write")),
) -> JSONResponse:
    """
    Bootstrap a workspace with sample datasets, rules, a flow, sample issues
    and a starter dashboard so dashboards and lists aren't empty.

    Idempotent: subsequent calls are no-ops once seed rows exist.
    """
    logger.info(
        "demo-data.load called: workspace=%s actor=%s",
        workspace_id,
        actor.actor_id,
    )

    service = TemplateSeederService(db)
    try:
        service.seed(
            template_id=DEFAULT_TEMPLATE_ID,
            tenant_id=actor.tenant_id,
            workspace_id=workspace_id,
        )
        db.commit()
    except SeedingError as exc:
        db.rollback()
        logger.warning("demo-data.load seeding failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception:
        db.rollback()
        logger.exception("demo-data.load unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load demo data.",
        )

    # Re-read status for the response so callers see what's now present.
    row = db.execute(
        text(
            "SELECT seed_source, COUNT(*) AS n "
            "FROM control.datasets "
            "WHERE workspace_id = :wid AND seed_source IS NOT NULL "
            "GROUP BY seed_source"
        ),
        {"wid": str(workspace_id)},
    ).fetchall()
    sources = {r[0]: int(r[1]) for r in row}

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "workspace_id": str(workspace_id),
                "template_id": DEFAULT_TEMPLATE_ID,
                "seeded": True,
                "sources": sources,
            }
        },
    )
