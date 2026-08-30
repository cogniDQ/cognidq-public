"""
Spark Check Executor
Executes data quality checks using Apache Spark for distributed processing.
"""

import logging
from decimal import Decimal
from typing import Any

from app.services.datasources.connectors.spark import SparkConnector
from app.services.execution.spark_session_manager import SparkSessionManager

logger = logging.getLogger(__name__)


class SparkCheckExecutor:
    """
    Execute data quality checks using Spark for scalability.

    Handles execution mode selection, connection management,
    and result processing for Spark-based checks.
    """

    def __init__(self):
        self.session_manager = SparkSessionManager.get_instance()

    async def execute_check(
        self,
        data_source_config: dict[str, Any],
        compiled_sql: str,
        canonical_rule: dict[str, Any],
        sample_only: bool = False,
    ) -> dict[str, Any]:
        """
        Execute check using Spark.

        Args:
            data_source_config: Data source connection configuration (encrypted)
            compiled_sql: Compiled Spark SQL query
            canonical_rule: Canonical rule definition
            sample_only: If True, limit rows for sampling

        Returns:
            Dictionary with execution results
        """
        connector = None
        try:
            # Decrypt connection config before creating connector
            from app.services.datasources.connection_manager import ConnectionManager

            decrypted_config = ConnectionManager.decrypt_config(
                data_source_config.get("connection_config", {})
            )

            # Add type to config
            decrypted_config["type"] = data_source_config.get("type", "postgresql")

            # Create Spark connector
            connector = SparkConnector(decrypted_config)
            await connector.connect()

            # Add sampling limit if requested
            if sample_only:
                compiled_sql = self._add_sample_limit(compiled_sql)

            # Execute check query
            dimension = canonical_rule.get("dimension", "completeness")
            result = await connector.execute_check_query(compiled_sql, dimension)

            # Add metadata
            result["execution_mode"] = "spark"
            result["dimension"] = dimension

            logger.info(
                f"Spark check executed - Dimension: {dimension}, "
                f"Rows scanned: {result['rows_scanned']}, "
                f"Pass rate: {result['pass_rate']:.2f}%"
            )

            return result

        except Exception as e:
            logger.error(f"Spark check execution failed: {e}", exc_info=True)
            # Return empty result on error
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "execution_mode": "spark",
                "error": str(e),
            }
        finally:
            if connector:
                await connector.disconnect()

            # Note: Session is NOT stopped here - it's managed by SparkSessionManager
            # for reuse across multiple check executions. The session will be stopped
            # only on application shutdown via the session manager.

    async def execute_check_on_dataframe(
        self,
        dataframe,
        table_name: str,
        compiled_sql: str,
        canonical_rule: dict[str, Any],
        violation_sql: str | None = None,
        sample_limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute check on a pandas DataFrame using Spark.
        Used for file sources (CSV, Excel, Parquet, JSON).

        Args:
            dataframe: Pandas DataFrame to check
            table_name: Temporary table name to use
            compiled_sql: Compiled Spark SQL query (aggregate)
            canonical_rule: Canonical rule definition
            violation_sql: Optional Spark SQL returning the per-row failing
                records. When provided, up to ``sample_limit`` rows are
                collected and returned in ``violations`` and ``sample_data``
                so the issue UI can display failing examples for file
                connectors (Sprint 4.3).
            sample_limit: Max number of failing rows to materialise.

        Returns:
            Dictionary with execution results
        """
        try:
            # Get or create Spark session
            spark = self.session_manager.get_session()

            # Convert pandas DataFrame to Spark DataFrame
            logger.info(
                f"Converting pandas DataFrame to Spark (rows: {len(dataframe)}, cols: {len(dataframe.columns)})"
            )
            logger.info("Pandas DataFrame info:")
            logger.info(f"  Columns: {list(dataframe.columns)}")
            logger.info(f"  Shape: {dataframe.shape}")
            logger.info(f"  First 2 rows:\n{dataframe.head(2)}")

            if len(dataframe) == 0:
                logger.error("❌ DataFrame is EMPTY! Cannot execute check on 0 rows")
                return {
                    "rows_scanned": 0,
                    "rows_passed": 0,
                    "rows_failed": 0,
                    "pass_rate": Decimal(0),
                    "execution_mode": "spark_dataframe",
                    "dimension": canonical_rule.get("dimension", "completeness"),
                    "error": "Input DataFrame is empty",
                }

            # Replace all pandas NaN with None BEFORE creating the Spark DataFrame.
            # pandas NaN (float) in object columns does NOT become Spark NULL automatically;
            # it stays as a non-null value, which makes IS NOT NULL return True for empty
            # cells and causes completeness checks to report 100% incorrectly.
            import pandas as pd

            dataframe = dataframe.where(pd.notnull(dataframe), other=None)

            spark_df = spark.createDataFrame(dataframe)

            # Register as temporary view
            spark_df.createOrReplaceTempView(table_name)
            logger.info(f"✅ Registered DataFrame as temporary view: {table_name}")

            # Execute check query
            dimension = canonical_rule.get("dimension", "completeness")
            logger.info(f"📝 Executing {dimension} check SQL:")
            logger.info(f"   Temp view name: {table_name}")
            logger.info(f"   SQL query: {compiled_sql}")

            result_df = spark.sql(compiled_sql)
            result_rows = result_df.collect()

            if not result_rows:
                raise ValueError("Check query returned no results")

            row = result_rows[0]

            # Convert PySpark Row to plain dict so we can safely use .get().
            # PySpark Row raises AttributeError(attr_name) in __getattr__ when the
            # attribute is missing, so .get() itself raises AttributeError("get").
            if hasattr(row, "asDict"):
                row = row.asDict()
            elif not isinstance(row, dict):
                row = dict(zip(result_df.columns, row))

            # Map dimension-specific column names produced by the SQL compiler
            # to the standardised output format expected by the caller.
            #
            # completeness SQL:  total_rows, non_null_rows, null_rows, completeness_rate
            # validity SQL:      total_rows, valid_rows,    invalid_rows, validity_rate
            # uniqueness SQL:    total_rows, unique_rows,   duplicate_rows, uniqueness_rate
            # generic/fallback:  total_rows, valid_rows,    invalid_rows, validity_rate
            total = int(row.get("total_rows", 0))

            # Try standard names first, then dimension-specific aliases
            failed = (
                int(row["rows_failed"])
                if "rows_failed" in row
                else int(
                    row.get(
                        "null_rows",  # completeness
                        row.get(
                            "invalid_rows",  # validity
                            row.get(
                                "duplicate_rows",  # uniqueness
                                0,
                            ),
                        ),
                    )
                )
            )
            passed = (
                int(row["rows_passed"])
                if "rows_passed" in row
                else int(
                    row.get(
                        "non_null_rows",  # completeness
                        row.get(
                            "valid_rows",  # validity
                            row.get(
                                "unique_rows",  # uniqueness
                                total - failed,
                            ),
                        ),
                    )
                )
            )

            # Use pre-computed rate if available, otherwise derive it
            rate_key = next(
                (
                    k
                    for k in ("pass_rate", "completeness_rate", "validity_rate", "uniqueness_rate")
                    if k in row
                ),
                None,
            )
            if rate_key:
                pass_rate = float(row[rate_key])
            else:
                pass_rate = (passed / total * 100.0) if total > 0 else 0.0

            rows_scanned = total
            rows_passed = passed
            rows_failed = failed

            result = {
                "rows_scanned": rows_scanned,
                "rows_passed": rows_passed,
                "rows_failed": rows_failed,
                "pass_rate": Decimal(str(round(pass_rate, 2))),
                "execution_mode": "spark_dataframe",
                "dimension": dimension,
            }

            # Sprint 4.3 — collect sample failing rows for file connectors so the
            # issue UI can render evidence. Only runs when:
            #   - a violation_sql was provided
            #   - the check actually has failing rows
            # Errors here are non-fatal: the aggregate result is still returned.
            if violation_sql and rows_failed > 0:
                try:
                    # Defensive LIMIT — even if compiled SQL forgot one.
                    limited_sql = violation_sql.rstrip().rstrip(";")
                    if " limit " not in limited_sql.lower():
                        limited_sql = f"{limited_sql} LIMIT {int(sample_limit)}"
                    logger.info(
                        f"📋 Collecting up to {sample_limit} failing rows via violation_sql"
                    )
                    v_df = spark.sql(limited_sql)
                    v_cols = list(v_df.columns)
                    v_rows = v_df.limit(int(sample_limit)).collect()
                    violations = []
                    for r in v_rows:
                        if hasattr(r, "asDict"):
                            d = r.asDict(recursive=True)
                        else:
                            d = dict(zip(v_cols, r))
                        # JSON-safe scalars
                        for k, v in list(d.items()):
                            if isinstance(v, Decimal):
                                d[k] = float(v)
                            elif hasattr(v, "isoformat"):
                                d[k] = v.isoformat()
                        violations.append(d)
                    result["violations"] = violations
                    result["sample_data"] = violations  # alias used by issue_detail_service
                    result["violation_count"] = len(violations)
                    logger.info(f"✅ Collected {len(violations)} failing rows for file source")
                except Exception as v_exc:  # noqa: BLE001
                    logger.warning(
                        "violation_sql collection failed for file source: %s",
                        v_exc,
                        exc_info=True,
                    )
                    result["violations"] = []
                    result["sample_data"] = []
                    result["violation_collection_error"] = str(v_exc)
            else:
                # Keep keys present so downstream code paths don't trip on .get()
                result.setdefault("violations", [])
                result.setdefault("sample_data", [])

            logger.info(
                f"Spark DataFrame check executed - Dimension: {dimension}, "
                f"Rows scanned: {rows_scanned}, Pass rate: {pass_rate:.2f}%"
            )

            return result

        except Exception as e:
            logger.error(f"Spark DataFrame check execution failed: {e}", exc_info=True)
            return {
                "rows_scanned": 0,
                "rows_passed": 0,
                "rows_failed": 0,
                "pass_rate": Decimal(0),
                "execution_mode": "spark_dataframe",
                "error": str(e),
            }
        finally:
            # Note: Session is NOT stopped here - it's managed by SparkSessionManager
            # for reuse across multiple check executions. The session will be stopped
            # only on application shutdown via the session manager.
            pass

    async def get_table_row_count(
        self, data_source_config: dict[str, Any], schema_name: str, table_name: str
    ) -> int:
        """
        Get approximate row count for a table using Spark.
        Used to determine execution mode.

        Args:
            data_source_config: Data source connection configuration (encrypted)
            schema_name: Schema name
            table_name: Table name

        Returns:
            Approximate row count
        """
        connector = None
        try:
            # Decrypt connection config before creating connector
            from app.services.datasources.connection_manager import ConnectionManager

            decrypted_config = ConnectionManager.decrypt_config(
                data_source_config.get("connection_config", {})
            )

            # Add type to config
            decrypted_config["type"] = data_source_config.get("type", "postgresql")

            connector = SparkConnector(decrypted_config)
            await connector.connect()

            # Use Spark to get row count
            count = await connector.get_row_count(table_name, schema_name)

            logger.info(f"Row count for {schema_name}.{table_name}: {count:,}")
            return count

        except Exception as e:
            logger.error(f"Failed to get row count via Spark: {e}", exc_info=True)
            # Return 0 to fall back to direct execution
            return 0
        finally:
            if connector:
                await connector.disconnect()

            # Note: Don't stop session here - row count check is followed by actual execution
            # Session will be stopped after the main check execution

    def _add_sample_limit(self, sql: str, limit: int = 10000) -> str:
        """
        Add LIMIT clause to SQL for sampling.

        Args:
            sql: Original SQL query
            limit: Number of rows to limit to

        Returns:
            Modified SQL with LIMIT clause
        """
        # Check if already has LIMIT
        if "LIMIT" in sql.upper():
            return sql

        # Add LIMIT at the end
        return f"{sql.rstrip(';')} LIMIT {limit}"

    def should_use_spark(
        self,
        row_count: int,
        user_preference: str | None = None,
        auto_threshold: int = 50000,
        force_threshold: int = 500000,
    ) -> tuple[bool, str]:
        """
        Determine if Spark should be used based on dataset size and preferences.

        Args:
            row_count: Number of rows in the dataset
            user_preference: User's execution mode preference ('spark', 'direct', or None)
            auto_threshold: Threshold to auto-enable Spark
            force_threshold: Threshold to force Spark usage

        Returns:
            Tuple of (use_spark: bool, reason: str)
        """
        # Force Spark for very large datasets
        if row_count > force_threshold:
            return (
                True,
                f"Mandatory - dataset size ({row_count:,} rows) exceeds force threshold ({force_threshold:,})",
            )

        # Auto-recommend Spark for medium datasets
        if row_count > auto_threshold:
            if user_preference == "direct":
                return (
                    False,
                    f"User override - using direct execution despite size ({row_count:,} rows)",
                )
            return (
                True,
                f"Recommended - dataset size ({row_count:,} rows) exceeds auto threshold ({auto_threshold:,})",
            )

        # Use direct execution for small datasets (unless user forces Spark)
        if user_preference == "spark":
            return True, f"User preference - Spark requested for dataset ({row_count:,} rows)"

        return (
            False,
            f"Direct execution optimal - dataset size ({row_count:,} rows) below auto threshold ({auto_threshold:,})",
        )

    def get_session_info(self) -> dict[str, Any]:
        """Get Spark session information for monitoring"""
        return self.session_manager.get_session_info()
