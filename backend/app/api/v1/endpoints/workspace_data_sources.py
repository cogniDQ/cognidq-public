"""
F004 — Data Source Endpoint (Workspace-scoped)
================================================

Routes:
  POST   /api/v1/workspaces/{workspace_id}/data-sources
  PATCH  /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}
  GET    /api/v1/workspaces/{workspace_id}/data-sources
  GET    /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}
  GET    /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/audit-logs
  POST   /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/test-connection

Auth: JWT required.
  Write (POST): DATA_SOURCE_WRITE_ROLES
  Read  (GET):  DATA_SOURCE_READ_ROLES
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.data_source_auth import (
    DataSourceActorContext,
    enforce_data_source_tenant_admin_lockdown,
    verify_data_source_read_actor,
    verify_data_source_write_actor,
)
from app.models.database import get_db
from app.services.data_sources.service import DataSourceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/data-sources",
    tags=["data-sources"],
)

_service = DataSourceService()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateDataSourceRequest(BaseModel):
    source_name: str = Field(..., description="Human-readable name for the data source.")
    source_type: str = Field(
        ..., description="One of: postgresql, mysql, mssql, oracle, snowflake, bigquery."
    )
    connection_mode: str = Field(..., description="'direct' or 'agent'.")
    environment: str = Field(..., description="'production', 'staging', or 'development'.")
    credentials: dict[str, Any] = Field(
        ..., description="Type-specific credential dict. Never returned in responses."
    )
    description: str | None = Field(
        None, description="Optional free-text description (max 500 chars)."
    )


class PatchDataSourceRequest(BaseModel):
    """All fields optional; include only what should change."""

    source_name: str | None = Field(None, description="Rename the data source.")
    environment: str | None = Field(None, description="'production', 'staging', or 'development'.")
    description: str | None = Field(None, description="Free-text description (max 500 chars).")
    credentials: dict[str, Any] | None = Field(None, description="Provide to rotate credentials.")
    # Explicitly captured so the service can return 400 IMMUTABLE_FIELD
    source_type: str | None = Field(None, description="IMMUTABLE — not allowed after creation.")
    connection_mode: str | None = Field(None, description="IMMUTABLE — not allowed after creation.")


class TestConfigRequest(BaseModel):
    """Test a connection before saving — no data source record required."""

    type: str = Field(..., description="Source type, e.g. 'postgresql'.")
    connection_config: dict[str, Any] = Field(..., description="Plain-text credential dict.")


def _serialize_data_source(ds) -> dict:
    """Convert a DataSource domain object to a JSON-serialisable dict."""
    return {
        "data_source_id": str(ds.data_source_id),
        "workspace_id": str(ds.workspace_id),
        "source_name": ds.source_name,
        "source_type": ds.source_type,
        "connection_mode": ds.connection_mode,
        "environment": ds.environment,
        "description": ds.description,
        "credential_reference": str(ds.credential_reference) if ds.credential_reference else None,
        "status": ds.status.value,
        "last_test_status": ds.last_test_status.value,
        "last_tested_at": ds.last_tested_at.isoformat() if ds.last_tested_at else None,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        "created_by": str(ds.created_by),
        "updated_by": str(ds.updated_by) if ds.updated_by else None,
        "archived_at": ds.archived_at.isoformat() if ds.archived_at else None,
        "archived_by": str(ds.archived_by) if ds.archived_by else None,
    }


# ---------------------------------------------------------------------------
# POST — Test Connection Config (before saving)
# ---------------------------------------------------------------------------


@router.post(
    "/test-config",
    status_code=status.HTTP_200_OK,
    summary="Test a connection configuration without saving",
)
async def test_connection_config(
    workspace_id: UUID,
    body: TestConfigRequest,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    result = _service._perform_connection_test(
        source_type=body.type,
        connection_mode="direct",
        credentials=body.connection_config,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": result["status"] == "reachable",
            "status": result["status"],
            "message": result.get("error_summary") or "Connection successful",
            "tested_at": result["tested_at"].isoformat() if result["tested_at"] else None,
        },
    )


# ---------------------------------------------------------------------------
# POST — Create Data Source
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a Data Source",
)
async def create_data_source(
    workspace_id: UUID,
    body: CreateDataSourceRequest,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    data_source = _service.create(
        db,
        workspace_id=workspace_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
        source_name=body.source_name,
        source_type=body.source_type,
        connection_mode=body.connection_mode,
        environment=body.environment,
        credentials=body.credentials,
        description=body.description,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_serialize_data_source(data_source),
    )


# ---------------------------------------------------------------------------
# PATCH — Update Data Source
# ---------------------------------------------------------------------------


@router.patch(
    "/{data_source_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a Data Source",
)
async def update_data_source(
    workspace_id: UUID,
    data_source_id: UUID,
    body: PatchDataSourceRequest,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    ds = _service.update(
        db,
        workspace_id=workspace_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
        source_name=body.source_name,
        environment=body.environment,
        description=body.description,
        credentials=body.credentials,
        source_type=body.source_type,
        connection_mode=body.connection_mode,
    )
    return JSONResponse(status_code=200, content=_serialize_data_source(ds))


# ---------------------------------------------------------------------------
# GET — List Data Sources
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List Data Sources",
)
async def list_data_sources(
    workspace_id: UUID,
    status: str | None = Query(
        None, alias="status", description="Filter by status: 'active' or 'archived'."
    ),
    source_type: str | None = Query(None, description="Filter by source type, e.g. 'postgresql'."),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1–100)."),
    actor: DataSourceActorContext = Depends(verify_data_source_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    items, total = _service.list_sources(
        db,
        workspace_id=workspace_id,
        tenant_id=actor.tenant_id,
        actor_role=actor.actor_role,
        status_filter=status,
        source_type_filter=source_type,
        page=page,
        page_size=page_size,
    )
    return JSONResponse(
        status_code=200,
        content={
            "items": [_serialize_data_source(ds) for ds in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": (page * page_size) < total,
        },
    )


# ---------------------------------------------------------------------------
# GET — Get Data Source Detail
# ---------------------------------------------------------------------------


@router.get(
    "/{data_source_id}",
    status_code=status.HTTP_200_OK,
    summary="Get Data Source Detail",
)
async def get_data_source(
    workspace_id: UUID,
    data_source_id: UUID,
    actor: DataSourceActorContext = Depends(verify_data_source_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    ds = _service.get_by_id(
        db,
        workspace_id=workspace_id,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
        actor_role=actor.actor_role,
    )
    return JSONResponse(
        status_code=200,
        content=_serialize_data_source(ds),
    )


# ---------------------------------------------------------------------------
# GET — Audit Logs for a Data Source
# ---------------------------------------------------------------------------


@router.get(
    "/{data_source_id}/audit-logs",
    status_code=status.HTTP_200_OK,
    summary="Get Data Source Audit Logs",
)
async def get_data_source_audit_logs(
    workspace_id: UUID,
    data_source_id: UUID,
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (1–100)."),
    actor: DataSourceActorContext = Depends(verify_data_source_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    items, total = _service.get_audit_logs(
        db,
        workspace_id=workspace_id,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
        actor_role=actor.actor_role,
        page=page,
        page_size=page_size,
    )
    return JSONResponse(
        status_code=200,
        content={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": (page * page_size) < total,
        },
    )


# ---------------------------------------------------------------------------
# GET — Browse Data Source Schema
# ---------------------------------------------------------------------------


@router.get(
    "/{data_source_id}/browse",
    status_code=status.HTTP_200_OK,
    summary="Browse schemas, tables, and views in a Data Source",
)
async def browse_data_source(
    workspace_id: UUID,
    data_source_id: UUID,
    actor: DataSourceActorContext = Depends(verify_data_source_read_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = _service.browse_schema(
        db,
        workspace_id=workspace_id,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
        actor_role=actor.actor_role,
    )
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# POST — Test Connection
# ---------------------------------------------------------------------------


@router.post(
    "/{data_source_id}/test-connection",
    status_code=status.HTTP_200_OK,
    summary="Test Data Source Connection",
)
async def test_data_source_connection(
    workspace_id: UUID,
    data_source_id: UUID,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    result = _service.test_connection(
        db,
        workspace_id=workspace_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
    )
    return JSONResponse(
        status_code=200,
        content={
            "status": result["status"],
            "tested_at": result["tested_at"].isoformat() if result["tested_at"] else None,
            "error_summary": result["error_summary"],
        },
    )


# ---------------------------------------------------------------------------
# POST — Archive Data Source
# ---------------------------------------------------------------------------


@router.post(
    "/{data_source_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="Archive a Data Source",
)
async def archive_data_source(
    workspace_id: UUID,
    data_source_id: UUID,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    ds = _service.archive(
        db,
        workspace_id=workspace_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
    )
    return JSONResponse(status_code=200, content=_serialize_data_source(ds))


# ---------------------------------------------------------------------------
# POST — Restore Data Source
# ---------------------------------------------------------------------------


@router.post(
    "/{data_source_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restore an Archived Data Source",
)
async def restore_data_source(
    workspace_id: UUID,
    data_source_id: UUID,
    actor: DataSourceActorContext = Depends(verify_data_source_write_actor),
    db: Session = Depends(get_db),
) -> JSONResponse:
    enforce_data_source_tenant_admin_lockdown(workspace_id, actor, db)
    ds = _service.restore(
        db,
        workspace_id=workspace_id,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
        data_source_id=data_source_id,
    )
    return JSONResponse(status_code=200, content=_serialize_data_source(ds))
