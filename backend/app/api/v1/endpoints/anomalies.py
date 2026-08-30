"""F5 â€” Persisted anomalies REST endpoints.

Routes (mounted under /api/v1):
  POST   /workspaces/{workspace_id}/anomalies/run            â€” run detection + persist
  GET    /workspaces/{workspace_id}/anomalies                â€” list with filters
  GET    /workspaces/{workspace_id}/anomalies/{id}           â€” fetch one
  POST   /workspaces/{workspace_id}/anomalies/{id}/acknowledge
  POST   /workspaces/{workspace_id}/anomalies/{id}/resolve
  POST   /workspaces/{workspace_id}/anomalies/{id}/suppress
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.services.kqi.persisted_anomaly_service import PersistedAnomalyService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/anomalies",
    tags=["anomalies"],
)


class _LifecycleRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class _RunDetectionRequest(BaseModel):
    period_days: int = Field(default=30, ge=1, le=365)


@router.post("/run", status_code=status.HTTP_200_OK)
def run_detection(
    workspace_id: UUID,
    body: _RunDetectionRequest = _RunDetectionRequest(),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
):
    svc = PersistedAnomalyService(db)
    try:
        return svc.detect_and_persist(workspace_id, actor.tenant_id, period_days=body.period_days)
    except Exception as e:
        logger.exception("Anomaly detection run failed: %s", e)
        raise HTTPException(status_code=500, detail="Anomaly detection failed")


@router.get("", status_code=status.HTTP_200_OK)
def list_anomalies(
    workspace_id: UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    anomaly_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
):
    svc = PersistedAnomalyService(db)
    return svc.list_anomalies(
        workspace_id,
        status=status_filter,
        severity=severity,
        anomaly_type=anomaly_type,
        limit=limit,
        offset=offset,
    )


@router.get("/{anomaly_id}", status_code=status.HTTP_200_OK)
def get_anomaly(
    workspace_id: UUID,
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:read")),
):
    svc = PersistedAnomalyService(db)
    rec = svc.get(workspace_id, anomaly_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return PersistedAnomalyService._serialize(rec)


def _lifecycle(
    op: str,
    workspace_id: UUID,
    anomaly_id: UUID,
    body: _LifecycleRequest,
    db: Session,
    actor: WorkspaceActorContext,
):
    svc = PersistedAnomalyService(db)
    fn = {"acknowledge": svc.acknowledge, "resolve": svc.resolve, "suppress": svc.suppress}[op]
    rec = fn(workspace_id, anomaly_id, actor.actor_id, notes=body.notes)
    if rec is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return PersistedAnomalyService._serialize(rec)


@router.post("/{anomaly_id}/acknowledge", status_code=status.HTTP_200_OK)
def acknowledge_anomaly(
    workspace_id: UUID,
    anomaly_id: UUID,
    body: _LifecycleRequest = _LifecycleRequest(),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
):
    return _lifecycle("acknowledge", workspace_id, anomaly_id, body, db, actor)


@router.post("/{anomaly_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_anomaly(
    workspace_id: UUID,
    anomaly_id: UUID,
    body: _LifecycleRequest = _LifecycleRequest(),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
):
    return _lifecycle("resolve", workspace_id, anomaly_id, body, db, actor)


@router.post("/{anomaly_id}/suppress", status_code=status.HTTP_200_OK)
def suppress_anomaly(
    workspace_id: UUID,
    anomaly_id: UUID,
    body: _LifecycleRequest = _LifecycleRequest(),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("alerts:write")),
):
    return _lifecycle("suppress", workspace_id, anomaly_id, body, db, actor)
