"""F6 — Celery / Flower observability endpoints.

Proxies the local Flower REST API so platform operators can inspect Celery
worker health, active queues, and recent task history from inside the app
without exposing Flower directly to end users.

Routes (all platform-only):
  GET /api/v1/platform/celery/health   — quick status (workers up / down)
  GET /api/v1/platform/celery/workers  — per-worker details
  GET /api/v1/platform/celery/tasks    — recent task history
  GET /api/v1/platform/celery/queues   — broker queue lengths
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    require_read_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform/celery", tags=["platform-celery"])


def _flower_base_url() -> str:
    return os.getenv("FLOWER_URL", "http://flower:5555")


def _flower_auth() -> tuple[str, str] | None:
    creds = os.getenv("FLOWER_BASIC_AUTH", "").strip()
    if not creds or ":" not in creds:
        return None
    user, _, pwd = creds.partition(":")
    return (user, pwd)


async def _fetch_flower(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{_flower_base_url().rstrip('/')}{path}"
    auth = _flower_auth()
    timeout = httpx.Timeout(5.0, connect=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params or {}, auth=auth)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Flower returned %s for %s", exc.response.status_code, path)
        raise HTTPException(status_code=502, detail=f"Flower error: {exc.response.status_code}")
    except httpx.RequestError as exc:
        logger.warning("Flower unreachable: %s", exc)
        raise HTTPException(status_code=503, detail="Flower service unreachable")


@router.get("/health")
async def celery_health(actor: ActorContext = Depends(require_read_access())) -> dict[str, Any]:
    """Aggregate worker count and online status."""
    try:
        workers = await _fetch_flower("/api/workers")
    except HTTPException as exc:
        return {
            "status": "unavailable",
            "detail": exc.detail,
            "workers_total": 0,
            "workers_online": 0,
        }

    online = 0
    total = 0
    for _, info in (workers or {}).items():
        total += 1
        if isinstance(info, dict) and info.get("status") is True:
            online += 1
    return {
        "status": "ok" if online > 0 else ("degraded" if total > 0 else "no-workers"),
        "workers_total": total,
        "workers_online": online,
        "broker_url": os.getenv("CELERY_BROKER_URL", ""),
    }


@router.get("/workers")
async def celery_workers(actor: ActorContext = Depends(require_read_access())) -> dict[str, Any]:
    """Per-worker stats: active/processed counts, registered tasks, status."""
    workers = await _fetch_flower("/api/workers")
    items = []
    for name, info in (workers or {}).items():
        info = info if isinstance(info, dict) else {}
        items.append(
            {
                "name": name,
                "status": bool(info.get("status")),
                "active": info.get("active"),
                "processed": info.get("processed"),
                "loadavg": info.get("loadavg"),
                "pool": info.get("pool"),
                "registered_tasks": info.get("registered") or [],
            }
        )
    return {"workers": items}


@router.get("/tasks")
async def celery_tasks(
    limit: int = Query(default=50, ge=1, le=500),
    state: str | None = Query(default=None, description="SUCCESS | FAILURE | STARTED | RETRY | …"),
    actor: ActorContext = Depends(require_read_access()),
) -> dict[str, Any]:
    """Recent task history from Flower's in-memory store."""
    params: dict[str, Any] = {"limit": limit}
    if state:
        params["state"] = state
    tasks = await _fetch_flower("/api/tasks", params=params)
    items = []
    for task_id, info in (tasks or {}).items():
        info = info if isinstance(info, dict) else {}
        items.append(
            {
                "id": task_id,
                "name": info.get("name"),
                "state": info.get("state"),
                "received": info.get("received"),
                "started": info.get("started"),
                "succeeded": info.get("succeeded"),
                "failed": info.get("failed"),
                "runtime": info.get("runtime"),
                "exception": info.get("exception"),
                "worker": info.get("worker"),
                "args": info.get("args"),
                "kwargs": info.get("kwargs"),
            }
        )
    items.sort(key=lambda t: t.get("received") or 0, reverse=True)
    return {"tasks": items, "total": len(items)}


@router.get("/queues")
async def celery_queues(actor: ActorContext = Depends(require_read_access())) -> dict[str, Any]:
    """Broker queue lengths reported by Flower."""
    data = await _fetch_flower("/api/queues/length")
    return data or {"active_queues": [], "total": 0}
