"""
F060 — External Ticketing Integration Hooks — API Endpoints
============================================================

Routes (all workspace-scoped):

  Ticketing integration config CRUD:
    POST   /workspaces/{workspace_id}/ticketing-configs                — create config
    GET    /workspaces/{workspace_id}/ticketing-configs                — list configs
    GET    /workspaces/{workspace_id}/ticketing-configs/{config_id}    — get config
    PATCH  /workspaces/{workspace_id}/ticketing-configs/{config_id}    — update config
    DELETE /workspaces/{workspace_id}/ticketing-configs/{config_id}    — delete config

  External ticket link/unlink on issues:
    PUT    /workspaces/{workspace_id}/issues/{issue_id}/external-ticket        — link ticket
    DELETE /workspaces/{workspace_id}/issues/{issue_id}/external-ticket        — unlink ticket

  External ticket link/unlink on incidents:
    PUT    /workspaces/{workspace_id}/incidents/{incident_id}/external-ticket  — link ticket
    DELETE /workspaces/{workspace_id}/incidents/{incident_id}/external-ticket  — unlink ticket

  Meta:
    GET    /workspaces/{workspace_id}/ticketing-systems                — list valid system names
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.models.ticketing import TicketingIntegrationConfig
from app.services.ticketing import (
    VALID_SYSTEM_NAMES,
    ExternalTicketService,
    TicketingConfigConflictError,
    TicketingConfigNotFoundError,
    TicketingConfigService,
    TicketingConfigValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["ticketing"],
)

_cfg_svc = TicketingConfigService()
_ticket_svc = ExternalTicketService()


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class CreateTicketingConfigBody(BaseModel):
    system_name: str
    display_name: str
    base_url: str | None = None
    project_key: str | None = None
    default_issue_type: str | None = None
    enabled: bool = True
    config_json: dict | None = None


class PatchTicketingConfigBody(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    project_key: str | None = None
    default_issue_type: str | None = None
    enabled: bool | None = None
    config_json: dict | None = None


class LinkExternalTicketBody(BaseModel):
    external_ticket_id: str
    external_ticket_url: str | None = None
    external_system: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg_to_dict(cfg: TicketingIntegrationConfig) -> dict:
    return {
        "id": str(cfg.id),
        "workspace_id": str(cfg.workspace_id),
        "system_name": cfg.system_name,
        "display_name": cfg.display_name,
        "base_url": cfg.base_url,
        "project_key": cfg.project_key,
        "default_issue_type": cfg.default_issue_type,
        "enabled": cfg.enabled,
        "config_json": cfg.config_json,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


def _issue_ticket_fields(issue) -> dict:
    return {
        "id": str(issue.id),
        "external_ticket_id": issue.external_ticket_id,
        "external_ticket_url": issue.external_ticket_url,
        "external_system": issue.external_system,
    }


def _incident_ticket_fields(incident) -> dict:
    return {
        "id": str(incident.id),
        "external_ticket_id": incident.external_ticket_id,
        "external_ticket_url": incident.external_ticket_url,
        "external_system": incident.external_system,
    }


# ---------------------------------------------------------------------------
# Ticketing Config CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/ticketing-configs",
    summary="Create ticketing integration config",
    status_code=status.HTTP_201_CREATED,
)
async def create_ticketing_config(
    workspace_id: UUID,
    body: CreateTicketingConfigBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    try:
        cfg = _cfg_svc.create_config(
            db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            system_name=body.system_name,
            display_name=body.display_name,
            base_url=body.base_url,
            project_key=body.project_key,
            default_issue_type=body.default_issue_type,
            enabled=body.enabled,
            config_json=body.config_json,
        )
    except TicketingConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TicketingConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=_cfg_to_dict(cfg))


@router.get(
    "/ticketing-configs",
    summary="List ticketing integration configs",
)
async def list_ticketing_configs(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    configs = _cfg_svc.list_configs(db, workspace_id)
    return JSONResponse(
        status_code=200,
        content={
            "items": [_cfg_to_dict(c) for c in configs],
            "total": len(configs),
        },
    )


@router.get(
    "/ticketing-configs/{config_id}",
    summary="Get ticketing integration config",
)
async def get_ticketing_config(
    workspace_id: UUID,
    config_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    cfg = _cfg_svc.get_config(db, config_id, workspace_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Ticketing config not found")
    return JSONResponse(status_code=200, content=_cfg_to_dict(cfg))


@router.patch(
    "/ticketing-configs/{config_id}",
    summary="Update ticketing integration config",
)
async def update_ticketing_config(
    workspace_id: UUID,
    config_id: UUID,
    body: PatchTicketingConfigBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    try:
        cfg = _cfg_svc.update_config(
            db,
            config_id=config_id,
            workspace_id=workspace_id,
            display_name=body.display_name,
            base_url=body.base_url,
            project_key=body.project_key,
            default_issue_type=body.default_issue_type,
            enabled=body.enabled,
            config_json=body.config_json,
        )
    except TicketingConfigNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketingConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(status_code=200, content=_cfg_to_dict(cfg))


@router.delete(
    "/ticketing-configs/{config_id}",
    summary="Delete ticketing integration config",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ticketing_config(
    workspace_id: UUID,
    config_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
):
    deleted = _cfg_svc.delete_config(db, config_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ticketing config not found")


# ---------------------------------------------------------------------------
# External ticket link/unlink on issues
# ---------------------------------------------------------------------------


@router.put(
    "/issues/{issue_id}/external-ticket",
    summary="Link external ticket to issue",
)
async def link_issue_external_ticket(
    workspace_id: UUID,
    issue_id: UUID,
    body: LinkExternalTicketBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    if body.external_system not in VALID_SYSTEM_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid external_system '{body.external_system}'. "
            f"Must be one of: {sorted(VALID_SYSTEM_NAMES)}",
        )
    issue = _ticket_svc.link_issue_ticket(
        db,
        issue_id=issue_id,
        workspace_id=workspace_id,
        external_ticket_id=body.external_ticket_id,
        external_ticket_url=body.external_ticket_url,
        external_system=body.external_system,
    )
    return JSONResponse(status_code=200, content=_issue_ticket_fields(issue))


@router.delete(
    "/issues/{issue_id}/external-ticket",
    summary="Unlink external ticket from issue",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_issue_external_ticket(
    workspace_id: UUID,
    issue_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
):
    _ticket_svc.unlink_issue_ticket(db, issue_id=issue_id, workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# External ticket link/unlink on incidents
# ---------------------------------------------------------------------------


@router.put(
    "/incidents/{incident_id}/external-ticket",
    summary="Link external ticket to incident",
)
async def link_incident_external_ticket(
    workspace_id: UUID,
    incident_id: UUID,
    body: LinkExternalTicketBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    if body.external_system not in VALID_SYSTEM_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid external_system '{body.external_system}'. "
            f"Must be one of: {sorted(VALID_SYSTEM_NAMES)}",
        )
    incident = _ticket_svc.link_incident_ticket(
        db,
        incident_id=incident_id,
        workspace_id=workspace_id,
        external_ticket_id=body.external_ticket_id,
        external_ticket_url=body.external_ticket_url,
        external_system=body.external_system,
    )
    return JSONResponse(status_code=200, content=_incident_ticket_fields(incident))


@router.delete(
    "/incidents/{incident_id}/external-ticket",
    summary="Unlink external ticket from incident",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_incident_external_ticket(
    workspace_id: UUID,
    incident_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
):
    _ticket_svc.unlink_incident_ticket(db, incident_id=incident_id, workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# Meta — valid system names
# ---------------------------------------------------------------------------


@router.get(
    "/ticketing-systems",
    summary="List supported external ticketing system names",
)
async def list_ticketing_systems(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"systems": sorted(VALID_SYSTEM_NAMES)},
    )
