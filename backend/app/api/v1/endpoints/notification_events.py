"""
F045 — Notification Event API Endpoints
=========================================

Routes:
  POST   /api/v1/workspaces/{workspace_id}/notification-events               — log event
  GET    /api/v1/workspaces/{workspace_id}/notification-events               — list events
  GET    /api/v1/workspaces/{workspace_id}/notification-events/summary       — summary counts
  GET    /api/v1/workspaces/{workspace_id}/notification-events/metrics       — F4 KQI aggregates
  GET    /api/v1/workspaces/{workspace_id}/notification-events/{event_id}    — get event
  PATCH  /api/v1/workspaces/{workspace_id}/notification-events/{event_id}/status — update status
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.alerts.notification_event_models import (
    CreateNotificationEventRequest,
    UpdateNotificationEventStatusRequest,
)
from app.services.alerts.notification_event_service import (
    NotificationEventNotFoundError,
    NotificationEventService,
    NotificationEventValidationError,
)
from app.services.audit.models import AuditContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/notification-events",
    tags=["notification-events"],
)

_svc = NotificationEventService()


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
        "alert_rule_id": str(resp.alert_rule_id),
        "alert_channel_id": str(resp.alert_channel_id),
        "recipient": resp.recipient,
        "status": resp.status,
        "payload": resp.payload,
        "retry_count": resp.retry_count,
        "max_retries": resp.max_retries,
        "last_error": resp.last_error,
        "sent_at": resp.sent_at.isoformat() if resp.sent_at else None,
        "delivered_at": resp.delivered_at.isoformat() if resp.delivered_at else None,
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
async def create_notification_event(
    workspace_id: UUID,
    body: CreateNotificationEventRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.log_event(
            db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            alert_rule_id=body.alert_rule_id,
            alert_channel_id=body.alert_channel_id,
            recipient=body.recipient,
            payload=body.payload,
            status=body.status,
            max_retries=body.max_retries,
            audit_ctx=_build_audit_ctx(actor),
        )
        return JSONResponse(status_code=201, content=_serialize(result))
    except NotificationEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


@router.get(
    "",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def list_notification_events(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    rule_id: UUID | None = Query(None),
    channel_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    events = _svc.list_events(
        db,
        workspace_id=workspace_id,
        status_filter=status_filter,
        rule_filter=rule_id,
        channel_filter=channel_id,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(status_code=200, content=[_serialize(e) for e in events])


# ---------------------------------------------------------------------------
# GET summary
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def get_notification_event_summary(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    summary = _svc.get_summary(db, workspace_id=workspace_id)
    return JSONResponse(
        status_code=200,
        content={
            "pending": summary.pending,
            "sent": summary.sent,
            "failed": summary.failed,
            "retrying": summary.retrying,
        },
    )


# ---------------------------------------------------------------------------
# GET metrics (F4 — KQI aggregates for Alerts dashboard)
# ---------------------------------------------------------------------------


@router.get(
    "/metrics",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def get_notification_event_metrics(
    workspace_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
    window_hours: int = Query(
        24, ge=1, le=168, description="Lookback window in hours (max 7 days)"
    ),
    top_n: int = Query(5, ge=1, le=20),
):
    """Return aggregate KQIs for the alerts/notifications dashboard.

    Includes:
      - status_counts: counts in the lookback window grouped by status
      - hourly_buckets: per-hour event counts in the lookback window (oldest → newest)
      - top_firing_rules: rules with the most events in the window (rule_id, name, count, last_fired_at)
      - channel_health: per-channel success/failure breakdown (channel_id, name, channel_type,
                        sent, failed, success_pct, last_success_at, last_failure_at)
      - retry_rate, failure_rate, total
    """
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    params = {"ws": str(workspace_id), "since": since}

    # 1. status counts in window
    status_rows = db.execute(
        text(
            """
        SELECT status, COUNT(*) AS c
        FROM public.notification_events
        WHERE workspace_id = :ws AND created_at >= :since
        GROUP BY status
        """
        ),
        params,
    ).fetchall()
    status_counts = {row[0]: int(row[1]) for row in status_rows}
    total = sum(status_counts.values())
    sent_count = status_counts.get("sent", 0)
    failed_count = status_counts.get("failed", 0)
    retrying_count = status_counts.get("retrying", 0)
    failure_rate = round(failed_count / total, 4) if total else 0.0
    retry_rate = round(retrying_count / total, 4) if total else 0.0
    success_rate = round(sent_count / total, 4) if total else 0.0

    # 2. hourly buckets — generate full series so the chart has zeros for empty hours
    hourly_rows = db.execute(
        text(
            """
        SELECT date_trunc('hour', created_at) AS bucket, COUNT(*) AS c
        FROM public.notification_events
        WHERE workspace_id = :ws AND created_at >= :since
        GROUP BY bucket
        ORDER BY bucket ASC
        """
        ),
        params,
    ).fetchall()
    hourly_map = {row[0]: int(row[1]) for row in hourly_rows}
    buckets: list[dict] = []
    cursor = since.replace(minute=0, second=0, microsecond=0)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    while cursor <= end:
        buckets.append(
            {
                "hour": cursor.isoformat(),
                "count": hourly_map.get(cursor, 0),
            }
        )
        cursor = cursor + timedelta(hours=1)

    # 3. top firing rules
    rule_rows = db.execute(
        text(
            """
        SELECT
          ne.alert_rule_id,
          COALESCE(ar.name, ne.alert_rule_id::text) AS rule_name,
          COUNT(*) AS fired_count,
          MAX(ne.created_at) AS last_fired_at
        FROM public.notification_events ne
        LEFT JOIN public.alert_rules ar ON ar.id = ne.alert_rule_id
        WHERE ne.workspace_id = :ws AND ne.created_at >= :since
        GROUP BY ne.alert_rule_id, ar.name
        ORDER BY fired_count DESC
        LIMIT :top_n
        """
        ),
        {**params, "top_n": top_n},
    ).fetchall()
    top_firing_rules = [
        {
            "rule_id": str(row[0]),
            "name": row[1],
            "fired_count": int(row[2]),
            "last_fired_at": row[3].isoformat() if row[3] else None,
        }
        for row in rule_rows
    ]

    # 4. channel health
    channel_rows = db.execute(
        text(
            """
        SELECT
          ne.alert_channel_id,
          COALESCE(ac.name, ne.alert_channel_id::text) AS channel_name,
          ac.channel_type,
          COUNT(*) FILTER (WHERE ne.status = 'sent')   AS sent_count,
          COUNT(*) FILTER (WHERE ne.status = 'failed') AS failed_count,
          COUNT(*) AS total_count,
          MAX(CASE WHEN ne.status = 'sent'   THEN ne.sent_at END)    AS last_success_at,
          MAX(CASE WHEN ne.status = 'failed' THEN ne.updated_at END) AS last_failure_at
        FROM public.notification_events ne
        LEFT JOIN public.alert_channels ac ON ac.id = ne.alert_channel_id
        WHERE ne.workspace_id = :ws AND ne.created_at >= :since
        GROUP BY ne.alert_channel_id, ac.name, ac.channel_type
        ORDER BY total_count DESC
        """
        ),
        params,
    ).fetchall()
    channel_health = []
    for row in channel_rows:
        ch_total = int(row[5])
        ch_sent = int(row[3])
        channel_health.append(
            {
                "channel_id": str(row[0]),
                "name": row[1],
                "channel_type": row[2],
                "sent_count": ch_sent,
                "failed_count": int(row[4]),
                "total_count": ch_total,
                "success_pct": round(ch_sent / ch_total, 4) if ch_total else 0.0,
                "last_success_at": row[6].isoformat() if row[6] else None,
                "last_failure_at": row[7].isoformat() if row[7] else None,
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "window_hours": window_hours,
            "since": since.isoformat(),
            "total": total,
            "status_counts": status_counts,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "retry_rate": retry_rate,
            "hourly_buckets": buckets,
            "top_firing_rules": top_firing_rules,
            "channel_health": channel_health,
        },
    )


# ---------------------------------------------------------------------------
# GET single
# ---------------------------------------------------------------------------


@router.get(
    "/{event_id}",
    dependencies=[Depends(require_workspace_permission("alerts:read"))],
)
async def get_notification_event(
    workspace_id: UUID,
    event_id: UUID,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.get_event(db, event_id=event_id, workspace_id=workspace_id)
        return JSONResponse(status_code=200, content=_serialize(result))
    except NotificationEventNotFoundError:
        raise HTTPException(status_code=404, detail="Notification event not found")


# ---------------------------------------------------------------------------
# PATCH status
# ---------------------------------------------------------------------------


@router.patch(
    "/{event_id}/status",
    dependencies=[Depends(require_workspace_permission("alerts:write"))],
)
async def update_notification_event_status(
    workspace_id: UUID,
    event_id: UUID,
    body: UpdateNotificationEventStatusRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
    db: Session = Depends(get_db),
):
    try:
        result = _svc.update_event_status(
            db,
            event_id=event_id,
            workspace_id=workspace_id,
            status=body.status,
            last_error=body.last_error,
            retry_count=body.retry_count,
            audit_ctx=_build_audit_ctx(actor),
        )
        return JSONResponse(status_code=200, content=_serialize(result))
    except NotificationEventNotFoundError:
        raise HTTPException(status_code=404, detail="Notification event not found")
    except NotificationEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
