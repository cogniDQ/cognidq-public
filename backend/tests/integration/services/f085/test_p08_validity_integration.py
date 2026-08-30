"""P08 — F085 Validity Integration Tests.

End-to-end pipeline: UI config → _build_canonical_rule → compile_rule → _parse_validity_results.
Tests verify the full pipeline works correctly for all 8 validation types,
backward compatibility, error paths, and WARN threshold behaviour.
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


def pipeline(handler, compiler, ui_config, schema="public", table="orders"):
    """Run the full validity pipeline: config → canonical → compile → return (canonical, compiled)."""
    canonical = handler._build_canonical_rule("validity", ui_config, schema, table)
    compiled = compiler.compile_rule(canonical, target_schema=schema, target_table=table)
    return canonical, compiled


def full_pipeline(handler, compiler, ui_config, mock_row, schema="public", table="orders"):
    """Run full pipeline including result parsing."""
    canonical, compiled = pipeline(handler, compiler, ui_config, schema, table)
    result = handler._parse_validity_results([mock_row], canonical)
    return result


# ===================================================================
# 1. End-to-end per validation type
# ===================================================================
class TestEndToEndRegex:
    def test_regex_pipeline(self, handler, compiler):
        config = {"columns": ["email"], "pattern": "^[A-Z]+$", "pass_threshold": 95}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "regex"
        assert "~" in compiled["compiled_postgres"]
        assert "error" not in compiled

    def test_regex_with_null_skip(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^\\d+$",
            "nullHandling": "skip",
            "pass_threshold": 90,
        }
        result = full_pipeline(
            handler,
            compiler,
            config,
            {"total_rows": 80, "valid_rows": 80, "invalid_rows": 0, "skipped_rows": 20},
        )
        assert result["check_status"] == "PASS"
        assert result["skipped_rows"] == 20
        assert result["rows_scanned"] == 100


class TestEndToEndRange:
    def test_range_pipeline(self, handler, compiler):
        config = {"columns": ["age"], "min_value": 0, "max_value": 120, "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "range"
        assert ">= 0" in compiled["compiled_sql"]
        assert "<= 120" in compiled["compiled_sql"]

    def test_range_min_only(self, handler, compiler):
        config = {"columns": ["salary"], "min_value": 0, "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert ">= 0" in compiled["compiled_sql"]
        assert "<=" not in compiled["compiled_sql"]


class TestEndToEndAllowedValues:
    def test_allowed_values_pipeline(self, handler, compiler):
        config = {"columns": ["status"], "allowedValues": ["A", "B", "C"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "allowed_values"
        assert "IN (" in compiled["compiled_sql"]

    def test_case_insensitive(self, handler, compiler):
        config = {
            "columns": ["status"],
            "validationType": "allowed_values",
            "allowedValues": ["Active", "Inactive"],
            "caseSensitive": False,
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "LOWER" in compiled["compiled_sql"]


class TestEndToEndReferenceLookup:
    def test_reference_lookup_pipeline(self, handler, compiler):
        config = {
            "columns": ["country_code"],
            "validationType": "reference_lookup",
            "referenceDataset": "ref.countries",
            "referenceColumn": "code",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "reference_lookup"
        assert "LEFT JOIN" in compiled["compiled_sql"]


class TestEndToEndBusinessRule:
    def test_business_rule_pipeline(self, handler, compiler):
        config = {
            "columns": ["amount"],
            "validationType": "business_rule",
            "businessRuleExpression": "amount > 0 AND amount < 10000",
            "pass_threshold": 95,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "business_rule"
        assert "amount > 0" in compiled["compiled_sql"]


class TestEndToEndCrossField:
    def test_cross_field_pipeline(self, handler, compiler):
        config = {
            "columns": ["start_date"],
            "validationType": "cross_field",
            "comparisonColumn": "end_date",
            "comparisonOperator": "<=",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "cross_field"
        assert '"start_date" <=' in compiled["compiled_sql"]


class TestEndToEndDateLogic:
    def test_date_logic_pipeline(self, handler, compiler):
        config = {
            "columns": ["created_at"],
            "validationType": "date_logic",
            "comparisonColumn": "updated_at",
            "comparisonOperator": "<=",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert "CAST" in compiled["compiled_sql"]
        assert "DATE" in compiled["compiled_sql"]


class TestEndToEndNegative:
    def test_negative_pipeline(self, handler, compiler):
        config = {
            "columns": ["status"],
            "validationType": "negative",
            "negativeExpression": "status = 'DELETED'",
            "pass_threshold": 100,
        }
        canonical, compiled = pipeline(handler, compiler, config)
        assert canonical["parameters"]["validation_type"] == "negative"
        assert "NOT (status = 'DELETED')" in compiled["compiled_sql"]


# ===================================================================
# 2. Backward compatibility
# ===================================================================
class TestBackwardCompatibility:
    def test_old_regex_config(self, handler, compiler):
        """Config with only 'pattern' (no validationType) still works."""
        config = {"columns": ["email"], "pattern": "^[A-Z]+$", "pass_threshold": 95}
        canonical, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is not True
        assert "~" in compiled["compiled_postgres"]

    def test_old_range_config(self, handler, compiler):
        config = {"columns": ["age"], "min_value": 0, "max_value": 100, "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is not True
        assert ">= 0" in compiled["compiled_sql"]

    def test_old_allowed_values_config(self, handler, compiler):
        config = {"columns": ["status"], "allowed_values": ["A", "B"], "pass_threshold": 100}
        canonical, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is not True
        assert "IN (" in compiled["compiled_sql"]

    def test_legacy_nested_rule_pattern(self, handler, compiler):
        config = {"columns": ["email"], "rule": {"pattern": "^[A-Z]+$"}, "pass_threshold": 95}
        canonical, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is not True


# ===================================================================
# 3. Error paths
# ===================================================================
class TestErrorPaths:
    def test_unknown_validation_type(self, handler, compiler):
        config = {"columns": ["x"], "validationType": "bogus", "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True
        assert "bogus" in compiled["error_message"]

    def test_reference_lookup_missing_dataset(self, handler, compiler):
        config = {
            "columns": ["code"],
            "validationType": "reference_lookup",
            "referenceColumn": "code",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_business_rule_injection(self, handler, compiler):
        config = {
            "columns": ["x"],
            "validationType": "business_rule",
            "businessRuleExpression": "1=1; DROP TABLE users",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_negative_missing_expression(self, handler, compiler):
        config = {"columns": ["x"], "validationType": "negative", "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_cross_field_missing_column(self, handler, compiler):
        config = {
            "columns": ["a"],
            "validationType": "cross_field",
            "comparisonOperator": "=",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_range_no_bounds(self, handler, compiler):
        config = {"columns": ["x"], "validationType": "range", "pass_threshold": 100}
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_allowed_values_empty_list(self, handler, compiler):
        config = {
            "columns": ["x"],
            "validationType": "allowed_values",
            "allowedValues": [],
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True

    def test_filter_expression_injection(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^[A-Z]+$",
            "filterExpression": "DELETE FROM users",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("error") is True


# ===================================================================
# 4. WARN threshold
# ===================================================================
class TestWarnThreshold:
    def test_pass_above_warn(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^[A-Z]+$",
            "pass_threshold": 95,
            "thresholdWarn": 80,
        }
        result = full_pipeline(
            handler, compiler, config, {"total_rows": 100, "valid_rows": 100, "invalid_rows": 0}
        )
        assert result["check_status"] == "PASS"

    def test_warn_between_thresholds(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^[A-Z]+$",
            "pass_threshold": 95,
            "thresholdWarn": 80,
        }
        result = full_pipeline(
            handler, compiler, config, {"total_rows": 100, "valid_rows": 85, "invalid_rows": 15}
        )
        assert result["check_status"] == "WARN"

    def test_fail_below_warn(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^[A-Z]+$",
            "pass_threshold": 95,
            "thresholdWarn": 80,
        }
        result = full_pipeline(
            handler, compiler, config, {"total_rows": 100, "valid_rows": 70, "invalid_rows": 30}
        )
        assert result["check_status"] == "FAIL"


# ===================================================================
# 5. Filter expression end-to-end
# ===================================================================
class TestFilterExpressionPipeline:
    def test_filter_in_compiled_sql(self, handler, compiler):
        config = {
            "columns": ["email"],
            "pattern": "^[A-Z]+$",
            "filterExpression": "status = 'active'",
            "pass_threshold": 100,
        }
        _, compiled = pipeline(handler, compiler, config)
        assert "status = 'active'" in compiled["compiled_sql"]


# ===================================================================
# 6. Spark output present
# ===================================================================
class TestSparkOutput:
    @pytest.mark.parametrize(
        "vtype,extra",
        [
            ("regex", {"pattern": "^\\d+$"}),
            ("range", {"min_value": 0, "max_value": 100}),
            ("allowed_values", {"allowedValues": ["A", "B"]}),
            ("reference_lookup", {"referenceDataset": "ref.t", "referenceColumn": "c"}),
            ("business_rule", {"businessRuleExpression": "x > 0"}),
            ("cross_field", {"comparisonColumn": "b", "comparisonOperator": "="}),
            ("date_logic", {"comparisonColumn": "b", "comparisonOperator": "<="}),
            ("negative", {"negativeExpression": "x = 1"}),
        ],
    )
    def test_spark_output_present(self, handler, compiler, vtype, extra):
        config = {"columns": ["col"], "validationType": vtype, "pass_threshold": 100}
        config.update(extra)
        _, compiled = pipeline(handler, compiler, config)
        assert compiled.get("compiled_spark"), f"No spark output for {vtype}"
