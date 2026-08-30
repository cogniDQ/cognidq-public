"""
Ingestion API Endpoints

Handle file uploads, ingestion jobs, and data profiling.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import logger
from app.models.database import get_db
from app.schemas.ingestion import (
    DataProfileResponse,
    FileUploadResponse,
)
from app.services.ingestion.file_upload import FileUploadService
from app.services.ingestion.profiler import DataProfiler

# Import MinIO client if available
try:
    from app.services.ingestion.file_upload import minio_client
except ImportError:
    minio_client = None

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

file_service = FileUploadService()
profiler = DataProfiler()
settings = get_settings()


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
) -> FileUploadResponse:
    """
    Upload and parse a file (CSV, Excel, JSON, Parquet).

    - Validates file format
    - Parses and infers column types
    - Returns sample data and metadata
    - File is stored temporarily for ingestion
    """
    try:
        logger.info(f"Uploading file: {file.filename}")
        result = await file_service.upload_and_parse(file)
        return FileUploadResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/workspaces/{workspace_id}/profile", response_model=DataProfileResponse)
async def profile_uploaded_file(
    workspace_id: str, file_id: str = Query(..., description="File ID from upload response")
) -> DataProfileResponse:
    """
    Profile an uploaded file to get column statistics.

    - file_id: ID returned from upload endpoint
    - Returns profiling statistics for all columns
    """
    try:
        # Construct file path from file_id
        import os
        from pathlib import Path

        # Find file with this ID (any extension)
        upload_dir = Path(file_service.upload_dir)
        matching_files = list(upload_dir.glob(f"{file_id}.*"))

        if not matching_files:
            raise HTTPException(status_code=404, detail="File not found")

        file_path = str(matching_files[0])

        # Determine file type from extension
        ext = Path(file_path).suffix.lower()
        file_type_map = {
            ".csv": "csv",
            ".txt": "csv",
            ".tsv": "csv",
            ".xlsx": "excel",
            ".xls": "excel",
            ".json": "json",
            ".jsonl": "json",
            ".parquet": "parquet",
        }
        file_type = file_type_map.get(ext, "csv")

        # Parse file
        parse_result = file_service.parse_file(file_path, file_type, os.path.basename(file_path))

        # Profile data
        profile = profiler.profile_dataframe(parse_result.data)

        return DataProfileResponse(**profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to profile file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/workspaces/{workspace_id}/assets/{asset_id}/profile", response_model=DataProfileResponse
)
async def profile_data_asset(
    workspace_id: str,
    asset_id: str,
    asset_type: str = Query(..., description="Asset type: database, csv, excel, parquet, json"),
    table_name: str | None = Query(None, description="Table name for database assets"),
    db: Session = Depends(get_db),
) -> DataProfileResponse:
    """
    Profile a data asset (database table or uploaded file).

    - asset_id: ID of the asset (datasource_id or file_id)
    - asset_type: Type of asset (database, csv, excel, parquet, json)
    - table_name: Required for database assets
    """
    try:
        from pathlib import Path

        import pandas as pd

        # Handle database assets
        if asset_type == "database":
            from app.models.datasource import DataSource
            from app.services.datasources.connection_manager import ConnectionManager

            if not table_name:
                raise HTTPException(
                    status_code=400, detail="table_name required for database assets"
                )

            # Get datasource
            datasource = (
                db.query(DataSource)
                .filter(DataSource.id == asset_id, DataSource.workspace_id == workspace_id)
                .first()
            )

            if not datasource:
                raise HTTPException(status_code=404, detail="Data source not found")

            # Connect and query (await instead of asyncio.run)
            connector = await ConnectionManager.get_connector(
                datasource.type, datasource.connection_config
            )

            # First, get actual row count
            count_query = f"SELECT COUNT(*) as total FROM {table_name}"
            count_df = pd.read_sql(count_query, connector.connection)
            actual_row_count = int(count_df.iloc[0]["total"])

            # Sample data for profiling (limit to avoid memory issues)
            query = f"SELECT * FROM {table_name} LIMIT 10000"
            df = pd.read_sql(query, connector.connection)

            # Disconnect (await instead of asyncio.run)
            await connector.disconnect()

            # Profile the dataframe with actual row count
            profile = profiler.profile_dataframe(df, actual_row_count)

            return DataProfileResponse(**profile)

        # Handle file assets
        else:
            # Find file path (supports both local and MinIO)
            file_path = None

            # Check MinIO first
            if settings.STORAGE_TYPE == "minio" and minio_client:
                try:
                    # List objects with this prefix
                    objects = list(
                        minio_client.list_objects(settings.MINIO_BUCKET, prefix=asset_id)
                    )
                    if objects:
                        file_path = f"minio://{settings.MINIO_BUCKET}/{objects[0].object_name}"
                except Exception:
                    pass

            # Fall back to local storage
            if not file_path:
                upload_dir = Path(file_service.upload_dir)
                matching_files = list(upload_dir.glob(f"{asset_id}.*"))
                if matching_files:
                    file_path = str(matching_files[0])

            if not file_path:
                raise HTTPException(status_code=404, detail="File not found")

            # Parse file
            parse_result = file_service.parse_file(file_path, asset_type, Path(file_path).name)

            # Profile data with actual row count
            profile = profiler.profile_dataframe(parse_result.data, parse_result.row_count)

            return DataProfileResponse(**profile)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to profile asset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/temp-files/{file_id}")
async def cleanup_temp_file(file_id: str) -> dict:
    """
    Delete a temporary uploaded file.

    - file_id: ID from upload response (without extension)
    """
    try:
        from pathlib import Path

        # Find and delete file with this ID (any extension)
        upload_dir = Path(file_service.upload_dir)
        matching_files = list(upload_dir.glob(f"{file_id}.*"))

        deleted_count = 0
        for file_path in matching_files:
            file_service.cleanup_file(str(file_path))
            deleted_count += 1

        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="File not found")

        return {"message": f"Deleted {deleted_count} file(s) successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cleanup file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/data-assets")
async def list_data_assets(workspace_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """
    List all available data assets for an organization.

    This includes:
    - Database tables from connected data sources
    - Uploaded files (CSV, Excel, Parquet, JSON)
    """

    def to_native_type(value):
        """Convert numpy types to native Python types for JSON serialization."""
        if value is None:
            return None
        # Convert numpy bool to Python bool
        if hasattr(value, "item"):  # numpy types have .item() method
            return value.item()
        return value

    try:
        from pathlib import Path

        from app.models.datasource import DataSource
        from app.services.datasources.connection_manager import ConnectionManager

        assets = []

        # 1. Get database-based assets from data sources
        data_sources = (
            db.query(DataSource)
            .filter(DataSource.workspace_id == workspace_id, DataSource.status == "active")
            .all()
        )

        for ds in data_sources:
            try:
                # Get connector (await instead of asyncio.run)
                connector = await ConnectionManager.get_connector(ds.type, ds.connection_config)

                # Get list of tables (await instead of asyncio.run)
                tables = await connector.get_tables()

                # Add each table as a separate asset
                for table_info in tables:
                    table_name = table_info.get("table_name")
                    schema_name = table_info.get("schema_name", "public")
                    database_name = (
                        ds.connection_config.get("database") if ds.connection_config else None
                    )

                    # Try to get columns for this table
                    columns = []
                    try:
                        columns_data = await connector.get_columns(table_name, schema_name)
                        columns = [
                            {
                                "column_name": col.get("column_name"),
                                "column_type": col.get("data_type"),
                                "is_nullable": bool(col.get("is_nullable", True)),
                                "is_primary_key": bool(col.get("is_primary_key", False)),
                            }
                            for col in columns_data
                        ]
                    except Exception as col_error:
                        logger.debug(
                            f"Could not fetch columns for {schema_name}.{table_name}: {str(col_error)}"
                        )

                    # Build full qualified name: database.schema.table
                    if database_name:
                        full_table_name = f"{database_name}.{schema_name}.{table_name}"
                        display_table_name = full_table_name
                    else:
                        full_table_name = f"{schema_name}.{table_name}"
                        display_table_name = full_table_name

                    asset = {
                        "id": f"{ds.id}:{schema_name}.{table_name}",  # Composite ID
                        "name": display_table_name,
                        "type": "table",
                        "source": ds.type,
                        "status": "active",
                        "last_updated": ds.last_tested_at.isoformat()
                        if ds.last_tested_at
                        else None,
                        "metadata": {
                            "datasource_id": ds.id,
                            "datasource_name": ds.name,
                            "table_name": f"{schema_name}.{table_name}",  # schema.table for querying
                            "schema_name": schema_name,
                            "database_name": database_name,
                            "connection_type": ds.type,
                            "host": ds.connection_config.get("host")
                            if ds.connection_config
                            else None,
                            "database": database_name,
                            "rows": table_info.get("row_count"),
                            "columns": columns,
                        },
                    }
                    assets.append(asset)

                # Close connector (await instead of asyncio.run)
                await connector.disconnect()
            except Exception as e:
                logger.warning(f"Could not list tables for datasource {ds.id}: {str(e)}")
                # Still add the datasource itself as an asset
                asset = {
                    "id": ds.id,
                    "name": ds.name,
                    "type": "database",
                    "source": ds.type,
                    "status": ds.status,
                    "last_updated": ds.last_tested_at.isoformat() if ds.last_tested_at else None,
                    "metadata": {
                        "connection_type": ds.type,
                        "host": ds.connection_config.get("host") if ds.connection_config else None,
                        "database": ds.connection_config.get("database")
                        if ds.connection_config
                        else None,
                        "error": "Could not list tables",
                    },
                }
                assets.append(asset)

        # 2. Get uploaded file assets from MinIO or local storage
        if settings.STORAGE_TYPE == "minio" and minio_client:
            # List files from MinIO
            try:
                objects = minio_client.list_objects(settings.MINIO_BUCKET)
                for obj in objects:
                    ext = Path(obj.object_name).suffix.lower()

                    # Determine file type
                    if ext in [".csv", ".txt", ".tsv"]:
                        file_type = "csv"
                    elif ext in [".xlsx", ".xls"]:
                        file_type = "excel"
                    elif ext in [".json", ".jsonl"]:
                        file_type = "json"
                    elif ext == ".parquet":
                        file_type = "parquet"
                    else:
                        continue  # Skip unsupported files

                    # Get object metadata
                    file_id = Path(obj.object_name).stem

                    # Get metadata from MinIO object
                    try:
                        stat_obj = minio_client.stat_object(settings.MINIO_BUCKET, obj.object_name)
                        original_filename = stat_obj.metadata.get(
                            "x-amz-meta-original-filename", obj.object_name
                        )
                    except:
                        original_filename = obj.object_name

                    # Try to get row count and columns
                    row_count = None
                    columns = []
                    try:
                        file_path = f"minio://{settings.MINIO_BUCKET}/{obj.object_name}"
                        parse_result = file_service.parse_file(
                            file_path, file_type, original_filename
                        )
                        row_count = parse_result.row_count
                        # Extract column information
                        columns = [
                            {
                                "column_name": col.name,
                                "data_type": col.inferred_type,
                                "is_nullable": bool(to_native_type(col.nullable)),
                            }
                            for col in parse_result.columns
                        ]
                    except Exception as e:
                        logger.debug(f"Could not parse file {obj.object_name}: {str(e)}")
                        pass

                    asset = {
                        "id": file_id,
                        "name": original_filename,
                        "type": file_type,
                        "source": "Uploaded",
                        "status": "active",
                        "last_updated": obj.last_modified.timestamp()
                        if obj.last_modified
                        else None,
                        "metadata": {
                            "file_size": obj.size,
                            "file_path": file_path,
                            "rows": row_count,
                            "columns": columns,
                        },
                    }
                    assets.append(asset)
            except Exception as e:
                logger.error(f"Failed to list MinIO objects: {str(e)}")

        # Also check local storage as fallback
        else:
            upload_dir = Path(file_service.upload_dir)
            if upload_dir.exists():
                for file_path in upload_dir.iterdir():
                    if file_path.is_file():
                        # Get file stats
                        stat = file_path.stat()
                        ext = file_path.suffix.lower()

                        # Determine file type
                        if ext in [".csv", ".txt", ".tsv"]:
                            file_type = "csv"
                        elif ext in [".xlsx", ".xls"]:
                            file_type = "excel"
                        elif ext in [".json", ".jsonl"]:
                            file_type = "json"
                        elif ext == ".parquet":
                            file_type = "parquet"
                        else:
                            continue  # Skip unsupported files

                        # Try to get row count and columns
                        row_count = None
                        columns = []
                        try:
                            parse_result = file_service.parse_file(
                                str(file_path), file_type, file_path.name
                            )
                            row_count = parse_result.row_count
                            # Extract column information
                            columns = [
                                {
                                    "column_name": col.name,
                                    "data_type": col.inferred_type,
                                    "is_nullable": bool(to_native_type(col.nullable)),
                                }
                                for col in parse_result.columns
                            ]
                        except:
                            pass

                        asset = {
                            "id": file_path.stem,  # Filename without extension
                            "name": file_path.name,
                            "type": file_type,
                            "source": "Uploaded",
                            "status": "active",
                            "last_updated": stat.st_mtime,
                            "metadata": {
                                "file_size": stat.st_size,
                                "file_path": str(file_path),
                                "rows": row_count,
                                "columns": columns,
                            },
                        }
                        assets.append(asset)

        logger.info(f"Found {len(assets)} data assets for org {workspace_id}")
        return assets

    except Exception as e:
        logger.error(f"Failed to list data assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
