"""
F044 — Alert Channel API Endpoints
====================================

Routes:
  POST   /api/v1/workspaces/{workspace_id}/alert-channels              — create channel
  GET    /api/v1/workspaces/{workspace_id}/alert-channels              — list channels
  GET    /api/v1/workspaces/{workspace_id}/alert-channels/{channel_id} — get channel
  PATCH  /api/v1/workspaces/{workspace_id}/alert-channels/{channel_id} — update channel
  DELETE /api/v1/workspaces/{workspace_id}/alert-channels/{channel_id} — delete channel
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.alerts.alert_channel_models import (
    CreateAlertChannelRequest,
    UpdateAlertChannelRequest,
)
from app.services.alerts.alert_channel_service import (
    AlertChannelNotFoundError,
    AlertChannelService,
    AlertChannelValidationError,
    DuplicateAlertChannelNameError,
)
from app.services.audit.models import AuditContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/alert-channels",
    tags=["alert-channels"],
)

_svc = AlertChannelService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_audit_ctx(actor: WorkspaceActorContext) -> AuditContext:
    return AuditContext(
        tenant_id=actor.tenant_id,
        actor_id=actor.actor_id,
        actor_type="user",
        actor_role=actor.actor_role,
        request_id=None,
        source_ip=None,
    )


def _serialize(resp) -> dict:
    return {
        "id": str(resp.id),
        "workspace_id": str(resp.workspace_id),
        "name": resp.name,
        "channel_type": resp.channel_type,
        "configuration": resp.configuration,
        "enabled": resp.enabled,
        "created_by_user_id": str(resp.created_by_user_id) if resp.created_by_user_id else None,
        "created_at": resp.created_at.isoformat(),
        "updated_at": resp.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------


@router.post(
    "",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def create_alert_channel(
    workspace_id: UUID,
    body: CreateAlertChannelRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.create_channel(
            db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            created_by_user_id=actor.actor_id,
            name=body.name,
            channel_type=body.channel_type,
            configuration=body.configuration,
            enabled=body.enabled,
            audit_ctx=_build_audit_ctx(actor),
        )
        db.commit()
        return JSONResponse(status_code=201, content=_serialize(result))
    except DuplicateAlertChannelNameError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except AlertChannelValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


@router.get(
    "",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def list_alert_channels(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    channels = _svc.list_channels(db, workspace_id=workspace_id)
    return JSONResponse(status_code=200, content=[_serialize(c) for c in channels])


# ---------------------------------------------------------------------------
# GET single
# ---------------------------------------------------------------------------


@router.get(
    "/{channel_id}",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def get_alert_channel(
    workspace_id: UUID,
    channel_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.get_channel(db, channel_id=channel_id, workspace_id=workspace_id)
        return JSONResponse(status_code=200, content=_serialize(result))
    except AlertChannelNotFoundError:
        raise HTTPException(status_code=404, detail="Alert channel not found")


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


@router.patch(
    "/{channel_id}",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def update_alert_channel(
    workspace_id: UUID,
    channel_id: UUID,
    body: UpdateAlertChannelRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    kwargs: dict = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.channel_type is not None:
        kwargs["channel_type"] = body.channel_type
    if body.configuration is not None:
        kwargs["configuration"] = body.configuration
    if body.enabled is not None:
        kwargs["enabled"] = body.enabled

    try:
        result = _svc.update_channel(
            db,
            channel_id=channel_id,
            workspace_id=workspace_id,
            audit_ctx=_build_audit_ctx(actor),
            **kwargs,
        )
        return JSONResponse(status_code=200, content=_serialize(result))
    except AlertChannelNotFoundError:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    except DuplicateAlertChannelNameError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except AlertChannelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@router.delete(
    "/{channel_id}",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def delete_alert_channel(
    workspace_id: UUID,
    channel_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        _svc.delete_channel(
            db,
            channel_id=channel_id,
            workspace_id=workspace_id,
            audit_ctx=_build_audit_ctx(actor),
        )
        return JSONResponse(status_code=204, content=None)
    except AlertChannelNotFoundError:
        raise HTTPException(status_code=404, detail="Alert channel not found")


# ---------------------------------------------------------------------------
# F116 — Test & Dispatch
# ---------------------------------------------------------------------------


@router.post(
    "/{channel_id}/test",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
    summary="Send a test notification to verify channel configuration",
)
async def test_alert_channel(
    workspace_id: UUID,
    channel_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    from app.services.alerts.notification_dispatcher import NotificationDispatcher

    dispatcher = NotificationDispatcher()
    result = dispatcher.send_test(db, channel_id=channel_id, workspace_id=workspace_id)
    code = 200 if result["success"] else 422
    return JSONResponse(status_code=code, content=result)


@router.post(
    "/dispatch",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
    summary="Dispatch pending notification events for this workspace",
)
async def dispatch_notifications(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    from app.services.alerts.notification_dispatcher import NotificationDispatcher

    dispatcher = NotificationDispatcher()
    counts = dispatcher.dispatch_pending(db, workspace_id=workspace_id)
    return JSONResponse(status_code=200, content=counts)
