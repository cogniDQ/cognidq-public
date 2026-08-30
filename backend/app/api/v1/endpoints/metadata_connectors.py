"""
F108 — Metadata Connectors Framework API Endpoints.

CRUD + test-connection for metadata connector configurations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.metadata_connector import (
    ConnectorConfigCreate,
    ConnectorConfigResponse,
    ConnectorConfigUpdate,
    ConnectorListResponse,
    ConnectorTestResult,
)
from app.services.auth.jwt import get_current_user
from app.services.metadata_connectors.manager import ConnectorManager

router = APIRouter()
_manager = ConnectorManager()


@router.post(
    "/workspaces/{workspace_id}/metadata-connectors",
    response_model=ConnectorConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a metadata connector",
    tags=["metadata-connectors"],
)
def create_connector(
    workspace_id: UUID,
    data: ConnectorConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorConfigResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _manager.create_config(db, workspace_id, data)


@router.get(
    "/workspaces/{workspace_id}/metadata-connectors",
    response_model=ConnectorListResponse,
    summary="List metadata connectors",
    tags=["metadata-connectors"],
)
def list_connectors(
    workspace_id: UUID,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorListResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _manager.list_configs(db, workspace_id, active_only=active_only)


@router.get(
    "/workspaces/{workspace_id}/metadata-connectors/{config_id}",
    response_model=ConnectorConfigResponse,
    summary="Get a metadata connector config",
    tags=["metadata-connectors"],
)
def get_connector(
    workspace_id: UUID,
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorConfigResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    cfg = _manager.get_config(db, workspace_id, config_id)
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return cfg


@router.put(
    "/workspaces/{workspace_id}/metadata-connectors/{config_id}",
    response_model=ConnectorConfigResponse,
    summary="Update a metadata connector config",
    tags=["metadata-connectors"],
)
def update_connector(
    workspace_id: UUID,
    config_id: str,
    data: ConnectorConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorConfigResponse:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    result = _manager.update_config(db, workspace_id, config_id, data)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return result


@router.delete(
    "/workspaces/{workspace_id}/metadata-connectors/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a metadata connector config",
    tags=["metadata-connectors"],
)
def delete_connector(
    workspace_id: UUID,
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    deleted = _manager.delete_config(db, workspace_id, config_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return None


@router.post(
    "/workspaces/{workspace_id}/metadata-connectors/{config_id}/test",
    response_model=ConnectorTestResult,
    summary="Test a metadata connector connection",
    tags=["metadata-connectors"],
)
def test_connector(
    workspace_id: UUID,
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorTestResult:
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return _manager.test_connection(db, workspace_id, config_id)
