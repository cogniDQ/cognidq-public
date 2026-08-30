"""
Source Node Handler - Handles data source nodes
"""

import logging
from typing import Any
from uuid import UUID

from app.schemas.flow import NodeStatus
from app.services.flows.node_handlers.base import (
    BaseNodeHandler,
    NodeExecutionContext,
    NodeExecutionResult,
)

logger = logging.getLogger(__name__)


class SourceNodeHandler(BaseNodeHandler):
    """Handler for data source nodes"""

    def __init__(self):
        pass

    @staticmethod
    def _sanitize_table_name(file_name: str) -> str:
        """
        Sanitize file name to create valid Spark table name.

        Spark temporary view names must:
        - Be single-part (no dots except for file extensions to remove)
        - Contain only alphanumeric and underscore characters
        - Start with letter or underscore

        Args:
            file_name: Original file name

        Returns:
            Sanitized table name safe for Spark
        """
        import re
        from pathlib import Path

        # Remove file extension
        name = Path(file_name).stem

        # Replace any non-alphanumeric characters (except underscore) with underscore
        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)

        # Ensure it starts with letter or underscore (not a number)
        if name and name[0].isdigit():
            name = f"table_{name}"

        # If empty after sanitization, use default
        if not name:
            name = "file_data"

        return name

    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        """
        Execute source node - load data source metadata and sample data

        Supports both database tables and file-based sources (CSV, Excel, Parquet, JSON)

        Args:
            context: Node execution context

        Returns:
            NodeExecutionResult with source data information
        """
        try:
            config = context.node_config

            logger.info(f"\n{'=' * 60}")
            logger.info("📋 SOURCE NODE EXECUTION START")
            logger.info(f"   Node ID: {context.node_id}")
            logger.info(f"   Config: {config}")

            # Check if this is a file-based source or database source
            file_path = config.get("file_path")
            file_id = config.get("file_id")

            if file_path or file_id:
                logger.info("📄 Executing file-based source")
                # Handle file-based source (CSV, Excel, Parquet, JSON)
                return await self._execute_file_source(context, config)
            else:
                logger.info("📊 Executing database source")
                # Handle database source
                return await self._execute_database_source(context, config)

        except Exception as e:
            logger.error(f"❌ SOURCE NODE EXCEPTION: {type(e).__name__}: {str(e)}")
            logger.error("Exception details:", exc_info=True)
            return self.handle_error(e, context)

    async def _execute_file_source(
        self, context: NodeExecutionContext, config: dict[str, Any]
    ) -> NodeExecutionResult:
        """Execute file-based source node - Unified with database sources"""
        try:
            from app.services.ingestion.file_upload import FileUploadService

            logger.info("📁 Processing file source...")

            file_service = FileUploadService()

            file_path = config.get("file_path")
            file_id = config.get("file_id")
            file_name = config.get("file_name") or config.get("name", "Unknown File")
            file_type = config.get("file_type") or config.get("type", "csv")

            logger.info(f"   File ID: {file_id}")
            logger.info(f"   File Name: {file_name}")
            logger.info(f"   File Type: {file_type}")
            logger.info(f"   File Path: {file_path}")

            # Get file path from file_id if not provided
            if not file_path and file_id:
                from pathlib import Path

                upload_dir = Path(file_service.upload_dir)
                matching_files = list(upload_dir.glob(f"{file_id}.*"))
                logger.info(f"🔍 Searching for file with ID {file_id} in {upload_dir}")
                logger.info(f"   Found {len(matching_files)} matching files")
                if matching_files:
                    file_path = str(matching_files[0])
                    logger.info(f"✅ Found file: {file_path}")

            if not file_path:
                logger.error(f"❌ File not found for file_id: {file_id}")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED, error_message=f"File not found for file_id: {file_id}"
                )

            # Parse the file to get columns and data
            logger.info(f"📂 Parsing file: {file_path}")
            parse_result = file_service.parse_file(file_path, file_type, file_name)
            logger.info("✅ File parsed successfully")
            logger.info(f"   Rows: {parse_result.row_count}")
            logger.info(f"   Columns: {len(parse_result.columns)}")

            # Extract columns in same format as database sources
            columns = []
            for col in parse_result.columns:
                col_dict = col.to_dict()  # Use to_dict() for proper type conversion
                columns.append(
                    {
                        "name": col_dict["name"],
                        "data_type": col_dict["inferred_type"],
                        "type": col_dict["inferred_type"],
                        "nullable": col_dict["nullable"],
                    }
                )

            # Build result_data - SAME FORMAT as database sources
            result_data = {
                "source_name": file_name,
                "source_type": "file",
                "rows_scanned": parse_result.row_count or 0,
                "schema_version": "v1.0",
                "columns": [col["name"] for col in columns],
                "schema_drift": False,  # Not tracked for files
                # Legacy fields for backward compatibility
                "file_path": file_path,
                "file_name": file_name,
                "file_type": file_type,
                "row_count": parse_result.row_count,
                "sample_size": parse_result.row_count,
            }

            # Create UNIFIED output_data format - compatible with check nodes
            # File sources provide dataframe AND mock data_source structure

            # Convert DataFrame to JSON-serializable format (list of dicts)
            # Only store a sample to avoid large data in DB
            sample_size = min(1000, parse_result.row_count or 0)
            sample_data = (
                parse_result.data.head(sample_size).to_dict("records")
                if parse_result.data is not None
                else []
            )

            # Sanitize file name for use as Spark table name
            sanitized_table_name = self._sanitize_table_name(file_name)
            logger.info(f"   Original filename: {file_name}")
            logger.info(f"   Sanitized table name: {sanitized_table_name}")

            output_data = {
                # Mock data_source structure for check node compatibility
                "data_source": {
                    "id": file_id or "file_source",
                    "name": file_name,
                    "type": "file",  # Indicates this is a file source
                    "file_type": file_type,
                    "file_path": file_path,
                    "workspace_id": str(context.workspace_id),
                },
                "schema_name": "default",  # Files don't have schemas
                "table_name": sanitized_table_name,  # Use sanitized name for Spark compatibility
                "columns": columns,
                "row_count": parse_result.row_count,
                # Sample data as list of dicts (JSON-serializable)
                "sample_data": sample_data,
                "sample_size": len(sample_data),
                # Mark as file source for special handling
                "is_file_source": True,
            }

            logger.info("\n📤 FILE SOURCE OUTPUT:")
            logger.info(f"   Source Name: {file_name}")
            logger.info(f"   Table Name (sanitized): {sanitized_table_name}")
            logger.info(f"   Columns: {[col['name'] for col in columns]}")
            logger.info(f"   Row Count: {parse_result.row_count}")
            logger.info(f"   Sample Size: {len(sample_data)}")
            logger.info(
                f"   DataFrame shape: {parse_result.data.shape if parse_result.data is not None else 'None'}"
            )
            logger.info(f"   DataFrame is None: {parse_result.data is None}")
            logger.info(
                f"   DataFrame memory: {parse_result.data.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB"
                if parse_result.data is not None
                else "   No DataFrame"
            )
            logger.info("✅ FILE SOURCE NODE COMPLETE")
            logger.info(f"{'=' * 60}\n")

            return NodeExecutionResult(
                status=NodeStatus.COMPLETED, result_data=result_data, output_data=output_data
            )

        except Exception as e:
            logger.error(f"❌ Error executing file source node: {type(e).__name__}: {str(e)}")
            logger.error("Exception details:", exc_info=True)
            return NodeExecutionResult(
                status=NodeStatus.FAILED, error_message=f"Failed to load file source: {str(e)}"
            )

    async def _execute_database_source(
        self, context: NodeExecutionContext, config: dict[str, Any]
    ) -> NodeExecutionResult:
        """Execute database source node — queries control.data_sources for credentials."""
        try:
            from sqlalchemy import text as sa_text

            from app.models.flow import FlowExecution, FlowNodeResult
            from app.services.data_sources import credential_service as cred_svc

            logger.info("📊 Processing database source...")

            # Get data source
            data_source_id = config.get("data_source_id")
            logger.info(f"   Data Source ID: {data_source_id}")

            if not data_source_id:
                logger.error("❌ No data_source_id specified")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message="No data_source_id specified in source node configuration",
                )

            # Validate UUID
            try:
                data_source_uuid = UUID(data_source_id)
            except (ValueError, AttributeError):
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message=f"Invalid data_source_id format: '{data_source_id}'. Must be a valid UUID.",
                )

            # ── Look up data source from control.data_sources ────────────────
            # Resolve in two ways:
            #   (a) Workspace-owned connection: workspace_id = :ws_id.
            #   (b) Tenant-owned connection (workspace_id IS NULL) that has been
            #       assigned to this workspace via
            #       control.workspace_connection_assignments.
            logger.info("🔍 Looking up data source in control.data_sources...")
            row = context.db.execute(
                sa_text("""
                    SELECT data_source_id, source_name, source_type, credential_reference
                    FROM control.data_sources
                    WHERE data_source_id = CAST(:ds_id AS UUID)
                      AND archived_at IS NULL
                      AND (
                            workspace_id = CAST(:ws_id AS UUID)
                         OR (
                                workspace_id IS NULL
                            AND data_source_id IN (
                                SELECT connection_id
                                FROM control.workspace_connection_assignments
                                WHERE workspace_id = CAST(:ws_id AS UUID)
                            )
                         )
                      )
                """),
                {"ds_id": str(data_source_uuid), "ws_id": str(context.workspace_id)},
            ).fetchone()

            if not row:
                logger.error(f"❌ Data source {data_source_id} not found in control.data_sources")
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message=f"Data source {data_source_id} not found",
                )

            ds_id, ds_name, ds_type, cred_ref = row
            logger.info(f"✅ Found data source: {ds_name} (type: {ds_type})")

            # ── Decrypt credentials ──────────────────────────────────────────
            creds: dict[str, Any] = {}
            if cred_ref is not None:
                cred_row = context.db.execute(
                    sa_text("""
                        SELECT encrypted_payload
                        FROM control.data_source_credentials
                        WHERE credential_id = CAST(:cred_id AS UUID)
                          AND superseded_at IS NULL
                    """),
                    {"cred_id": str(cred_ref)},
                ).fetchone()
                if cred_row and cred_row[0]:
                    creds = cred_svc.decrypt(bytes(cred_row[0]))
                    logger.info("✅ Credentials decrypted")
                else:
                    logger.warning("⚠️ No credentials found for data source")

            # Get schema and table from config
            schema_name = config.get("schema_name")
            table_name = config.get("table_name")

            logger.info(f"   Schema: {schema_name}")
            logger.info(f"   Table: {table_name}")

            if not schema_name or not table_name:
                return NodeExecutionResult(
                    status=NodeStatus.FAILED,
                    error_message="Source node must specify schema_name and table_name",
                )

            # ── Connect to the actual database and gather metadata ───────────
            import psycopg2 as pg2
            import psycopg2.extras

            conn = pg2.connect(
                host=creds.get("host"),
                port=int(creds.get("port", 5432)),
                database=creds.get("database"),
                user=creds.get("username"),
                password=creds.get("password"),
                connect_timeout=15,
            )
            conn.set_session(readonly=True, autocommit=True)
            logger.info("✅ Connected to target database")

            try:
                cur = conn.cursor()

                # ── Schema metadata (columns) ────────────────────────────────
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, table_name),
                )
                columns = [
                    {"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in cur.fetchall()
                ]
                logger.info(f"✅ Schema loaded: {len(columns)} columns")

                # ── Row count ────────────────────────────────────────────────
                # Use safe identifier quoting
                cur.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
                row_count = cur.fetchone()[0]
                logger.info(f"✅ Total rows: {row_count}")

                # ── Sample data ──────────────────────────────────────────────
                sample_size = context.execution_config.get("sample_size", 100)
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(
                    f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT %s',
                    (sample_size,),
                )
                sample_data = cur.fetchall()
                # Convert RealDictRow to plain dicts with JSON-safe values
                from datetime import date
                from datetime import datetime as dt_type
                from decimal import Decimal as Dec

                def _json_safe(v):
                    if isinstance(v, (dt_type, date)):
                        return v.isoformat()
                    if isinstance(v, Dec):
                        return float(v)
                    if isinstance(v, (bytes, bytearray, memoryview)):
                        return None
                    return v

                sample_data = [{k: _json_safe(v) for k, v in dict(r).items()} for r in sample_data]
                logger.info(f"✅ Sample data loaded: {len(sample_data)} rows")
            finally:
                conn.close()

            # ── Schema drift detection ───────────────────────────────────────
            previous_row_count = None
            schema_drift_detected = False

            previous_execution = (
                context.db.query(FlowExecution)
                .join(FlowNodeResult, FlowNodeResult.execution_id == FlowExecution.id)
                .filter(
                    FlowExecution.flow_id == context.flow_id,
                    FlowExecution.status == "completed",
                    FlowNodeResult.node_id == context.node_id,
                    FlowNodeResult.node_type == "source",
                )
                .order_by(FlowExecution.completed_at.desc())
                .first()
            )

            if previous_execution:
                prev_node_result = (
                    context.db.query(FlowNodeResult)
                    .filter(
                        FlowNodeResult.execution_id == previous_execution.id,
                        FlowNodeResult.node_id == context.node_id,
                    )
                    .first()
                )

                if prev_node_result and prev_node_result.result_data:
                    previous_row_count = prev_node_result.result_data.get("rows_scanned")
                    prev_columns = prev_node_result.result_data.get("columns", [])
                    prev_col_names = set(
                        col.get("name") if isinstance(col, dict) else col for col in prev_columns
                    )
                    curr_col_names = set(col["name"] for col in columns)
                    if prev_col_names != curr_col_names:
                        schema_drift_detected = True

            # ── Build result_data ────────────────────────────────────────────
            col_names = [c["name"] for c in columns]
            result_data = {
                "source_name": f"{ds_name} - {schema_name}.{table_name}",
                "source_type": ds_type,
                "rows_scanned": row_count or 0,
                "schema_version": "v1.0",
                "columns": col_names,
                "schema_drift": schema_drift_detected,
                "data_source_id": str(ds_id),
                "data_source_name": ds_name,
                "data_source_type": ds_type,
                "schema_name": schema_name,
                "table_name": table_name,
                "row_count": row_count,
                "sample_size": len(sample_data),
            }

            if previous_row_count is not None and row_count is not None and previous_row_count > 0:
                change_pct = ((row_count - previous_row_count) / previous_row_count) * 100
                result_data["volume_change"] = {
                    "previous": previous_row_count,
                    "change_percent": round(change_pct, 1),
                }

            # ── Output for downstream check nodes ────────────────────────────
            output_data = {
                "data_source": {
                    "id": str(ds_id),
                    "name": ds_name,
                    "type": ds_type,
                    "workspace_id": str(context.workspace_id),
                    "credential_reference": str(cred_ref) if cred_ref else None,
                },
                "schema_name": schema_name,
                "table_name": table_name,
                "columns": columns,
                "sample_data": sample_data,
                "row_count": row_count,
            }

            logger.info(
                f"📤 DATABASE SOURCE OUTPUT: {ds_name} {schema_name}.{table_name} "
                f"cols={len(columns)} rows={row_count}"
            )
            logger.info("✅ DATABASE SOURCE NODE COMPLETE")

            return NodeExecutionResult(
                status=NodeStatus.COMPLETED,
                result_data=result_data,
                output_data=output_data,
            )

        except Exception as e:
            logger.error(f"❌ Error executing database source node: {type(e).__name__}: {str(e)}")
            logger.error("Exception details:", exc_info=True)
            return self.handle_error(e, context)

    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate source node configuration

        Supports both database sources and file-based sources

        Args:
            config: Node configuration

        Returns:
            True if valid
        """
        # Check if it's a file-based source
        if "file_path" in config or "file_id" in config:
            # File-based source - just needs file_path or file_id
            return True

        # Database source - requires data_source_id, schema_name, and table_name
        required_fields = ["data_source_id", "schema_name", "table_name"]
        return all(field in config for field in required_fields)
