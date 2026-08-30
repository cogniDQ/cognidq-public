"""Data Source service for managing data source connections."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.datasource import DataSource
from app.schemas.datasource import (
    CreateDataSourceRequest,
    TestConnectionRequest,
    UpdateDataSourceRequest,
)
from app.services.datasources.connection_manager import ConnectionManager
from app.services.datasources.schema_inspector import SchemaInspector

logger = logging.getLogger(__name__)


class DataSourceService:
    """Service for data source operations."""

    @staticmethod
    async def create_datasource(
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        request: CreateDataSourceRequest,
        user_id: UUID,
    ) -> DataSource:
        """
        Create a new data source.

        Args:
            db: Database session
            workspace_id: Workspace ID (for reference/audit)
            tenant_id: Tenant ID (for tenant-scoped isolation)
            request: Create data source request
            user_id: User ID creating the datasource

        Returns:
            Created DataSource instance
        """
        try:
            # Encrypt connection config
            encrypted_config = ConnectionManager.encrypt_config(request.connection_config)

            # Create datasource
            datasource = DataSource(
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                name=request.name,
                type=request.type,
                connection_config=encrypted_config,
                status="active",
                created_by=user_id,
            )

            db.add(datasource)
            db.commit()
            db.refresh(datasource)

            logger.info(f"Created datasource: {datasource.name} (ID: {datasource.id})")
            return datasource

        except IntegrityError as e:
            db.rollback()
            logger.error(f"Datasource creation failed (IntegrityError): {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Data source with name '{request.name}' already exists in this organization",
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Datasource creation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create data source: {str(e)}",
            )

    @staticmethod
    def get_datasources(db: Session, tenant_id: UUID) -> list[DataSource]:
        """Get all data sources for a tenant (shared across all workspaces)."""
        return (
            db.query(DataSource)
            .filter(DataSource.tenant_id == tenant_id)
            .order_by(DataSource.created_at.desc())
            .all()
        )

    @staticmethod
    def get_datasource(db: Session, datasource_id: UUID, tenant_id: UUID) -> DataSource:
        """Get a specific data source."""
        datasource = (
            db.query(DataSource)
            .filter(DataSource.id == datasource_id, DataSource.tenant_id == tenant_id)
            .first()
        )

        if not datasource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )

        return datasource

    @staticmethod
    async def update_datasource(
        db: Session, datasource_id: UUID, tenant_id: UUID, request: UpdateDataSourceRequest
    ) -> DataSource:
        """Update a data source."""
        datasource = DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            if request.name is not None:
                datasource.name = request.name

            if request.connection_config is not None:
                # Encrypt new config
                encrypted_config = ConnectionManager.encrypt_config(request.connection_config)
                datasource.connection_config = encrypted_config
                # Reset test status since config changed
                datasource.last_tested_at = None
                datasource.test_result = None

            if request.status is not None:
                datasource.status = request.status

            datasource.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(datasource)

            logger.info(f"Updated datasource: {datasource.name}")
            return datasource

        except IntegrityError as e:
            db.rollback()
            logger.error(f"Datasource update failed (IntegrityError): {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Data source with name '{request.name}' already exists",
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Datasource update failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update data source: {str(e)}",
            )

    @staticmethod
    async def delete_datasource(db: Session, datasource_id: UUID, tenant_id: UUID):
        """Delete a data source."""
        datasource = DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            db.delete(datasource)
            db.commit()
            logger.info(f"Deleted datasource: {datasource.name}")
        except Exception as e:
            db.rollback()
            logger.error(f"Datasource deletion failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete data source: {str(e)}",
            )

    @staticmethod
    async def test_connection(db: Session, datasource_id: UUID, tenant_id: UUID) -> dict:
        """Test connection to a data source."""
        datasource = DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            # Test connection
            success, message, details = await ConnectionManager.test_connection(
                datasource.type, datasource.connection_config, encrypted=True
            )

            # Update datasource with test result
            datasource.last_tested_at = datetime.utcnow()
            datasource.test_result = {"success": success, "message": message, "details": details}
            datasource.status = "active" if success else "error"

            db.commit()
            db.refresh(datasource)

            return {
                "success": success,
                "message": message,
                "details": details,
                "tested_at": datasource.last_tested_at,
            }

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Connection test failed: {str(e)}",
            )

    @staticmethod
    async def test_connection_config(request: TestConnectionRequest) -> dict:
        """Test a connection configuration without saving."""
        try:
            success, message, details = await ConnectionManager.test_connection(
                request.type, request.connection_config, encrypted=False
            )

            return {
                "success": success,
                "message": message,
                "details": details,
                "tested_at": datetime.utcnow(),
            }
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Connection test failed: {str(e)}",
            )

    @staticmethod
    async def refresh_schema(db: Session, datasource_id: UUID, tenant_id: UUID) -> dict:
        """Refresh schema metadata for a data source."""
        datasource = DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            columns_count = await SchemaInspector.refresh_schema(db, datasource)

            return {
                "data_source_id": datasource_id,
                "columns_discovered": columns_count,
                "refreshed_at": datetime.utcnow(),
            }
        except Exception as e:
            logger.error(f"Schema refresh failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Schema refresh failed: {str(e)}",
            )

    @staticmethod
    async def get_schema_metadata(db: Session, datasource_id: UUID, tenant_id: UUID) -> dict:
        """Get cached schema metadata."""
        DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            metadata = await SchemaInspector.get_schema_metadata(db, str(datasource_id))
            return metadata
        except Exception as e:
            logger.error(f"Get schema metadata failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get schema metadata: {str(e)}",
            )

    @staticmethod
    async def get_preview_data(
        db: Session,
        datasource_id: UUID,
        tenant_id: UUID,
        schema_name: str | None,
        table_name: str,
        limit: int,
    ) -> dict:
        """Get preview data from a table."""
        datasource = DataSourceService.get_datasource(db, datasource_id, tenant_id)

        try:
            preview = await SchemaInspector.get_preview_data(
                datasource, schema_name, table_name, limit
            )
            return preview
        except Exception as e:
            logger.error(f"Get preview data failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get preview data: {str(e)}",
            )
