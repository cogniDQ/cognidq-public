"""Data Source API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.schemas.datasource import (
    CreateDataSourceRequest,
    DataPreviewResponse,
    DataSourceResponse,
    SchemaMetadataResponse,
    TestConnectionRequest,
    TestConnectionResponse,
    UpdateDataSourceRequest,
)
from app.services.audit.hooks import build_data_source_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.datasources.connection_manager import ConnectionManager
from app.services.datasources.service import DataSourceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/datasources", tags=["Data Sources"])
_audit_svc = AuditService()


def _resolve_tenant_id(workspace_id: UUID, actor: WorkspaceActorContext, db: Session) -> UUID:
    """
    Resolve tenant_id for datasource operations.
    Platform operators always look up the workspace's tenant (cross-tenant support).
    Regular users use tenant_id from JWT.
    """
    PLATFORM_ROLES = {"platform_admin", "platform_viewer"}
    is_platform_op = (actor.actor_role or "") in PLATFORM_ROLES
    if not is_platform_op and actor.tenant_id:
        return actor.tenant_id
    row = db.execute(
        text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid LIMIT 1"),
        {"wid": str(workspace_id)},
    ).fetchone()
    if not row or not row.tenant_id:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return row.tenant_id


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_datasource(
    workspace_id: UUID,
    request: CreateDataSourceRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:write")),
):
    """
    Create a new data source connection.
    Requires 'datasources:write' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "write")

    datasource = await DataSourceService.create_datasource(
        db=db,
        workspace_id=workspace_id,
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        request=request,
        user_id=actor.actor_id,
    )

    # Mask sensitive data in response
    response_data = DataSourceResponse.from_orm(datasource)
    response_data.connection_config = ConnectionManager.mask_config(datasource.connection_config)

    # F052 audit hook (best-effort; sensitive fields stripped by AuditService)
    try:
        tenant_id = _resolve_tenant_id(workspace_id, actor, db)
        _audit_svc.write(
            db,
            build_data_source_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="data_source_created",
                workspace_id=workspace_id,
                data_source_id=datasource.id,
                after_state={"source_name": datasource.name, "source_type": datasource.type},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=data_source_created id=%s", datasource.id)

    return response_data


@router.get("", response_model=list[DataSourceResponse])
async def list_datasources(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:read")),
):
    """
    List all data sources for an organization.
    Requires 'datasources:read' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "read")

    datasources = DataSourceService.get_datasources(db, _resolve_tenant_id(workspace_id, actor, db))

    # Mask sensitive data in all responses
    results = []
    for datasource in datasources:
        response_data = DataSourceResponse.from_orm(datasource)
        response_data.connection_config = ConnectionManager.mask_config(
            datasource.connection_config
        )
        results.append(response_data)

    return results


@router.get("/{datasource_id}", response_model=DataSourceResponse)
async def get_datasource(
    workspace_id: UUID,
    datasource_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:read")),
):
    """
    Get a specific data source.
    Requires 'datasources:read' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "read")

    datasource = DataSourceService.get_datasource(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    # Mask sensitive data
    response_data = DataSourceResponse.from_orm(datasource)
    response_data.connection_config = ConnectionManager.mask_config(datasource.connection_config)

    return response_data


@router.patch("/{datasource_id}", response_model=DataSourceResponse)
async def update_datasource(
    workspace_id: UUID,
    datasource_id: UUID,
    request: UpdateDataSourceRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:write")),
):
    """
    Update a data source.
    Requires 'datasources:write' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "write")

    datasource = await DataSourceService.update_datasource(
        db=db,
        datasource_id=datasource_id,
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        request=request,
    )

    # Mask sensitive data
    response_data = DataSourceResponse.from_orm(datasource)
    response_data.connection_config = ConnectionManager.mask_config(datasource.connection_config)

    # F052 audit hook (best-effort)
    try:
        tenant_id = _resolve_tenant_id(workspace_id, actor, db)
        _audit_svc.write(
            db,
            build_data_source_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="data_source_updated",
                workspace_id=workspace_id,
                data_source_id=datasource.id,
                after_state={"source_name": datasource.name, "source_type": datasource.type},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=data_source_updated id=%s", datasource.id)

    return response_data


@router.delete("/{datasource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datasource(
    workspace_id: UUID,
    datasource_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:delete")),
):
    """
    Delete a data source.
    Requires 'datasources:delete' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "delete")

    # Capture before_state for audit diff before deletion (P04-AC-03)
    ds_before = DataSourceService.get_datasource(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    await DataSourceService.delete_datasource(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    # F052 audit hook (best-effort)
    try:
        tenant_id = _resolve_tenant_id(workspace_id, actor, db)
        before_state = {"name": ds_before.name, "type": ds_before.type} if ds_before else None
        _audit_svc.write(
            db,
            build_data_source_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="data_source_deleted",
                workspace_id=workspace_id,
                data_source_id=datasource_id,
                before_state=before_state,
                after_state={"deleted": True},
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=data_source_deleted id=%s", datasource_id)

    return None


@router.post("/{datasource_id}/test", response_model=TestConnectionResponse)
async def test_datasource_connection(
    workspace_id: UUID,
    datasource_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:write")),
):
    """
    Test connection to a data source.
    Requires 'datasources:test' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "test")

    result = await DataSourceService.test_connection(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    return TestConnectionResponse(**result)


@router.post("/test-config", response_model=TestConnectionResponse)
async def test_connection_config(
    workspace_id: UUID,
    request: TestConnectionRequest,
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:write")),
):
    """
    Test a connection configuration without saving.
    Useful for validating config before creating a data source.
    Requires 'datasources:write' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "write")

    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"Test connection request - Type: {request.type}, Config keys: {list(request.connection_config.keys())}"
    )

    result = await DataSourceService.test_connection_config(request)

    return TestConnectionResponse(**result)


@router.post("/{datasource_id}/refresh-schema")
async def refresh_schema(
    workspace_id: UUID,
    datasource_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:write")),
):
    """
    Refresh schema metadata for a data source.
    Introspects the database and updates cached metadata.
    Requires 'datasources:refresh' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "refresh")

    result = await DataSourceService.refresh_schema(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    return result


@router.get("/{datasource_id}/schema", response_model=SchemaMetadataResponse)
async def get_schema_metadata(
    workspace_id: UUID,
    datasource_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:read")),
):
    """
    Get cached schema metadata for a data source.
    Returns tables and columns discovered during last refresh.
    Requires 'datasources:read' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "read")

    metadata = await DataSourceService.get_schema_metadata(
        db, datasource_id, _resolve_tenant_id(workspace_id, actor, db)
    )

    return metadata


@router.get("/{datasource_id}/preview", response_model=DataPreviewResponse)
async def preview_data(
    workspace_id: UUID,
    datasource_id: UUID,
    schema_name: str = Query(None, description="Schema name"),
    table_name: str = Query(..., description="Table name"),
    limit: int = Query(100, ge=1, le=1000, description="Number of rows to preview"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("datasources:read")),
):
    """
    Get preview data from a table.
    Requires 'datasources:read' permission.
    """
    # TODO: Add permission check - @require_permission("datasources", "read")

    preview = await DataSourceService.get_preview_data(
        db=db,
        datasource_id=datasource_id,
        tenant_id=_resolve_tenant_id(workspace_id, actor, db),
        schema_name=schema_name,
        table_name=table_name,
        limit=limit,
    )

    return preview
