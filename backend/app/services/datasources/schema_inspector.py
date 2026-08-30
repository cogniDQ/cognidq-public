"""Schema inspector for introspecting database structures."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.datasource import DataSource, DataSourceSchema
from app.services.datasources.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class SchemaInspector:
    """
    Inspects and caches database schema metadata.
    """

    @classmethod
    async def refresh_schema(cls, db: Session, datasource: DataSource) -> int:
        """
        Refresh schema metadata for a data source.
        Introspects database structure and updates data_source_schemas table.

        Args:
            db: Database session
            datasource: DataSource model instance

        Returns:
            Number of columns discovered
        """
        try:
            logger.info(f"Refreshing schema for datasource: {datasource.name}")

            # Get connector
            connector = await ConnectionManager.get_connector(
                datasource.type, datasource.connection_config
            )

            async with connector:
                # Get all schemas
                schemas = await connector.get_schemas()
                logger.info(f"Found {len(schemas)} schemas")

                total_columns = 0

                for schema_name in schemas:
                    # Get tables in schema
                    tables = await connector.get_tables(schema_name)
                    logger.info(f"Found {len(tables)} tables in schema {schema_name}")

                    for table_info in tables:
                        # Get columns for each table
                        columns = await connector.get_columns(table_info["table_name"], schema_name)

                        for column in columns:
                            # Check if column metadata already exists
                            existing = (
                                db.query(DataSourceSchema)
                                .filter(
                                    DataSourceSchema.data_source_id == datasource.id,
                                    DataSourceSchema.schema_name == schema_name,
                                    DataSourceSchema.table_name == table_info["table_name"],
                                    DataSourceSchema.column_name == column["column_name"],
                                )
                                .first()
                            )

                            if existing:
                                # Update existing
                                existing.column_type = column["column_type"]
                                existing.is_nullable = column["is_nullable"]
                                existing.is_primary_key = column["is_primary_key"]
                                existing.default_value = column.get("default_value")
                                existing.meta_data = column.get("metadata", {})
                                existing.refreshed_at = datetime.utcnow()
                            else:
                                # Create new
                                schema_metadata = DataSourceSchema(
                                    data_source_id=datasource.id,
                                    schema_name=schema_name,
                                    table_name=table_info["table_name"],
                                    column_name=column["column_name"],
                                    column_type=column["column_type"],
                                    is_nullable=column["is_nullable"],
                                    is_primary_key=column["is_primary_key"],
                                    default_value=column.get("default_value"),
                                    meta_data=column.get("metadata", {}),
                                    refreshed_at=datetime.utcnow(),
                                )
                                db.add(schema_metadata)

                            total_columns += 1

                db.commit()
                logger.info(f"Schema refresh complete. Discovered {total_columns} columns.")
                return total_columns

        except Exception as e:
            logger.error(f"Schema refresh failed: {e}")
            db.rollback()
            raise

    @classmethod
    async def get_schema_metadata(cls, db: Session, datasource_id: str) -> dict[str, Any]:
        """
        Get cached schema metadata for a data source.

        Args:
            db: Database session
            datasource_id: Data source ID

        Returns:
            Dictionary with schema metadata organized by schema/table/columns
        """
        # Query all schema metadata for this datasource
        metadata_records = (
            db.query(DataSourceSchema)
            .filter(DataSourceSchema.data_source_id == datasource_id)
            .order_by(
                DataSourceSchema.schema_name,
                DataSourceSchema.table_name,
                DataSourceSchema.column_name,
            )
            .all()
        )

        if not metadata_records:
            return {"data_source_id": datasource_id, "tables": [], "refreshed_at": None}

        # Organize by schema -> table -> columns
        tables_dict = {}
        last_refreshed = None

        for record in metadata_records:
            table_key = f"{record.schema_name}.{record.table_name}"

            if table_key not in tables_dict:
                tables_dict[table_key] = {
                    "schema_name": record.schema_name,
                    "table_name": record.table_name,
                    "columns": [],
                }

            tables_dict[table_key]["columns"].append(
                {
                    "column_name": record.column_name,
                    "column_type": record.column_type,
                    "is_nullable": record.is_nullable,
                    "is_primary_key": record.is_primary_key,
                    "default_value": record.default_value,
                    "metadata": record.meta_data,
                }
            )

            if not last_refreshed or record.refreshed_at > last_refreshed:
                last_refreshed = record.refreshed_at

        return {
            "data_source_id": datasource_id,
            "tables": list(tables_dict.values()),
            "refreshed_at": last_refreshed,
        }

    @classmethod
    async def get_preview_data(
        cls, datasource: DataSource, schema_name: str | None, table_name: str, limit: int = 100
    ) -> dict[str, Any]:
        """
        Get sample data from a table.

        Args:
            datasource: DataSource model instance
            schema_name: Schema name (optional)
            table_name: Table name
            limit: Number of rows to preview

        Returns:
            Dictionary with preview data
        """
        try:
            connector = await ConnectionManager.get_connector(
                datasource.type, datasource.connection_config
            )

            async with connector:
                # Get sample data
                rows = await connector.get_sample_data(table_name, schema_name, limit)

                # Get row count
                total_rows = await connector.get_row_count(table_name, schema_name)

                # Extract column names from first row if available
                columns = list(rows[0].keys()) if rows else []

                return {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "columns": columns,
                    "rows": rows,
                    "total_rows": total_rows,
                    "preview_rows": len(rows),
                }
        except Exception as e:
            logger.error(f"Preview data failed: {e}")
            raise
