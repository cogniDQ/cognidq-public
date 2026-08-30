"""
F076-P01  Rule Compilation + Check Execution Integration
15 tests · RuleCompiler real execution + CheckNodeHandler with mocked connector/db
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.schemas.flow import NodeStatus
from app.services.flows.node_handlers.base import (
    NodeExecutionContext,
    NodeExecutionResult,
)
from app.services.rules.compiler import RuleCompiler

CHECK_MOD = "app.services.flows.node_handlers.check_node"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
compiler = RuleCompiler()


def _context(
    check_type="completeness",
    node_config=None,
    input_data=None,
    rule_id=None,
    execution_config=None,
):
    cfg = node_config or {"checkType": check_type, "columns": ["email"], "threshold": 90}
    if rule_id:
        cfg["rule_id"] = rule_id
    inp = input_data or {
        "data_source": {"type": "postgresql", "host": "localhost"},
        "schema_name": "public",
        "table_name": "customers",
        "columns": [{"name": "email"}, {"name": "name"}],
    }
    return NodeExecutionContext(
        db=MagicMock(),
        workspace_id=uuid4(),
        flow_id=uuid4(),
        execution_id=uuid4(),
        node_id="check-1",
        node_config=cfg,
        execution_config=execution_config or {},
        input_data=inp,
        check_type=check_type,
    )


# ===========================================================================
# TestRuleCompilerIntegration — real RuleCompiler, no mocks
# ===========================================================================
class TestRuleCompilerIntegration:
    def test_compile_completeness_produces_sql(self):
        rule = {
            "dimension": "completeness",
            "entity": "customers.email",
            "condition": "IS NOT NULL",
            "expectation": "100%",
            "parameters": {"columns": ["email"]},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="customers")
        assert "compiled_sql" in result or "compiled_postgres" in result
        sql = result.get("compiled_postgres", result.get("compiled_sql", ""))
        assert "COUNT" in sql.upper()
        assert "NULL" in sql.upper()

    def test_compile_validity_produces_sql(self):
        rule = {
            "dimension": "validity",
            "entity": "customers.email",
            "condition": "^[a-zA-Z0-9._%+-]+@",
            "expectation": "95%",
            "parameters": {"regex_pattern": "^[a-zA-Z0-9._%+-]+@"},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="customers")
        sql = result.get("compiled_postgres", result.get("compiled_sql", ""))
        assert "COUNT" in sql.upper()

    def test_compile_uniqueness_produces_sql(self):
        rule = {
            "dimension": "uniqueness",
            "entity": "customers.email",
            "condition": "IS UNIQUE",
            "expectation": "100%",
            "parameters": {},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="customers")
        sql = result.get("compiled_postgres", result.get("compiled_sql", ""))
        assert "COUNT" in sql.upper()

    def test_compile_conformity_produces_sql(self):
        rule = {
            "dimension": "conformity",
            "entity": "customers.phone",
            "condition": "MATCHES FORMAT",
            "expectation": "90%",
            "parameters": {"format_pattern": r"^\+\d{1,3}-\d{3}-\d{4}$"},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="customers")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_compile_consistency_produces_sql(self):
        rule = {
            "dimension": "consistency",
            "entity": "orders.total",
            "condition": "EQUALS",
            "expectation": "100%",
            "parameters": {"reference_column": "subtotal", "reference_table": "orders"},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="orders")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_compile_statistical_produces_sql(self):
        rule = {
            "dimension": "statistical",
            "entity": "orders.amount",
            "condition": "WITHIN RANGE",
            "expectation": "95%",
            "parameters": {"min_value": 0, "max_value": 10000},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="orders")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_compiler_spark_no_schema_prefix(self):
        rule = {
            "dimension": "completeness",
            "entity": "customers.email",
            "condition": "IS NOT NULL",
            "expectation": "100%",
            "parameters": {"columns": ["email"]},
        }
        spark_sql = compiler.compile_rule_for_spark(
            rule, target_schema="public", target_table="customers"
        )
        assert isinstance(spark_sql, str)
        # Spark SQL should not have quoted "schema"."table" format
        assert '"public"."customers"' not in spark_sql

    def test_compile_with_custom_parameters(self):
        rule = {
            "dimension": "validity",
            "entity": "products.price",
            "condition": "WITHIN RANGE",
            "expectation": "100%",
            "parameters": {"min_value": 0, "max_value": 9999},
        }
        result = compiler.compile_rule(rule, target_schema="public", target_table="products")
        sql = result.get("compiled_postgres", result.get("compiled_sql", ""))
        # Parameters should be embedded in the SQL
        assert "0" in sql or "9999" in sql


# ===========================================================================
# TestCheckExecution — CheckNodeHandler with mocked external deps
# ===========================================================================
class TestCheckExecution:
    @pytest.mark.asyncio
    async def test_check_handler_passing_check(self):
        """Passing check: pass_rate >= threshold → COMPLETED"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        ctx = _context(check_type="completeness")

        exec_result = {
            "rows_scanned": 100,
            "rows_passed": 95,
            "rows_failed": 5,
            "pass_rate": Decimal("95"),
            "violations": [],
        }
        with (
            patch.object(
                handler, "_determine_execution_mode", new_callable=AsyncMock, return_value="direct"
            ),
            patch.object(
                handler, "_execute_adhoc_check", new_callable=AsyncMock, return_value=exec_result
            ),
        ):
            result = await handler.execute(ctx)

        assert result.status == NodeStatus.COMPLETED
        assert result.result_data["pass_rate"] == Decimal("95")

    @pytest.mark.asyncio
    async def test_check_handler_failing_check(self):
        """Failing check: pass_rate < threshold → FAILED with violations"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        ctx = _context(check_type="completeness")

        exec_result = {
            "rows_scanned": 100,
            "rows_passed": 50,
            "rows_failed": 50,
            "pass_rate": Decimal("50"),
            "violations": [{"email": None, "id": 1}],
        }
        with (
            patch.object(
                handler, "_determine_execution_mode", new_callable=AsyncMock, return_value="direct"
            ),
            patch.object(
                handler, "_execute_adhoc_check", new_callable=AsyncMock, return_value=exec_result
            ),
        ):
            result = await handler.execute(ctx)

        assert result.status == NodeStatus.FAILED
        assert len(result.result_data["violations"]) > 0

    @pytest.mark.asyncio
    async def test_check_handler_adhoc_no_rule_id(self):
        """No rule_id → builds canonical rule from config, uses compile+execute path"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        ctx = _context(check_type="completeness")

        exec_result = {
            "rows_scanned": 10,
            "rows_passed": 10,
            "rows_failed": 0,
            "pass_rate": Decimal("100"),
            "violations": [],
        }
        with (
            patch.object(
                handler, "_determine_execution_mode", new_callable=AsyncMock, return_value="direct"
            ),
            patch.object(
                handler, "_execute_adhoc_check", new_callable=AsyncMock, return_value=exec_result
            ) as mock_adhoc,
        ):
            result = await handler.execute(ctx)

        # Adhoc path was used (not rule_executor)
        mock_adhoc.assert_called_once()
        assert result.status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_check_handler_with_rule_id(self):
        """rule_id present → loads DQRule from db, uses RuleExecutor"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        rule_id = uuid4()
        ctx = _context(check_type="completeness", rule_id=str(rule_id))

        mock_rule = MagicMock()
        mock_rule.name = "email_check"
        ctx.db.query.return_value.filter.return_value.first.return_value = mock_rule

        exec_result = {
            "rows_scanned": 100,
            "rows_passed": 100,
            "rows_failed": 0,
            "pass_rate": Decimal("100"),
            "violations": [],
        }
        with patch.object(
            handler.rule_executor, "execute_rule", new_callable=AsyncMock, return_value=exec_result
        ):
            result = await handler.execute(ctx)

        assert result.status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_check_handler_spark_path(self):
        """File source → Spark execution path: compile_rule_for_spark + execute_check_on_dataframe"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        inp = {
            "data_source": {"type": "file", "file_path": "/tmp/data.csv", "name": "data.csv"},
            "schema_name": "default",
            "table_name": "data",
            "is_file_source": True,
            "columns": [{"name": "age"}],
        }
        ctx = _context(check_type="completeness", input_data=inp)

        import pandas as pd

        mock_df = pd.DataFrame({"age": [25, 30, None]})

        exec_result = {
            "rows_scanned": 3,
            "rows_passed": 2,
            "rows_failed": 1,
            "pass_rate": Decimal("66.67"),
            "violations": [{"age": None}],
        }
        with patch("app.services.ingestion.file_upload.FileUploadService") as MockFile:
            MockFile.return_value.parse_file.return_value = MagicMock(data=mock_df)
            with patch.object(
                handler.spark_executor,
                "execute_check_on_dataframe",
                new_callable=AsyncMock,
                return_value=exec_result,
            ):
                result = await handler.execute(ctx)

        assert result.status == NodeStatus.FAILED  # 66.67 < 90 threshold

    @pytest.mark.asyncio
    async def test_check_handler_error_returns_failed(self):
        """Exception in handler → FAILED status with error_message"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        ctx = _context(check_type="completeness")

        with patch.object(
            handler,
            "_determine_execution_mode",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ):
            result = await handler.execute(ctx)

        assert result.status == NodeStatus.FAILED
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_check_handler_result_structure(self):
        """Verify result_data contains all expected keys"""
        from app.services.flows.node_handlers.check_node import CheckNodeHandler

        handler = CheckNodeHandler()
        ctx = _context(check_type="completeness")

        exec_result = {
            "rows_scanned": 100,
            "rows_passed": 90,
            "rows_failed": 10,
            "pass_rate": Decimal("90"),
            "violations": [{"email": None}],
        }
        with (
            patch.object(
                handler, "_determine_execution_mode", new_callable=AsyncMock, return_value="direct"
            ),
            patch.object(
                handler, "_execute_adhoc_check", new_callable=AsyncMock, return_value=exec_result
            ),
        ):
            result = await handler.execute(ctx)

        rd = result.result_data
        assert "rows_scanned" in rd
        assert "rows_passed" in rd
        assert "rows_failed" in rd
        assert "pass_rate" in rd
        assert "violations" in rd
        assert "check_type" in rd
        assert "dataset" in rd
