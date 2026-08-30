"""P06 — CheckNodeHandler mapping & result-parsing tests."""

import sys
import types
from unittest.mock import MagicMock

# Stub out pyspark and heavy deps before importing check_node
for mod_name in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
    "app.services.execution.spark_executor",
    "app.services.execution.spark_session_manager",
    "app.services.execution",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Ensure SparkCheckExecutor attribute exists on the stub
sys.modules["app.services.execution.spark_executor"].SparkCheckExecutor = MagicMock
sys.modules["app.services.execution.spark_session_manager"].SparkSessionManager = MagicMock
sys.modules["app.services.execution"].SparkSessionManager = MagicMock

from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    h = CheckNodeHandler.__new__(CheckNodeHandler)
    return h


# ------------------------------------------------------------------
# A) _build_canonical_rule mapping
# ------------------------------------------------------------------
class TestCanonicalRuleMapping:
    """Verify camelCase config → snake_case canonical rule forwarding."""

    def _build(self, handler, config_overrides=None):
        config = {
            "columns": ["email"],
            "checkMode": "null",
            "pass_threshold": 95,
        }
        if config_overrides:
            config.update(config_overrides)
        return handler._build_canonical_rule("completeness", config, "public", "customers")

    def test_default_null_mode(self, handler):
        rule = self._build(handler)
        assert rule["dimension"] == "completeness"
        assert rule["parameters"]["check_mode"] == "null"
        assert rule["parameters"]["threshold_pass"] == 95

    def test_placeholder_mode_forwarding(self, handler):
        rule = self._build(
            handler,
            {
                "checkMode": "placeholder",
                "placeholderValues": ["N/A", "TBD"],
            },
        )
        p = rule["parameters"]
        assert p["check_mode"] == "placeholder"
        assert p["placeholder_values"] == ["N/A", "TBD"]

    def test_conditional_mode_forwarding(self, handler):
        rule = self._build(
            handler,
            {
                "checkMode": "conditional",
                "conditionColumn": "status",
                "conditionValue": "active",
            },
        )
        p = rule["parameters"]
        assert p["condition_column"] == "status"
        assert p["condition_value"] == "active"

    def test_multi_field_mode_forwarding(self, handler):
        rule = self._build(
            handler,
            {
                "checkMode": "multi_field",
                "multiFieldMode": "any",
                "columns": ["phone", "email"],
            },
        )
        p = rule["parameters"]
        assert p["multi_field_mode"] == "any"
        assert p["columns"] == ["phone", "email"]

    def test_group_mode_forwarding(self, handler):
        rule = self._build(
            handler,
            {
                "checkMode": "group",
                "groupByColumns": ["country"],
            },
        )
        p = rule["parameters"]
        assert p["group_by_columns"] == ["country"]

    def test_warn_threshold_forwarding(self, handler):
        rule = self._build(handler, {"thresholdWarn": 80})
        assert rule["parameters"]["threshold_warn"] == 80

    def test_filter_expression_forwarding(self, handler):
        rule = self._build(handler, {"filterExpression": "status = 'active'"})
        assert rule["parameters"]["filter_expression"] == "status = 'active'"

    def test_include_empty_strings_forwarding(self, handler):
        rule = self._build(handler, {"includeEmptyStrings": True})
        assert rule["parameters"]["include_empty_strings"] is True


# ------------------------------------------------------------------
# B) _determine_check_status helper
# ------------------------------------------------------------------
class TestDetermineCheckStatus:
    def test_pass(self, handler):
        assert handler._determine_check_status(100.0, 95.0, None) == "PASS"

    def test_fail_no_warn(self, handler):
        assert handler._determine_check_status(90.0, 95.0, None) == "FAIL"

    def test_warn_between_thresholds(self, handler):
        assert handler._determine_check_status(85.0, 95.0, 80.0) == "WARN"

    def test_fail_below_warn(self, handler):
        assert handler._determine_check_status(70.0, 95.0, 80.0) == "FAIL"

    def test_exact_pass_boundary(self, handler):
        assert handler._determine_check_status(95.0, 95.0, 80.0) == "PASS"

    def test_exact_warn_boundary(self, handler):
        assert handler._determine_check_status(80.0, 95.0, 80.0) == "WARN"


# ------------------------------------------------------------------
# C) _worst_status helper
# ------------------------------------------------------------------
class TestWorstStatus:
    def test_pass_pass(self, handler):
        assert handler._worst_status("PASS", "PASS") == "PASS"

    def test_pass_fail(self, handler):
        assert handler._worst_status("PASS", "FAIL") == "FAIL"

    def test_warn_fail(self, handler):
        assert handler._worst_status("WARN", "FAIL") == "FAIL"

    def test_fail_pass(self, handler):
        assert handler._worst_status("FAIL", "PASS") == "FAIL"


# ------------------------------------------------------------------
# D) _parse_completeness_results — single-row modes
# ------------------------------------------------------------------
class TestParseCompleteness:
    def _parse(self, handler, rows, check_mode="null", threshold_pass=100, threshold_warn=None):
        canonical = {
            "dimension": "completeness",
            "parameters": {
                "check_mode": check_mode,
                "threshold_pass": threshold_pass,
            },
        }
        if threshold_warn is not None:
            canonical["parameters"]["threshold_warn"] = threshold_warn
        return handler._parse_completeness_results(rows, canonical)

    def test_null_mode_pass(self, handler):
        result = self._parse(handler, [{"total_rows": "100", "null_rows": "0"}])
        assert result["check_status"] == "PASS"
        assert result["rows_scanned"] == 100
        assert result["rows_passed"] == 100
        assert result["rows_failed"] == 0
        assert result["check_mode"] == "null"
        assert result["zero_rows"] is False

    def test_null_mode_fail(self, handler):
        result = self._parse(handler, [{"total_rows": "100", "null_rows": "10"}], threshold_pass=95)
        assert result["check_status"] == "FAIL"
        assert result["rows_failed"] == 10

    def test_warn_threshold(self, handler):
        result = self._parse(
            handler,
            [{"total_rows": "100", "null_rows": "15"}],
            threshold_pass=95,
            threshold_warn=80,
        )
        assert result["check_status"] == "WARN"

    def test_zero_rows_flag(self, handler):
        result = self._parse(handler, [{"total_rows": "0", "null_rows": "0"}])
        assert result["zero_rows"] is True
        assert result["check_status"] == "PASS"

    def test_empty_mode_preserved(self, handler):
        result = self._parse(handler, [{"total_rows": "50", "null_rows": "5"}], check_mode="empty")
        assert result["check_mode"] == "empty"


# ------------------------------------------------------------------
# E) Group mode parsing
# ------------------------------------------------------------------
class TestParseGroupCompleteness:
    def _parse_group(self, handler, rows, threshold_pass=95, threshold_warn=None, group_cols=None):
        canonical = {
            "dimension": "completeness",
            "parameters": {
                "check_mode": "group",
                "threshold_pass": threshold_pass,
                "group_by_columns": group_cols or ["country"],
            },
        }
        if threshold_warn is not None:
            canonical["parameters"]["threshold_warn"] = threshold_warn
        return handler._parse_group_completeness_results(rows, canonical)

    def test_two_groups_worst_status(self, handler):
        rows = [
            {"country": "US", "total_rows": "100", "null_rows": "2"},
            {"country": "UK", "total_rows": "100", "null_rows": "20"},
        ]
        result = self._parse_group(handler, rows)
        assert result["check_status"] == "FAIL"
        assert result["rows_scanned"] == 200
        assert result["check_mode"] == "group"
        groups = result["metadata"]["group_results"]
        assert len(groups) == 2
        assert groups[0]["group_key"] == {"country": "US"}
        assert groups[0]["check_status"] == "PASS"
        assert groups[1]["check_status"] == "FAIL"

    def test_all_groups_pass(self, handler):
        rows = [
            {"country": "US", "total_rows": "50", "null_rows": "0"},
            {"country": "UK", "total_rows": "50", "null_rows": "0"},
        ]
        result = self._parse_group(handler, rows)
        assert result["check_status"] == "PASS"
        assert result["rows_passed"] == 100

    def test_group_warn(self, handler):
        rows = [
            {"country": "US", "total_rows": "100", "null_rows": "10"},
        ]
        result = self._parse_group(handler, rows, threshold_pass=95, threshold_warn=85)
        assert result["check_status"] == "WARN"

    def test_empty_groups(self, handler):
        result = self._parse_group(handler, [])
        assert result["rows_scanned"] == 0
        assert result["zero_rows"] is True
