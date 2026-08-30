"""
F059 — Webhook and Event Delivery — API Endpoints
==================================================

Routes (all under /workspaces/{workspace_id}/webhooks):
  POST   /workspaces/{workspace_id}/webhooks              — create subscription
  GET    /workspaces/{workspace_id}/webhooks              — list subscriptions
  GET    /workspaces/{workspace_id}/webhooks/{sub_id}     — get subscription
  PATCH  /workspaces/{workspace_id}/webhooks/{sub_id}     — update subscription
  DELETE /workspaces/{workspace_id}/webhooks/{sub_id}     — delete subscription
  GET    /workspaces/{workspace_id}/webhooks/{sub_id}/deliveries — delivery history

  POST   /internal/webhooks/retry                        — retry pending deliveries (internal)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.models.webhook import WebhookDeliveryLog, WebhookSubscription
from app.services.webhooks import (
    VALID_EVENT_TYPES,
    WebhookLimitError,
    WebhookNotFoundError,
    WebhookSubscriptionService,
    WebhookValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["webhooks"],
)

_svc = WebhookSubscriptionService()


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class CreateWebhookBody(BaseModel):
    name: str
    target_url: str
    event_types: list[str]
    enabled: bool = True


class PatchWebhookBody(BaseModel):
    name: str | None = None
    target_url: str | None = None
    event_types: list[str] | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sub_to_dict(sub: WebhookSubscription, include_secret: bool = False) -> dict:
    d = {
        "id": str(sub.id),
        "workspace_id": str(sub.workspace_id),
        "name": sub.name,
        "target_url": sub.target_url,
        "event_types": sub.event_types or [],
        "enabled": sub.enabled,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
    }
    if include_secret:
        d["secret_key"] = sub.secret_key
    return d


def _delivery_to_dict(log: WebhookDeliveryLog) -> dict:
    return {
        "id": str(log.id),
        "subscription_id": str(log.subscription_id),
        "event_type": log.event_type,
        "status": log.status,
        "attempt_count": log.attempt_count,
        "http_response_code": log.http_response_code,
        "last_error": log.last_error,
        "last_attempt_at": log.last_attempt_at.isoformat() if log.last_attempt_at else None,
        "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/webhooks",
    summary="Create webhook subscription",
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    workspace_id: UUID,
    body: CreateWebhookBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    tenant_id = _get_tenant_id(db, workspace_id)
    try:
        sub = _svc.create_subscription(
            db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            actor_id=actor.actor_id,
            name=body.name,
            target_url=body.target_url,
            event_types=body.event_types,
            enabled=body.enabled,
        )
    except WebhookValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except WebhookLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Include secret_key only on creation — callers must store it
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_sub_to_dict(sub, include_secret=True),
    )


@router.get(
    "/webhooks",
    summary="List webhook subscriptions",
)
async def list_webhooks(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    subscriptions = _svc.list_subscriptions(db, workspace_id)
    return JSONResponse(
        status_code=200,
        content={
            "items": [_sub_to_dict(s) for s in subscriptions],
            "total": len(subscriptions),
        },
    )


@router.get(
    "/webhooks/{subscription_id}",
    summary="Get webhook subscription",
)
async def get_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    sub = _svc.get_subscription(db, subscription_id, workspace_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    return JSONResponse(status_code=200, content=_sub_to_dict(sub))


@router.patch(
    "/webhooks/{subscription_id}",
    summary="Update webhook subscription",
)
async def update_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    body: PatchWebhookBody,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    try:
        sub = _svc.update_subscription(
            db,
            subscription_id=subscription_id,
            workspace_id=workspace_id,
            name=body.name,
            target_url=body.target_url,
            event_types=body.event_types,
            enabled=body.enabled,
        )
    except WebhookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WebhookValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return JSONResponse(status_code=200, content=_sub_to_dict(sub))


@router.delete(
    "/webhooks/{subscription_id}",
    summary="Delete webhook subscription",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
):
    deleted = _svc.delete_subscription(db, subscription_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")


@router.get(
    "/webhooks/{subscription_id}/deliveries",
    summary="List delivery log for a webhook subscription",
)
async def list_deliveries(
    workspace_id: UUID,
    subscription_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    # Verify subscription belongs to workspace
    sub = _svc.get_subscription(db, subscription_id, workspace_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")

    from sqlalchemy import func, select

    offset = (page - 1) * page_size
    total_result = db.execute(
        select(func.count())
        .select_from(WebhookDeliveryLog)
        .where(WebhookDeliveryLog.subscription_id == subscription_id)
    )
    total = total_result.scalar_one()

    logs_result = db.execute(
        select(WebhookDeliveryLog)
        .where(WebhookDeliveryLog.subscription_id == subscription_id)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    logs = list(logs_result.scalars().all())

    return JSONResponse(
        status_code=200,
        content={
            "items": [_delivery_to_dict(log) for log in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": total > page * page_size,
        },
    )


# ---------------------------------------------------------------------------
# Valid event types meta endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/webhooks-event-types",
    summary="List valid webhook event types",
    tags=["webhooks"],
)
async def list_event_types(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"event_types": sorted(VALID_EVENT_TYPES)},
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_tenant_id(db: Session, workspace_id: UUID) -> UUID:
    from sqlalchemy import text

    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid"),
        {"wid": workspace_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    return row[0]
