"""
Spark Connector - Uses Apache Spark for distributed data quality checks
"""

import logging
from decimal import Decimal
from typing import Any

from pyspark.sql import DataFrame, SparkSession

from app.services.datasources.connectors.base import BaseConnector
from app.services.execution.spark_session_manager import SparkSessionManager

logger = logging.getLogger(__name__)


class SparkConnector(BaseConnector):
    """
    Connector that uses Spark for data source access and processing.
    Supports JDBC sources (PostgreSQL, MySQL, etc.) and cloud storage.
    """

    def __init__(self, connection_config: dict[str, Any]):
        super().__init__(connection_config)
        self.spark_session: SparkSession | None = None
        self.source_type = connection_config.get("type", "postgresql")
        self.session_manager = SparkSessionManager.get_instance()

    async def connect(self):
        """Initialize Spark session via session manager"""
        try:
            self.spark_session = self.session_manager.get_session()
            logger.info(f"Spark connector initialized for {self.source_type}")
        except Exception as e:
            logger.error(f"Failed to initialize Spark session: {e}")
            raise

    async def disconnect(self):
        """
        Disconnect - Note: We don't close the shared session,
        just release our reference to it.
        """
        self.spark_session = None
        logger.info(f"Spark connector disconnected from {self.source_type}")

    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Test connection by attempting to read from data source"""
        try:
            await self.connect()

            # Try to read a simple query to test connection
            test_query = "(SELECT 1 as test) as test_query"
            df = self._read_jdbc_table(test_query)
            count = df.count()

            details = {
                "spark_version": self.spark_session.version,
                "source_type": self.source_type,
                "test_result": count,
            }

            return True, "Connection successful via Spark", details

        except Exception as e:
            logger.error(f"Spark connection test failed: {e}")
            return False, f"Connection failed: {str(e)}", None
        finally:
            await self.disconnect()

    async def get_schemas(self) -> list[str]:
        """Get list of available schemas/databases"""
        try:
            if self.source_type == "postgresql":
                query = """
                (SELECT schema_name 
                 FROM information_schema.schemata 
                 WHERE schema_name NOT IN ('information_schema', 'pg_catalog')
                ) as schemas
                """
                df = self._read_jdbc_table(query)
                schemas = [row.schema_name for row in df.collect()]
                return schemas
            else:
                # For other sources, use Spark catalog
                return [db.name for db in self.spark_session.catalog.listDatabases()]

        except Exception as e:
            logger.error(f"Failed to get schemas: {e}")
            return []

    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        """Get list of tables in a schema"""
        try:
            if self.source_type == "postgresql":
                schema_filter = f"AND table_schema = '{schema_name}'" if schema_name else ""
                query = f"""
                (SELECT table_schema, table_name
                 FROM information_schema.tables
                 WHERE table_type = 'BASE TABLE'
                 {schema_filter}
                ) as tables
                """
                df = self._read_jdbc_table(query)

                tables = []
                for row in df.collect():
                    tables.append({"schema_name": row.table_schema, "table_name": row.table_name})
                return tables
            else:
                # Use Spark catalog
                tables = []
                for table in self.spark_session.catalog.listTables(schema_name):
                    tables.append(
                        {"schema_name": schema_name or "default", "table_name": table.name}
                    )
                return tables

        except Exception as e:
            logger.error(f"Failed to get tables: {e}")
            return []

    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        """Get column metadata for a table"""
        try:
            if self.source_type == "postgresql":
                schema_filter = f"AND table_schema = '{schema_name}'" if schema_name else ""
                query = f"""
                (SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                 FROM information_schema.columns
                 WHERE table_name = '{table_name}'
                 {schema_filter}
                 ORDER BY ordinal_position
                ) as columns
                """
                df = self._read_jdbc_table(query)

                columns = []
                for row in df.collect():
                    columns.append(
                        {
                            "column_name": row.column_name,
                            "column_type": row.data_type,
                            "is_nullable": row.is_nullable == "YES",
                            "is_primary_key": False,  # Would need additional query
                            "default_value": row.column_default,
                            "metadata": {"max_length": row.character_maximum_length},
                        }
                    )
                return columns
            else:
                # Use Spark to infer schema
                df = self.read_table(table_name, schema_name)
                columns = []
                for field in df.schema.fields:
                    columns.append(
                        {
                            "column_name": field.name,
                            "column_type": str(field.dataType),
                            "is_nullable": field.nullable,
                            "is_primary_key": False,
                            "metadata": {},
                        }
                    )
                return columns

        except Exception as e:
            logger.error(f"Failed to get columns: {e}")
            return []

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Execute SQL query via Spark and return results.

        Args:
            query: SQL query string (can be Spark SQL or wrapped JDBC query)
            params: Query parameters (not used in Spark SQL)

        Returns:
            Dictionary with 'rows' and metadata
        """
        import asyncio

        def _execute_sync():
            """Execute Spark query synchronously in thread pool"""
            try:
                # If query looks like a JDBC subquery (wrapped in parentheses), use JDBC read
                if query.strip().startswith("(") and "as " in query.lower():
                    df = self._read_jdbc_table(query)
                else:
                    # Register a temp view and execute as Spark SQL
                    # First, we need to load the source table
                    # For now, execute as raw SQL
                    df = self.spark_session.sql(query)

                # Collect results - this triggers Spark job execution
                logger.info("Starting Spark job execution (collect)")
                rows = df.collect()
                logger.info(f"Spark job completed, collected {len(rows)} rows")

                # Allow event logs to flush
                import time

                time.sleep(2)
                logger.info("Event logs flushed")

                # Convert to list of dicts or tuples
                result_rows = []
                for row in rows:
                    # Convert Row to dict or tuple based on structure
                    try:
                        result_rows.append(row.asDict())
                    except:
                        result_rows.append(tuple(row))

                # Force SparkContext to wait for all tasks to complete
                self.spark_session.sparkContext.setJobGroup("dq_check", "Data Quality Check")

                return {"rows": result_rows, "row_count": len(result_rows), "columns": df.columns}

            except Exception as e:
                logger.error(f"Failed to execute query: {e}")
                raise

        # Run Spark operation in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _execute_sync)

    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        """Get row count for a table using Spark"""
        try:
            logger.info(f"Getting row count for {schema_name}.{table_name} via Spark")
            df = self.read_table(table_name, schema_name)
            count = df.count()
            logger.info(f"Row count retrieved: {count}")
            return count
        except Exception as e:
            logger.error(f"Failed to get row count via Spark: {e}", exc_info=True)
            return 0

    def read_table(self, table_name: str, schema_name: str | None = None) -> DataFrame:
        """
        Read table into Spark DataFrame.

        Args:
            table_name: Table name
            schema_name: Schema name (optional)

        Returns:
            Spark DataFrame
        """
        full_table = f"{schema_name}.{table_name}" if schema_name else table_name

        if self.source_type in ["postgresql", "mysql", "sqlserver"]:
            return self._read_jdbc_table(full_table)
        elif self.source_type == "snowflake":
            return self._read_snowflake_table(full_table)
        elif self.source_type == "s3":
            return self._read_s3_data(full_table)
        else:
            raise ValueError(f"Unsupported source type for Spark: {self.source_type}")

    def _read_jdbc_table(self, table_or_query: str) -> DataFrame:
        """Read from JDBC source (PostgreSQL, MySQL, etc.)"""
        try:
            logger.info(f"Reading JDBC table: {table_or_query}")

            jdbc_url = self._build_jdbc_url()
            logger.info(f"JDBC URL: {jdbc_url}")

            # Extract credentials
            username = self.connection_config.get("username")
            password = self.connection_config.get("password")

            # Additional JDBC properties
            properties = {"user": username, "password": password, "driver": self._get_jdbc_driver()}

            logger.info(
                f"JDBC properties (without password): user={username}, driver={properties['driver']}"
            )

            # Add connection pool settings
            properties["numPartitions"] = self.connection_config.get("spark_partitions", "4")

            logger.info("About to read table via JDBC...")
            df = self.spark_session.read.jdbc(
                url=jdbc_url, table=table_or_query, properties=properties
            )

            logger.info(f"DataFrame created, schema: {df.schema}")
            logger.info("JDBC table read complete (lazy evaluation - no data loaded yet)")

            return df
        except Exception as e:
            logger.error(f"Failed to read JDBC table: {e}", exc_info=True)
            raise

        # SSL/TLS settings
        if self.connection_config.get("ssl", False):
            properties["ssl"] = "true"
            properties["sslmode"] = self.connection_config.get("sslmode", "require")

        return self.spark_session.read.jdbc(
            url=jdbc_url, table=table_or_query, properties=properties
        )

    def _read_snowflake_table(self, table_name: str) -> DataFrame:
        """Read from Snowflake"""
        sf_options = {
            "sfURL": self.connection_config.get("account"),
            "sfUser": self.connection_config.get("username"),
            "sfPassword": self.connection_config.get("password"),
            "sfDatabase": self.connection_config.get("database"),
            "sfSchema": self.connection_config.get("schema", "PUBLIC"),
            "sfWarehouse": self.connection_config.get("warehouse"),
        }

        return (
            self.spark_session.read.format("snowflake")
            .options(**sf_options)
            .option("dbtable", table_name)
            .load()
        )

    def _read_s3_data(self, path: str) -> DataFrame:
        """Read from S3"""
        file_format = self.connection_config.get("format", "parquet")
        s3_path = f"s3a://{self.connection_config.get('bucket')}/{path}"

        return self.spark_session.read.format(file_format).load(s3_path)

    def _build_jdbc_url(self) -> str:
        """Build JDBC URL from connection config"""
        host = self.connection_config.get("host")
        port = self.connection_config.get("port")
        database = self.connection_config.get("database")

        if self.source_type == "postgresql":
            return f"jdbc:postgresql://{host}:{port}/{database}"
        elif self.source_type == "mysql":
            return f"jdbc:mysql://{host}:{port}/{database}"
        elif self.source_type == "sqlserver":
            return f"jdbc:sqlserver://{host}:{port};databaseName={database}"
        else:
            raise ValueError(f"Unknown JDBC source type: {self.source_type}")

    def _get_jdbc_driver(self) -> str:
        """Get JDBC driver class name"""
        drivers = {
            "postgresql": "org.postgresql.Driver",
            "mysql": "com.mysql.cj.jdbc.Driver",
            "sqlserver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
        }
        return drivers.get(self.source_type, "org.postgresql.Driver")

    async def execute_check_query(self, query: str, dimension: str) -> dict[str, Any]:
        """
        Execute data quality check query optimized for Spark.
        Returns formatted results for check execution.

        Args:
            query: SQL query to execute
            dimension: Check dimension (completeness, validity, etc.)

        Returns:
            Dictionary with check results
        """
        import asyncio

        def _execute_check_sync():
            """Execute check query synchronously to ensure Spark job completes"""
            try:
                # Extract table name from query to load it first
                # Query format: SELECT ... FROM schema.table WHERE ...
                import re

                table_match = re.search(
                    r'FROM\s+(["\']?)(\w+)\1\.(["\']?)(\w+)\3', query, re.IGNORECASE
                )

                if table_match:
                    schema_name = table_match.group(2)
                    table_name = table_match.group(4)

                    logger.info(
                        f"Loading table {schema_name}.{table_name} into Spark for check query"
                    )

                    # Load the table from PostgreSQL into a Spark DataFrame
                    df = self.read_table(table_name, schema_name)

                    # Create temporary view for SQL query
                    temp_view_name = f"{schema_name}_{table_name}_temp"
                    df.createOrReplaceTempView(temp_view_name)

                    # Replace schema.table with temp view name in query
                    modified_query = re.sub(
                        r'FROM\s+["\']?\w+["\']?\.["\']?\w+["\']?',
                        f"FROM {temp_view_name}",
                        query,
                        flags=re.IGNORECASE,
                    )

                    logger.info(f"Executing Spark SQL query: {modified_query[:200]}...")

                    # Execute the query and collect results
                    result_df = self.spark_session.sql(modified_query)
                    logger.info("Query plan created, starting Spark job execution")

                    # This triggers the actual Spark job
                    rows = result_df.collect()
                    logger.info(f"Spark job completed successfully, collected {len(rows)} rows")

                    # Force Spark to wait for all executors to complete and flush event logs
                    self.spark_session.sparkContext.setJobGroup("", "")
                    import time

                    time.sleep(2)  # Allow event logs to flush
                    logger.info("Event logs flushed")

                    # Convert rows to dicts
                    result_rows = []
                    for row in rows:
                        try:
                            result_rows.append(row.asDict())
                        except:
                            result_rows.append(tuple(row))

                    result = {
                        "rows": result_rows,
                        "row_count": len(result_rows),
                        "columns": result_df.columns,
                    }
                else:
                    # Fallback to direct execution
                    logger.warning("Could not extract table name from query, executing directly")
                    result_df = self.spark_session.sql(query)
                    rows = result_df.collect()

                    result_rows = []
                    for row in rows:
                        try:
                            result_rows.append(row.asDict())
                        except:
                            result_rows.append(tuple(row))

                    result = {
                        "rows": result_rows,
                        "row_count": len(result_rows),
                        "columns": result_df.columns,
                    }

                rows = result.get("rows", [])

                if not rows or len(rows) == 0:
                    return {
                        "rows_scanned": 0,
                        "rows_passed": 0,
                        "rows_failed": 0,
                        "pass_rate": Decimal(0),
                    }

                # Parse first row - should contain aggregated counts
                row = rows[0]

                # Handle both dict and tuple responses
                if isinstance(row, dict):
                    total_rows = int(row.get("total_rows", 0))

                    # Handle different check dimensions:
                    # completeness:  total_rows, non_null_rows, null_rows, completeness_rate
                    # validity:      total_rows, valid_rows, invalid_rows, validity_rate
                    # uniqueness:    total_rows, unique_rows, duplicate_rows, uniqueness_rate
                    # generic:       total_rows, failed_rows
                    if "null_rows" in row:
                        failed_rows = int(row.get("null_rows", 0))
                    elif "invalid_rows" in row:
                        failed_rows = int(row.get("invalid_rows", 0))
                    elif "duplicate_rows" in row:
                        failed_rows = int(row.get("duplicate_rows", 0))
                    else:
                        failed_rows = int(row.get("failed_rows", 0))
                else:
                    total_rows = int(row[0]) if len(row) > 0 else 0
                    failed_rows = int(row[1]) if len(row) > 1 else 0

                passed_rows = total_rows - failed_rows

                # Calculate pass rate
                if total_rows == 0:
                    pass_rate = Decimal(100)
                else:
                    pass_rate = (Decimal(passed_rows) / Decimal(total_rows)) * Decimal(100)

                logger.info(
                    f"Check results: scanned={total_rows}, passed={passed_rows}, failed={failed_rows}, rate={pass_rate}%"
                )

                return {
                    "rows_scanned": total_rows,
                    "rows_passed": passed_rows,
                    "rows_failed": failed_rows,
                    "pass_rate": pass_rate,
                }

            except Exception as e:
                logger.error(f"Failed to execute check query: {e}", exc_info=True)
                raise

        # Run in thread pool to properly await Spark job completion
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _execute_check_sync)
