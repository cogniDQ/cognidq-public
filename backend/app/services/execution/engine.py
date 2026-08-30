"""
Execution Engine

Safely executes generated SQL/PySpark queries and returns results.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.schemas.rule import (
    DataSource,
    ExecutionResult,
    ExecutionStatus,
    Explanation,
    GeneratedRule,
    RuleExecution,
)
from app.services.llm.orchestrator import llm_orchestrator

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Query execution engine with safety constraints"""

    def __init__(self):
        self.engines: dict[str, sqlalchemy.Engine] = {}

    async def execute_rule(
        self, rule: GeneratedRule, datasource: DataSource, dry_run: bool = False
    ) -> RuleExecution:
        """
        Execute a data quality rule.

        Args:
            rule: Generated rule to execute
            datasource: Target datasource
            dry_run: If True, validate but don't execute

        Returns:
            RuleExecution with results and explanation
        """

        execution_id = f"exec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        logger.info(f"Executing rule {rule.rule_id} (execution_id: {execution_id})")

        start_time = datetime.utcnow()

        try:
            # Validate SQL safety
            self._validate_sql_safety(rule.sql)

            if dry_run:
                logger.info("Dry run mode - skipping actual execution")
                return self._create_dry_run_result(execution_id, rule, datasource, start_time)

            # Execute the query
            if datasource.type in ["postgresql", "mysql"]:
                violations, total_rows = await self._execute_sql(
                    sql=rule.sql, datasource=datasource
                )
            elif datasource.type in ["spark", "databricks"]:
                violations, total_rows = await self._execute_pyspark(
                    code=rule.pyspark, datasource=datasource
                )
            else:
                raise ValueError(f"Unsupported datasource type: {datasource.type}")

            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Calculate results
            violation_count = len(violations)
            total_scanned = max(total_rows, violation_count)
            pass_count = total_scanned - violation_count
            pass_rate = (pass_count / total_scanned) if total_scanned > 0 else 1.0

            execution_result = ExecutionResult(
                total_rows_scanned=total_scanned,
                total_rows_matching_criteria=total_scanned,
                violation_count=violation_count,
                pass_count=pass_count,
                pass_rate=pass_rate,
                status="PASS" if violation_count == 0 else "FAIL",
            )

            # Generate business explanation
            explanation_data = await llm_orchestrator.explain_results(
                prompt=rule.original_prompt,
                violation_count=violation_count,
                total_rows=total_scanned,
                sample_violations=violations[:3],
            )

            explanation = Explanation(**explanation_data)

            # Create execution record
            execution = RuleExecution(
                execution_id=execution_id,
                rule_id=rule.rule_id,
                status=ExecutionStatus.SUCCESS,
                executed_at=end_time,
                execution_duration_ms=duration_ms,
                datasource=datasource,
                rule=rule,
                results=execution_result,
                violations={
                    "sample": violations[:10],
                    "total_violations": violation_count,
                    "sample_size": min(10, violation_count),
                    "download_url": f"/api/v1/executions/{execution_id}/download",
                },
                explanation=explanation,
            )

            logger.info(f"Execution completed: {violation_count} violations found")

            return execution

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)

            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            return RuleExecution(
                execution_id=execution_id,
                rule_id=rule.rule_id,
                status=ExecutionStatus.FAILED,
                executed_at=end_time,
                execution_duration_ms=duration_ms,
                datasource=datasource,
                rule=rule,
                error=str(e),
            )

    async def _execute_sql(
        self, sql: str, datasource: DataSource
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Execute SQL query and return results.

        Returns:
            (violations, total_rows_in_table)
        """

        # Get or create engine for this datasource
        engine = self._get_engine(datasource)

        try:
            with engine.connect() as conn:
                # Execute the violation query
                result = conn.execute(text(sql))
                columns = result.keys()
                violations = [dict(zip(columns, row)) for row in result.fetchall()]

                # Get total row count (for context)
                table_name = (
                    f"{datasource.schema_name}.{datasource.table}"
                    if datasource.schema_name
                    else datasource.table
                )
                count_sql = f"SELECT COUNT(*) as total FROM {table_name}"
                count_result = conn.execute(text(count_sql))
                total_rows = count_result.scalar()

                return violations, total_rows

        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            raise

    async def _execute_pyspark(
        self, code: str, datasource: DataSource
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Execute PySpark code and return results.

        Note: This is a placeholder. In production, this would:
        - Connect to Databricks/Spark cluster
        - Execute code in isolated session
        - Return results
        """

        raise NotImplementedError("PySpark execution not yet implemented")

    def _get_engine(self, datasource: DataSource) -> sqlalchemy.Engine:
        """Get or create SQLAlchemy engine for datasource"""

        cache_key = datasource.connection_id

        if cache_key not in self.engines:
            # Build connection URL
            if datasource.connection_string:
                url = datasource.connection_string
            else:
                # For demo, use DATABASE_URL from settings
                url = settings.DATABASE_URL

            # Create engine with safety settings
            engine = create_engine(
                url,
                pool_size=5,
                max_overflow=10,
                pool_timeout=settings.QUERY_TIMEOUT_SECONDS,
                pool_pre_ping=True,
                connect_args={
                    "connect_timeout": settings.QUERY_TIMEOUT_SECONDS,
                    "options": f"-c statement_timeout={settings.QUERY_TIMEOUT_SECONDS * 1000}",
                }
                if datasource.type == "postgresql"
                else {},
            )

            self.engines[cache_key] = engine
            logger.info(f"Created database engine for {cache_key}")

        return self.engines[cache_key]

    def _validate_sql_safety(self, sql: str):
        """
        Validate that SQL is safe to execute.

        Checks for:
        - Only SELECT statements
        - No DDL/DML operations
        - No dangerous functions
        """

        sql_upper = sql.upper().strip()

        # Must start with SELECT (or WITH for CTEs)
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            raise ValueError("Only SELECT queries are allowed")

        # Forbidden keywords
        forbidden = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
            "EXEC",
            "EXECUTE",
        ]

        for keyword in forbidden:
            if keyword in sql_upper:
                raise ValueError(f"Forbidden keyword detected: {keyword}")

        logger.info("SQL safety validation passed")

    def _create_dry_run_result(
        self, execution_id: str, rule: GeneratedRule, datasource: DataSource, start_time: datetime
    ) -> RuleExecution:
        """Create dry run execution result"""

        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return RuleExecution(
            execution_id=execution_id,
            rule_id=rule.rule_id,
            status=ExecutionStatus.SUCCESS,
            executed_at=end_time,
            execution_duration_ms=duration_ms,
            datasource=datasource,
            rule=rule,
            results=ExecutionResult(
                total_rows_scanned=0,
                total_rows_matching_criteria=0,
                violation_count=0,
                pass_count=0,
                pass_rate=1.0,
                status="PASS",
            ),
            explanation=Explanation(
                business_summary="Dry run - query validated but not executed",
                technical_summary=f"SQL validation passed for: {rule.sql[:100]}...",
                impact_assessment="N/A",
                recommended_actions=["Execute the rule to see actual results"],
            ),
        )


# Singleton instance
execution_engine = ExecutionEngine()
