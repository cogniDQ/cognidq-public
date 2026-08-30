"""P07 — CheckNodeHandler uniqueness mapping & result-parsing tests."""

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

sys.modules["app.services.execution.spark_executor"].SparkCheckExecutor = MagicMock
sys.modules["app.services.execution.spark_session_manager"].SparkSessionManager = MagicMock
sys.modules["app.services.execution"].SparkSessionManager = MagicMock

from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


# ===================================================================
# A) _build_canonical_rule — Uniqueness branch mapping
# ===================================================================
class TestUniquenessCanonicalRuleMapping:
    """Verify camelCase config → snake_case canonical rule forwarding."""

    def _build(self, handler, config_overrides=None):
        config = {
            "columns": ["email"],
            "pass_threshold": 100,
        }
        if config_overrides:
            config.update(config_overrides)
        return handler._build_canonical_rule("uniqueness", config, "public", "customers")

    def test_exact_mode_default(self, handler):
        rule = self._build(handler)
        assert rule["dimension"] == "uniqueness"
        assert rule["parameters"]["uniqueness_mode"] == "exact"
        assert rule["parameters"]["columns"] == ["email"]

    def test_explicit_mode_forwarded(self, handler):
        rule = self._build(handler, {"uniquenessMode": "composite", "columns": ["a", "b"]})
        assert rule["parameters"]["uniqueness_mode"] == "composite"

    def test_infers_scoped_from_scope_columns(self, handler):
        rule = self._build(handler, {"scopeColumns": ["dept"]})
        assert rule["parameters"]["uniqueness_mode"] == "scoped"
        assert rule["parameters"]["scope_columns"] == ["dept"]

    def test_infers_cross_dataset(self, handler):
        rule = self._build(handler, {"crossDatasetName": "legacy", "crossDatasetColumn": "id"})
        assert rule["parameters"]["uniqueness_mode"] == "cross_dataset"
        assert rule["parameters"]["cross_dataset_name"] == "legacy"
        assert rule["parameters"]["cross_dataset_column"] == "id"

    def test_infers_fuzzy(self, handler):
        rule = self._build(handler, {"fuzzyAlgorithm": "levenshtein"})
        assert rule["parameters"]["uniqueness_mode"] == "fuzzy"
        assert rule["parameters"]["fuzzy_algorithm"] == "levenshtein"

    def test_infers_temporal(self, handler):
        rule = self._build(handler, {"temporalWindow": "1d", "temporalColumn": "created_at"})
        assert rule["parameters"]["uniqueness_mode"] == "temporal"
        assert rule["parameters"]["temporal_window"] == "1d"
        assert rule["parameters"]["temporal_column"] == "created_at"

    def test_infers_composite_from_multiple_columns(self, handler):
        rule = self._build(handler, {"columns": ["order_id", "line_item"]})
        assert rule["parameters"]["uniqueness_mode"] == "composite"

    def test_null_handling_forwarded(self, handler):
        rule = self._build(handler, {"nullHandling": "include"})
        assert rule["parameters"]["null_handling"] == "include"

    def test_case_sensitive_forwarded(self, handler):
        rule = self._build(handler, {"caseSensitive": False})
        assert rule["parameters"]["case_sensitive"] is False

    def test_threshold_warn_forwarded(self, handler):
        rule = self._build(handler, {"thresholdWarn": 95})
        assert rule["parameters"]["threshold_warn"] == 95

    def test_filter_expression_forwarded(self, handler):
        rule = self._build(handler, {"filterExpression": "status = 'active'"})
        assert rule["parameters"]["filter_expression"] == "status = 'active'"

    def test_fuzzy_threshold_forwarded(self, handler):
        rule = self._build(handler, {"fuzzyAlgorithm": "levenshtein", "fuzzyThreshold": 0.9})
        assert rule["parameters"]["fuzzy_threshold"] == 0.9

    def test_backward_compat_single_column_no_mode(self, handler):
        """Old config: no uniquenessMode, single column → defaults to exact."""
        rule = self._build(handler)
        assert rule["parameters"]["uniqueness_mode"] == "exact"
        assert "parameters" in rule

    def test_parameters_dict_present(self, handler):
        """Rule must include a parameters dict (unlike old handler that omitted it)."""
        rule = self._build(handler)
        assert "parameters" in rule
        assert isinstance(rule["parameters"], dict)

    def test_threshold_pass_forwarded(self, handler):
        rule = self._build(handler, {"pass_threshold": 98})
        assert rule["parameters"]["threshold_pass"] == 98

    def test_severity_forwarded(self, handler):
        rule = self._build(handler, {"severity": "warning"})
        assert rule["severity"] == "warning"

    def test_entity_format(self, handler):
        rule = self._build(handler)
        assert "customers" in rule["entity"]
        assert "email" in rule["entity"]


# ===================================================================
# B) _parse_uniqueness_results
# ===================================================================
class TestParseUniquenessResults:
    """Verify structured result parsing for uniqueness checks."""

    def _parse(self, handler, row_data, params_overrides=None):
        params = {
            "uniqueness_mode": "exact",
            "threshold_pass": 100,
        }
        if params_overrides:
            params.update(params_overrides)
        canonical = {"dimension": "uniqueness", "parameters": params}
        return handler._parse_uniqueness_results([row_data], canonical)

    def test_basic_pass(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert result["check_status"] == "PASS"
        assert result["rows_scanned"] == 100
        assert result["rows_passed"] == 100
        assert result["rows_failed"] == 0
        assert float(result["pass_rate"]) == 100.0

    def test_basic_fail(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 20, "duplicate_groups": 5, "max_group_size": 8},
        )
        assert result["check_status"] == "FAIL"
        assert result["rows_passed"] == 80
        assert result["rows_failed"] == 20
        assert float(result["pass_rate"]) == 80.0

    def test_warn_threshold(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 3, "duplicate_groups": 1, "max_group_size": 3},
            {"threshold_pass": 100, "threshold_warn": 95},
        )
        assert result["check_status"] == "WARN"

    def test_uniqueness_mode_in_result(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 10, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
            {"uniqueness_mode": "composite"},
        )
        assert result["uniqueness_mode"] == "composite"

    def test_duplicate_groups_in_result(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 10, "duplicate_groups": 3, "max_group_size": 5},
        )
        assert result["duplicate_groups"] == 3
        assert result["max_group_size"] == 5
        assert result["avg_group_size"] == pytest.approx(3.33, abs=0.01)

    def test_avg_group_size_zero_when_no_groups(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert result["avg_group_size"] == 0

    def test_zero_rows(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 0, "duplicate_rows": 0, "duplicate_groups": 0, "max_group_size": 0},
        )
        assert result["check_status"] == "PASS"
        assert result["zero_rows"] is True
        assert float(result["pass_rate"]) == 100.0

    def test_pass_rate_decimal(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "duplicate_rows": 10, "duplicate_groups": 5, "max_group_size": 3},
        )
        assert isinstance(result["pass_rate"], Decimal)

    def test_all_duplicates(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 10, "duplicate_rows": 10, "duplicate_groups": 5, "max_group_size": 2},
        )
        assert result["check_status"] == "FAIL"
        assert float(result["pass_rate"]) == 0.0
        assert result["rows_passed"] == 0
