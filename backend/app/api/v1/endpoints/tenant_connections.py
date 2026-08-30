"""
F130 — Tenant Connection API
==============================

Routes (all under /api/v1/tenants/{tenant_id}/connections):
  GET    /                                  — list connections
  POST   /                                  — create connection
  GET    /{connection_id}                   — get connection
  PATCH  /{connection_id}                   — update connection
  DELETE /{connection_id}                   — delete connection
  POST   /{connection_id}/test              — test connection
  GET    /{connection_id}/workspaces        — list workspace assignments
  PUT    /{connection_id}/workspaces        — replace workspace assignments

Auth: JWT required.
  Write (POST/PATCH/DELETE/PUT): require_write_access (platform_admin)
  Read  (GET):                   require_read_access  (platform_admin, platform_viewer)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    require_tenant_member_read_access,
    require_tenant_write_access,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.services.connections.errors import ConnectionAPIError
from app.services.connections.service import TenantConnectionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tenants/{tenant_id}/connections",
    tags=["connections"],
)

_service = TenantConnectionService()


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────────────────────────────────────


class CreateConnectionRequest(BaseModel):
    source_name: str = Field(..., description="Human-readable name for the connection.")
    source_type: str = Field(
        ..., description="One of: postgresql, mysql, mssql, oracle, snowflake, bigquery."
    )
    connection_mode: str = Field(..., description="'direct' or 'agent'.")
    environment: str = Field(..., description="'production', 'staging', or 'development'.")
    description: str | None = Field(
        None, description="Optional free-text description (max 500 chars)."
    )
    credentials: dict[str, Any] | None = Field(
        None,
        description="Plaintext credential dict; encrypted server-side and never returned.",
    )
    workspace_ids: list[UUID] | None = Field(
        None,
        description="Workspaces granted access to this connection. Empty/null means tenant-only (no workspace use yet).",
    )


class PatchConnectionRequest(BaseModel):
    source_name: str | None = Field(None)
    environment: str | None = Field(None)
    description: str | None = Field(None)
    status: str | None = Field(None)
    # Immutable fields — captured to return 400 instead of silently ignoring
    source_type: str | None = Field(None, description="IMMUTABLE — not allowed after creation.")
    connection_mode: str | None = Field(None, description="IMMUTABLE — not allowed after creation.")


class TestConnectionRequest(BaseModel):
    type: str = Field(..., description="Source type, e.g. 'postgresql'.")
    connection_config: dict[str, Any] = Field(..., description="Plain-text credential dict.")


class WorkspaceAssignmentsRequest(BaseModel):
    workspace_ids: list[UUID] = Field(..., description="Full replacement list of workspace UUIDs.")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _serialize_connection(conn: dict) -> dict:
    """Convert raw row dict to a JSON-serialisable response dict."""

    def _str(v) -> str | None:
        return str(v) if v is not None else None

    return {
        "connection_id": _str(conn.get("data_source_id")),
        "tenant_id": _str(conn.get("tenant_id")),
        "source_name": conn.get("source_name"),
        "source_type": conn.get("source_type"),
        "connection_mode": conn.get("connection_mode"),
        "environment": conn.get("environment"),
        "description": conn.get("description"),
        "status": conn.get("status"),
        "credential_reference": _str(conn.get("credential_reference")),
        "last_test_status": conn.get("last_test_status"),
        "last_tested_at": conn.get("last_tested_at").isoformat()
        if conn.get("last_tested_at")
        else None,
        "created_at": conn.get("created_at").isoformat() if conn.get("created_at") else None,
        "updated_at": conn.get("updated_at").isoformat() if conn.get("updated_at") else None,
        "created_by": _str(conn.get("created_by")),
        "updated_by": _str(conn.get("updated_by")),
    }


def _serialize_assignment(a: dict) -> dict:
    return {
        "connection_id": str(a["connection_id"]),
        "workspace_id": str(a["workspace_id"]),
        "assigned_at": a["assigned_at"].isoformat() if a.get("assigned_at") else None,
        "assigned_by": str(a["assigned_by"]) if a.get("assigned_by") else None,
    }


def _error_response(exc: ConnectionAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}},
    )


def _parse_tenant_id(tenant_id: str) -> UUID:
    return validate_uuid_path_param(tenant_id, "tenant_id")


def _parse_connection_id(connection_id: str) -> UUID:
    return validate_uuid_path_param(connection_id, "connection_id")


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.get("", status_code=status.HTTP_200_OK)
async def list_connections(
    tenant_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None),
    workspace_id: str | None = Query(None),
    actor: ActorContext = Depends(require_tenant_member_read_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    wid_filter: UUID | None = None
    if workspace_id:
        wid_filter = validate_uuid_path_param(workspace_id, "workspace_id")

    try:
        connections, total = _service.list_connections(
            db,
            tid,
            page=page,
            page_size=page_size,
            search=search,
            status_filter=status,
            workspace_id_filter=wid_filter,
        )
    except ConnectionAPIError as exc:
        return _error_response(exc)

    return {
        "items": [_serialize_connection(c) for c in connections],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_connection(
    tenant_id: str,
    body: CreateConnectionRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    payload = body.model_dump(exclude_none=True)
    try:
        conn = _service.create_connection(db, tid, payload, actor.actor_id)
    except ConnectionAPIError as exc:
        return _error_response(exc)
    return _serialize_connection(conn)


@router.get("/{connection_id}", status_code=status.HTTP_200_OK)
async def get_connection(
    tenant_id: str,
    connection_id: str,
    actor: ActorContext = Depends(require_tenant_member_read_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    cid = _parse_connection_id(connection_id)
    conn = _service.get_connection(db, tid, cid)
    if conn is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "CONNECTION_NOT_FOUND",
                    "message": "Connection not found.",
                    "fields": None,
                }
            },
        )
    return _serialize_connection(conn)


@router.patch("/{connection_id}", status_code=status.HTTP_200_OK)
async def patch_connection(
    tenant_id: str,
    connection_id: str,
    body: PatchConnectionRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    cid = _parse_connection_id(connection_id)
    patch = body.model_dump(exclude_none=True)
    try:
        conn = _service.update_connection(db, tid, cid, patch, actor.actor_id)
    except ConnectionAPIError as exc:
        return _error_response(exc)
    return _serialize_connection(conn)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    tenant_id: str,
    connection_id: str,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    cid = _parse_connection_id(connection_id)
    try:
        _service.delete_connection(db, tid, cid)
    except ConnectionAPIError as exc:
        return _error_response(exc)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@router.post("/{connection_id}/test", status_code=status.HTTP_200_OK)
async def test_connection(
    tenant_id: str,
    connection_id: str,
    body: TestConnectionRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    _parse_tenant_id(tenant_id)
    _parse_connection_id(connection_id)
    try:
        result = _service.test_connection(body.type, body.connection_config)
    except Exception as exc:
        logger.warning("Connection test failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": False, "error": str(exc)},
        )
    return result


@router.get("/{connection_id}/workspaces", status_code=status.HTTP_200_OK)
async def get_workspace_assignments(
    tenant_id: str,
    connection_id: str,
    actor: ActorContext = Depends(require_tenant_member_read_access()),
    db: Session = Depends(get_db),
):
    _parse_tenant_id(tenant_id)
    cid = _parse_connection_id(connection_id)
    assignments = _service.get_workspace_assignments(db, cid)
    return {"items": [_serialize_assignment(a) for a in assignments]}


@router.put("/{connection_id}/workspaces", status_code=status.HTTP_200_OK)
async def replace_workspace_assignments(
    tenant_id: str,
    connection_id: str,
    body: WorkspaceAssignmentsRequest,
    actor: ActorContext = Depends(require_tenant_write_access()),
    db: Session = Depends(get_db),
):
    tid = _parse_tenant_id(tenant_id)
    cid = _parse_connection_id(connection_id)
    try:
        assignments = _service.replace_workspace_assignments(
            db, tid, cid, body.workspace_ids, actor.actor_id
        )
    except ConnectionAPIError as exc:
        return _error_response(exc)
    return {"items": [_serialize_assignment(a) for a in assignments]}
