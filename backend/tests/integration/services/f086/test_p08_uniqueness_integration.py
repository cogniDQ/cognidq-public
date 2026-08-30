"""P08 — F086 Uniqueness Integration Tests.

End-to-end pipeline: UI config → _build_canonical_rule → compile_rule → _parse_uniqueness_results.
Tests verify the full pipeline works correctly for all 6 uniqueness modes,
backward compatibility, error paths, WARN threshold, and Spark code generation.
"""

import sys
import types
from unittest.mock import MagicMock

# Stub pyspark
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

from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


def pipeline(handler, compiler, ui_config, schema="public", table="customers"):
    """Config → canonical → compile → return (canonical, compiled)."""
    canonical = handler._build_canonical_rule("uniqueness", ui_config, schema, table)
    compiled = compiler.compile_rule(canonical, target_schema=schema, target_table=table)
    return canonical, compiled


def full_pipeline(handler, compiler, ui_config, mock_row, schema="public", table="customers"):
    """Full pipeline including result parsing."""
    canonical, compiled = pipeline(handler, compiler, ui_config, schema, table)
    result = handler._parse_uniqueness_results([mock_row], canonical)
    return result


# ===================================================================
# 1. End-to-end per uniqueness mode
# ===================================================================
class TestEndToEndExact:
    def test_exact_pipeline(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "exact"
        assert "GROUP BY" in compiled["compiled_postgres"]
        assert "HAVING" in compiled["compiled_postgres"]
        assert "error" not in compiled

    def test_exact_full_pass(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert result["check_status"] == "PASS"
        assert float(result["pass_rate"]) == 100.0
        assert result["uniqueness_mode"] == "exact"

    def test_exact_full_fail(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 5, "duplicate_groups": 2, "max_group_size": 3},
        )
        assert result["check_status"] == "FAIL"
        assert result["rows_failed"] == 5


class TestEndToEndComposite:
    def test_composite_pipeline(self, handler, compiler):
        config = {"columns": ["order_id", "line_item"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "composite"
        assert "order_id" in compiled["compiled_postgres"]
        assert "line_item" in compiled["compiled_postgres"]

    def test_composite_full_pipeline(self, handler, compiler):
        config = {"columns": ["order_id", "line_item"], "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 200, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert result["check_status"] == "PASS"
        assert result["uniqueness_mode"] == "composite"


class TestEndToEndScoped:
    def test_scoped_pipeline(self, handler, compiler):
        config = {"columns": ["email"], "scopeColumns": ["department"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "scoped"
        assert canonical["parameters"]["scope_columns"] == ["department"]
        assert "GROUP BY" in compiled["compiled_postgres"]
        assert "department" in compiled["compiled_postgres"]

    def test_scoped_full_pipeline(self, handler, compiler):
        config = {"columns": ["email"], "scopeColumns": ["region"], "pass_threshold": 95}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "duplicate_rows": 2, "duplicate_groups": 1, "max_group_size": 2},
        )
        assert result["check_status"] == "PASS"
        assert result["uniqueness_mode"] == "scoped"


class TestEndToEndCrossDataset:
    def test_cross_dataset_pipeline(self, handler, compiler):
        config = {
            "columns": ["id"],
            "crossDatasetName": "legacy_customers",
            "crossDatasetColumn": "customer_id",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "cross_dataset"
        assert "JOIN" in compiled["compiled_postgres"]
        assert "legacy_customers" in compiled["compiled_postgres"]

    def test_cross_dataset_full_pipeline(self, handler, compiler):
        config = {
            "columns": ["id"],
            "crossDatasetName": "legacy",
            "crossDatasetColumn": "cust_id",
            "pass_threshold": 100,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 3, "duplicate_groups": 3, "max_group_size": 1},
        )
        assert result["check_status"] == "FAIL"
        assert result["duplicate_groups"] == 3


class TestEndToEndFuzzy:
    def test_fuzzy_pipeline(self, handler, compiler):
        config = {
            "columns": ["name"],
            "fuzzyAlgorithm": "levenshtein",
            "fuzzyThreshold": 0.85,
            "pass_threshold": 90,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "fuzzy"
        assert canonical["parameters"]["fuzzy_algorithm"] == "levenshtein"
        assert (
            "levenshtein" in compiled["compiled_postgres"].lower()
            or "similarity" in compiled["compiled_postgres"].lower()
        )

    def test_fuzzy_full_pipeline(self, handler, compiler):
        config = {"columns": ["name"], "fuzzyAlgorithm": "soundex", "pass_threshold": 80}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 15, "duplicate_groups": 7, "max_group_size": 4},
        )
        assert result["check_status"] == "PASS"
        assert result["uniqueness_mode"] == "fuzzy"


class TestEndToEndTemporal:
    def test_temporal_pipeline(self, handler, compiler):
        config = {
            "columns": ["email"],
            "temporalColumn": "created_at",
            "temporalWindow": "1d",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "temporal"
        assert "EPOCH" in compiled["compiled_postgres"] or "epoch" in compiled["compiled_postgres"]

    def test_temporal_full_pipeline(self, handler, compiler):
        config = {
            "columns": ["email"],
            "temporalColumn": "created_at",
            "temporalWindow": "2h",
            "pass_threshold": 95,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "duplicate_rows": 2, "duplicate_groups": 1, "max_group_size": 2},
        )
        assert result["check_status"] == "PASS"
        assert result["uniqueness_mode"] == "temporal"


# ===================================================================
# 2. Backward compatibility
# ===================================================================
class TestBackwardCompat:
    def test_old_config_single_column(self, handler, compiler):
        """Old-style config without uniquenessMode → exact mode."""
        config = {"columns": ["email"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "exact"
        assert "error" not in compiled

    def test_old_config_multi_column(self, handler, compiler):
        """Old-style config with multiple columns → composite mode."""
        config = {"columns": ["first_name", "last_name"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["uniqueness_mode"] == "composite"


# ===================================================================
# 3. Error paths
# ===================================================================
class TestErrorPaths:
    def test_scoped_missing_scope_columns(self, handler, compiler):
        config = {"columns": ["email"], "uniquenessMode": "scoped", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_cross_dataset_missing_name(self, handler, compiler):
        config = {"columns": ["id"], "uniquenessMode": "cross_dataset", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_temporal_missing_window(self, handler, compiler):
        config = {
            "columns": ["email"],
            "uniquenessMode": "temporal",
            "temporalColumn": "created_at",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_temporal_invalid_window_format(self, handler, compiler):
        config = {
            "columns": ["email"],
            "uniquenessMode": "temporal",
            "temporalColumn": "created_at",
            "temporalWindow": "invalid",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled

    def test_unknown_mode_error(self, handler, compiler):
        config = {"columns": ["email"], "uniquenessMode": "unknown_mode", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert "error" in compiled


# ===================================================================
# 4. Spark code generation
# ===================================================================
class TestSparkGeneration:
    def test_exact_spark(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled
        assert "partitionBy" in compiled["compiled_spark"] or "Window" in compiled["compiled_spark"]

    def test_composite_spark(self, handler, compiler):
        config = {"columns": ["a", "b"], "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled

    def test_scoped_spark(self, handler, compiler):
        config = {"columns": ["email"], "scopeColumns": ["dept"], "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled

    def test_fuzzy_spark(self, handler, compiler):
        config = {"columns": ["name"], "fuzzyAlgorithm": "levenshtein", "pass_threshold": 90}
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled

    def test_temporal_spark(self, handler, compiler):
        config = {
            "columns": ["email"],
            "temporalColumn": "created_at",
            "temporalWindow": "1d",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "compiled_spark" in compiled


# ===================================================================
# 5. WARN threshold behaviour
# ===================================================================
class TestWarnThreshold:
    def test_pass_above_pass_threshold(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 95, "thresholdWarn": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 3, "duplicate_groups": 1, "max_group_size": 3},
        )
        assert result["check_status"] == "PASS"

    def test_warn_between_thresholds(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 98, "thresholdWarn": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 5, "duplicate_groups": 2, "max_group_size": 3},
        )
        assert result["check_status"] == "WARN"

    def test_fail_below_warn_threshold(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 98, "thresholdWarn": 90}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 15, "duplicate_groups": 5, "max_group_size": 4},
        )
        assert result["check_status"] == "FAIL"


# ===================================================================
# 6. Filter expression
# ===================================================================
class TestFilterExpression:
    def test_filter_in_compiled_sql(self, handler, compiler):
        config = {
            "columns": ["email"],
            "filterExpression": "status = 'active'",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "status" in compiled["compiled_postgres"]
        assert "active" in compiled["compiled_postgres"]

    def test_filter_with_scoped(self, handler, compiler):
        config = {
            "columns": ["email"],
            "scopeColumns": ["dept"],
            "filterExpression": "active = true",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "active" in compiled["compiled_postgres"]


# ===================================================================
# 7. Null handling
# ===================================================================
class TestNullHandling:
    def test_exclude_nulls_default(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        sql = compiled["compiled_postgres"]
        assert "IS NOT NULL" in sql

    def test_include_nulls(self, handler, compiler):
        config = {"columns": ["email"], "nullHandling": "include", "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        sql = compiled["compiled_postgres"]
        assert "COALESCE" in sql or "IS NOT NULL" not in sql


# ===================================================================
# 8. Case sensitivity
# ===================================================================
class TestCaseSensitivity:
    def test_case_insensitive_uses_lower(self, handler, compiler):
        config = {"columns": ["name"], "caseSensitive": False, "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "LOWER" in compiled["compiled_postgres"]

    def test_case_sensitive_no_lower(self, handler, compiler):
        config = {"columns": ["name"], "caseSensitive": True, "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert "LOWER" not in compiled["compiled_postgres"]


# ===================================================================
# 9. Result structure completeness
# ===================================================================
class TestResultStructure:
    def test_all_required_fields(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 50, "duplicate_rows": 2, "duplicate_groups": 1, "max_group_size": 2},
        )
        required = [
            "check_status",
            "pass_rate",
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "uniqueness_mode",
            "duplicate_groups",
            "max_group_size",
            "avg_group_size",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_pass_rate_is_decimal(self, handler, compiler):
        config = {"columns": ["email"], "pass_threshold": 100}
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 100, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert isinstance(result["pass_rate"], Decimal)
