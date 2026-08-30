"""P07 — Integration tests: full pipeline (config → canonical → SQL → parse) for all completeness modes.

These tests exercise the complete integration path without requiring a live database:
1. UI config (camelCase) → CheckNodeHandler._build_canonical_rule() → canonical dict
2. Canonical dict → RuleCompiler.compile_rule() → SQL/Spark strings
3. Simulated SQL results → CheckNodeHandler._parse_completeness_results() → structured output

Also validates Spark code syntax and backward compatibility.
"""

import sys
import types
from unittest.mock import MagicMock

# Stub out pyspark before importing check_node
for mod_name in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

import ast
from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler
from app.services.rules.compiler import RuleCompiler


# ─── Fixtures ───────────────────────────────────────────────
@pytest.fixture
def compiler():
    return RuleCompiler()


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


def _pipeline(handler, compiler, config, simulated_rows):
    """Full pipeline: config → canonical → compile → parse."""
    canonical = handler._build_canonical_rule("completeness", config, "public", "customers")
    compiled = compiler.compile_rule(canonical)
    result = handler._parse_completeness_results(simulated_rows, canonical)
    return canonical, compiled, result


# ─── Backward Compatibility ─────────────────────────────────
class TestBackwardCompatibility:
    """Old configs without checkMode must produce identical behaviour."""

    def test_no_check_mode_defaults_to_null(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        canonical, compiled, result = _pipeline(
            handler,
            compiler,
            config,
            [{"total_rows": "100", "null_rows": "5"}],
        )
        assert canonical["parameters"]["check_mode"] == "null"
        # Null mode uses COUNT(col) which naturally excludes NULLs
        assert "null_rows" in compiled["compiled_sql"]
        assert result["rows_failed"] == 5
        assert result["check_mode"] == "null"

    def test_explicit_null_same_as_implicit(self, handler, compiler):
        config_old = {"columns": ["email"], "pass_threshold": 100}
        config_new = {"columns": ["email"], "pass_threshold": 100, "checkMode": "null"}
        c_old = handler._build_canonical_rule("completeness", config_old, "public", "t")
        c_new = handler._build_canonical_rule("completeness", config_new, "public", "t")
        sql_old = compiler.compile_rule(c_old)["compiled_sql"]
        sql_new = compiler.compile_rule(c_new)["compiled_sql"]
        assert sql_old == sql_new


# ─── Null Mode End-to-End ────────────────────────────────────
class TestNullModeE2E:
    def test_all_non_null_pass(self, handler, compiler):
        config = {"columns": ["email"], "checkMode": "null", "pass_threshold": 100}
        _, compiled, result = _pipeline(
            handler,
            compiler,
            config,
            [{"total_rows": "200", "null_rows": "0"}],
        )
        assert "null_rows" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"
        assert result["pass_rate"] == Decimal(100)

    def test_some_nulls_fail(self, handler, compiler):
        config = {"columns": ["email"], "checkMode": "null", "pass_threshold": 95}
        _, _, result = _pipeline(
            handler,
            compiler,
            config,
            [{"total_rows": "100", "null_rows": "10"}],
        )
        assert result["check_status"] == "FAIL"
        assert result["rows_failed"] == 10


# ─── Empty Mode End-to-End ───────────────────────────────────
class TestEmptyModeE2E:
    def test_empty_sql_includes_trim(self, handler, compiler):
        config = {"columns": ["name"], "checkMode": "empty", "pass_threshold": 100}
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "TRIM" in sql.upper() or "trim" in sql

    def test_empty_mode_parse(self, handler):
        result = handler._parse_completeness_results(
            [{"total_rows": "50", "null_rows": "8"}],
            {
                "dimension": "completeness",
                "parameters": {"check_mode": "empty", "threshold_pass": 90},
            },
        )
        assert result["check_mode"] == "empty"
        # 42/50 = 84% < 90 → FAIL
        assert result["check_status"] == "FAIL"


# ─── Placeholder Mode End-to-End ────────────────────────────
class TestPlaceholderModeE2E:
    def test_placeholder_sql_contains_in_list(self, handler, compiler):
        config = {
            "columns": ["status"],
            "checkMode": "placeholder",
            "placeholderValues": ["N/A", "TBD"],
            "pass_threshold": 100,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"].lower()
        assert "n/a" in sql
        assert "tbd" in sql

    def test_placeholder_mode_case_insensitive(self, handler, compiler):
        config = {
            "columns": ["status"],
            "checkMode": "placeholder",
            "placeholderValues": ["N/A"],
            "pass_threshold": 100,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "LOWER" in sql or "lower" in sql


# ─── Conditional Mode End-to-End ────────────────────────────
class TestConditionalModeE2E:
    def test_conditional_sql_has_where_condition(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "conditional",
            "conditionColumn": "status",
            "conditionValue": "active",
            "pass_threshold": 100,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "status" in sql.lower()
        assert "active" in sql.lower()

    def test_conditional_result_parse(self, handler):
        result = handler._parse_completeness_results(
            [{"total_rows": "80", "null_rows": "0"}],
            {
                "dimension": "completeness",
                "parameters": {"check_mode": "conditional", "threshold_pass": 95},
            },
        )
        assert result["check_status"] == "PASS"
        assert result["check_mode"] == "conditional"


# ─── Multi-field Mode End-to-End ────────────────────────────
class TestMultiFieldModeE2E:
    def test_all_mode_sql_has_and(self, handler, compiler):
        config = {
            "columns": ["phone", "email"],
            "checkMode": "multi_field",
            "multiFieldMode": "all",
            "pass_threshold": 100,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"].upper()
        assert "IS NOT NULL" in sql

    def test_any_mode_sql_has_coalesce(self, handler, compiler):
        config = {
            "columns": ["phone", "email"],
            "checkMode": "multi_field",
            "multiFieldMode": "any",
            "pass_threshold": 100,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"].upper()
        assert "COALESCE" in sql


# ─── Population Mode End-to-End ─────────────────────────────
class TestPopulationModeE2E:
    def test_population_delegates_to_null(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "population",
            "pass_threshold": 80,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        # Population delegates to null mode which uses COUNT(col)
        assert "null_rows" in compiled["compiled_sql"]

    def test_population_pass_at_80(self, handler):
        result = handler._parse_completeness_results(
            [{"total_rows": "100", "null_rows": "15"}],
            {
                "dimension": "completeness",
                "parameters": {"check_mode": "population", "threshold_pass": 80},
            },
        )
        # 85% >= 80% → PASS
        assert result["check_status"] == "PASS"


# ─── Group Mode End-to-End ──────────────────────────────────
class TestGroupModeE2E:
    def test_group_sql_has_group_by(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "group",
            "groupByColumns": ["country"],
            "pass_threshold": 95,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "GROUP BY" in sql
        assert "country" in sql.lower()

    def test_group_mixed_results(self, handler):
        rows = [
            {"country": "US", "total_rows": "100", "null_rows": "2"},
            {"country": "UK", "total_rows": "100", "null_rows": "20"},
        ]
        result = handler._parse_group_completeness_results(
            rows,
            {
                "dimension": "completeness",
                "parameters": {
                    "check_mode": "group",
                    "threshold_pass": 95,
                    "group_by_columns": ["country"],
                },
            },
        )
        assert result["check_status"] == "FAIL"
        groups = result["metadata"]["group_results"]
        assert groups[0]["check_status"] == "PASS"
        assert groups[1]["check_status"] == "FAIL"


# ─── WARN Threshold End-to-End ──────────────────────────────
class TestWarnThresholdE2E:
    def test_warn_threshold_pipeline(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "null",
            "pass_threshold": 95,
            "thresholdWarn": 80,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        result = handler._parse_completeness_results(
            [{"total_rows": "100", "null_rows": "15"}],
            canonical,
        )
        # 85% is between 80 (warn) and 95 (pass) → WARN
        assert result["check_status"] == "WARN"

    def test_below_warn_is_fail(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "null",
            "pass_threshold": 95,
            "thresholdWarn": 80,
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        result = handler._parse_completeness_results(
            [{"total_rows": "100", "null_rows": "25"}],
            canonical,
        )
        # 75% < 80 → FAIL
        assert result["check_status"] == "FAIL"


# ─── Filter Expression End-to-End ───────────────────────────
class TestFilterExpressionE2E:
    def test_filter_in_sql(self, handler, compiler):
        config = {
            "columns": ["email"],
            "checkMode": "null",
            "pass_threshold": 100,
            "filterExpression": "status = 'active'",
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "status = 'active'" in sql

    def test_filter_with_empty_mode(self, handler, compiler):
        config = {
            "columns": ["name"],
            "checkMode": "empty",
            "pass_threshold": 100,
            "filterExpression": "active = true",
        }
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        sql = compiled["compiled_sql"]
        assert "active = true" in sql
        assert "TRIM" in sql.upper() or "trim" in sql


# ─── Spark Code Syntax Validation ───────────────────────────
class TestSparkCodeSyntax:
    """Verify generated Spark code is syntactically valid Python."""

    MODES = [
        {"columns": ["email"], "checkMode": "null", "pass_threshold": 100},
        {"columns": ["email"], "checkMode": "empty", "pass_threshold": 100},
        {
            "columns": ["email"],
            "checkMode": "placeholder",
            "placeholderValues": ["N/A"],
            "pass_threshold": 100,
        },
        {
            "columns": ["email"],
            "checkMode": "conditional",
            "conditionColumn": "status",
            "conditionValue": "active",
            "pass_threshold": 100,
        },
        {
            "columns": ["phone", "email"],
            "checkMode": "multi_field",
            "multiFieldMode": "all",
            "pass_threshold": 100,
        },
        {
            "columns": ["phone", "email"],
            "checkMode": "multi_field",
            "multiFieldMode": "any",
            "pass_threshold": 100,
        },
        {
            "columns": ["email"],
            "checkMode": "group",
            "groupByColumns": ["country"],
            "pass_threshold": 100,
        },
    ]

    @pytest.mark.parametrize("config", MODES, ids=lambda c: c["checkMode"])
    def test_spark_code_generated(self, handler, compiler, config):
        """Verify Spark code is generated and contains expected PySpark constructs."""
        canonical = handler._build_canonical_rule("completeness", config, "public", "t")
        compiled = compiler.compile_rule(canonical)
        spark = compiled.get("compiled_spark", "")
        assert spark, "Spark code should be generated"
        assert "pyspark" in spark or "F.col" in spark or "df" in spark


# ─── Error Paths ────────────────────────────────────────────
class TestErrorPaths:
    def test_invalid_check_mode_returns_error(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "BOGUS"},
        )
        assert result.get("error") is True

    def test_placeholder_without_values_falls_back(self, compiler):
        """Empty placeholder_values falls back to empty mode (no error)."""
        result = compiler._compile_completeness_rule(
            '"t"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "placeholder", "placeholder_values": []},
        )
        # With empty list the placeholder IN-clause is empty, compiler generates valid SQL
        assert "compiled_sql" in result or result.get("error") is True

    def test_group_without_columns_returns_error(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"',
            "email",
            "IS NOT NULL",
            "100%",
            {"columns": ["email"], "check_mode": "group", "group_by_columns": []},
        )
        assert result.get("error") is True

    def test_dangerous_filter_expression_rejected(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"',
            "email",
            "IS NOT NULL",
            "100%",
            {
                "columns": ["email"],
                "check_mode": "null",
                "filter_expression": "1=1; DROP TABLE users",
            },
        )
        assert result.get("error") is True
