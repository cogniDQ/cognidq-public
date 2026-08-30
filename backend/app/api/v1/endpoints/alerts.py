"""
F043 — Alert Rule API Endpoints
=================================

Routes:
  POST   /api/v1/workspaces/{workspace_id}/alert-rules              — create alert rule
  GET    /api/v1/workspaces/{workspace_id}/alert-rules              — list alert rules
  GET    /api/v1/workspaces/{workspace_id}/alert-rules/{rule_id}    — get single alert rule
  PATCH  /api/v1/workspaces/{workspace_id}/alert-rules/{rule_id}    — update alert rule
  DELETE /api/v1/workspaces/{workspace_id}/alert-rules/{rule_id}    — delete alert rule

Auth:
  All endpoints require ``alerts:write`` (or ``alerts:read`` for read).
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
from app.services.alerts.alert_rule_models import CreateAlertRuleRequest, UpdateAlertRuleRequest
from app.services.alerts.alert_rule_service import (
    AlertRuleLimitError,
    AlertRuleNotFoundError,
    AlertRuleService,
    AlertRuleValidationError,
    DuplicateAlertRuleNameError,
)
from app.services.audit.models import AuditContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/alert-rules",
    tags=["alert-rules"],
)

_svc = AlertRuleService()


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
        "trigger_type": resp.trigger_type,
        "conditions": resp.conditions,
        "recipient_user_ids": resp.recipient_user_ids,
        "channel_ids": getattr(resp, "channel_ids", []),
        "enabled": resp.enabled,
        "created_by_user_id": str(resp.created_by_user_id) if resp.created_by_user_id else None,
        "created_at": resp.created_at.isoformat(),
        "updated_at": resp.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/alert-rules
# ---------------------------------------------------------------------------


@router.post(
    "",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def create_alert_rule(
    workspace_id: UUID,
    body: CreateAlertRuleRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.create_rule(
            db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            created_by_user_id=actor.actor_id,
            name=body.name,
            trigger_type=body.trigger_type,
            conditions=body.conditions,
            recipient_user_ids=[str(uid) for uid in body.recipient_user_ids],
            channel_ids=[str(cid) for cid in (body.channel_ids or [])],
            enabled=body.enabled,
            audit_ctx=_build_audit_ctx(actor),
        )
        db.commit()
        return JSONResponse(status_code=201, content=_serialize(result))
    except DuplicateAlertRuleNameError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except AlertRuleLimitError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except AlertRuleValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/alert-rules
# ---------------------------------------------------------------------------


@router.get(
    "",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def list_alert_rules(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    rules = _svc.list_rules(db, workspace_id=workspace_id)
    return JSONResponse(status_code=200, content=[_serialize(r) for r in rules])


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}/alert-rules/{rule_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{rule_id}",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def get_alert_rule(
    workspace_id: UUID,
    rule_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.get_rule(db, rule_id=rule_id, workspace_id=workspace_id)
        return JSONResponse(status_code=200, content=_serialize(result))
    except AlertRuleNotFoundError:
        raise HTTPException(status_code=404, detail="Alert rule not found")


# ---------------------------------------------------------------------------
# PATCH /workspaces/{workspace_id}/alert-rules/{rule_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{rule_id}",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def update_alert_rule(
    workspace_id: UUID,
    rule_id: UUID,
    body: UpdateAlertRuleRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    kwargs: dict = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.trigger_type is not None:
        kwargs["trigger_type"] = body.trigger_type
    if body.conditions is not None:
        kwargs["conditions"] = body.conditions
    if body.recipient_user_ids is not None:
        kwargs["recipient_user_ids"] = [str(uid) for uid in body.recipient_user_ids]
    if body.enabled is not None:
        kwargs["enabled"] = body.enabled

    try:
        result = _svc.update_rule(
            db,
            rule_id=rule_id,
            workspace_id=workspace_id,
            audit_ctx=_build_audit_ctx(actor),
            **kwargs,
        )
        db.commit()
        return JSONResponse(status_code=200, content=_serialize(result))
    except AlertRuleNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Alert rule not found")
    except DuplicateAlertRuleNameError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except AlertRuleValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# DELETE /workspaces/{workspace_id}/alert-rules/{rule_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{rule_id}",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def delete_alert_rule(
    workspace_id: UUID,
    rule_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        _svc.delete_rule(
            db,
            rule_id=rule_id,
            workspace_id=workspace_id,
            audit_ctx=_build_audit_ctx(actor),
        )
        db.commit()
        return JSONResponse(status_code=204, content=None)
    except AlertRuleNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Alert rule not found")


# ---------------------------------------------------------------------------
# POST /workspaces/{workspace_id}/alert-rules/{rule_id}/test
# ---------------------------------------------------------------------------


@router.post(
    "/{rule_id}/test",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def test_alert_rule(
    workspace_id: UUID,
    rule_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    """Fire a test event for the given alert rule.

    Constructs a synthetic payload matching the rule's ``trigger_type``,
    invokes the AlertTriggerService to create NotificationEvents, then
    immediately dispatches them so the admin sees end-to-end delivery
    success/failure for the rule's channels and recipients.
    """
    from app.models.notification_event import NotificationEvent
    from app.services.alerts.alert_trigger_service import AlertTriggerService
    from app.services.alerts.notification_dispatcher import NotificationDispatcher

    try:
        rule = _svc.get_rule(db, rule_id=rule_id, workspace_id=workspace_id)
    except AlertRuleNotFoundError:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    synthetic_payload = {
        "test": True,
        "rule_id": str(rule_id),
        "rule_name": rule.name,
        "trigger_type": rule.trigger_type,
        "issue_id": "00000000-0000-0000-0000-000000000000",
        "incident_id": "00000000-0000-0000-0000-000000000000",
        "execution_id": "00000000-0000-0000-0000-000000000000",
        "title": f"[TEST] {rule.name}",
        "severity": "informational",
        "old_status": "open",
        "new_status": "open",
        "error_message": "Synthetic test event",
    }

    try:
        before_ids = {
            r[0]
            for r in db.query(NotificationEvent.id)
            .filter(NotificationEvent.alert_rule_id == rule_id)
            .all()
        }
        count = AlertTriggerService().trigger(
            db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            trigger_type=rule.trigger_type,
            payload=synthetic_payload,
            audit_ctx=_build_audit_ctx(actor),
        )
        db.commit()

        new_events = (
            db.query(NotificationEvent)
            .filter(
                NotificationEvent.alert_rule_id == rule_id,
                NotificationEvent.id.notin_(before_ids) if before_ids else True,
            )
            .all()
        )

        dispatcher = NotificationDispatcher()
        results = []
        for ev in new_events:
            ok = dispatcher.dispatch_event(db, ev.id)
            db.refresh(ev)
            results.append(
                {
                    "event_id": str(ev.id),
                    "channel_id": str(ev.alert_channel_id),
                    "recipient": ev.recipient,
                    "delivered": bool(ok),
                    "status": ev.status,
                    "last_error": ev.last_error,
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "rule_id": str(rule_id),
                "events_created": count,
                "events": results,
            },
        )
    except Exception as exc:
        db.rollback()
        logger.exception("alert rule test failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Test failed: {exc}")
