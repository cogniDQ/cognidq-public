"""P05 — CheckNodeHandler conformity mapping & result-parsing tests."""

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
# A) _build_canonical_rule — Conformity branch mapping
# ===================================================================
class TestConformityCanonicalRuleMapping:
    def _build(self, handler, config_overrides=None):
        config = {"columns": ["email"], "pass_threshold": 100}
        if config_overrides:
            config.update(config_overrides)
        return handler._build_canonical_rule("conformity", config, "public", "customers")

    def test_default_infers_regex(self, handler):
        rule = self._build(handler)
        assert rule["dimension"] == "conformity"
        assert rule["parameters"]["conformity_type"] == "regex"

    def test_explicit_type_forwarded(self, handler):
        rule = self._build(handler, {"conformityType": "length", "minLength": 5})
        assert rule["parameters"]["conformity_type"] == "length"

    def test_infers_regex_from_pattern(self, handler):
        rule = self._build(handler, {"regexPattern": "^\\d+$"})
        assert rule["parameters"]["conformity_type"] == "regex"
        assert rule["parameters"]["regex_pattern"] == "^\\d+$"

    def test_infers_standard(self, handler):
        rule = self._build(handler, {"standardName": "e164"})
        assert rule["parameters"]["conformity_type"] == "standard"
        assert rule["parameters"]["standard_name"] == "e164"

    def test_infers_length_from_min(self, handler):
        rule = self._build(handler, {"minLength": 5})
        assert rule["parameters"]["conformity_type"] == "length"
        assert rule["parameters"]["min_length"] == 5

    def test_infers_length_from_max(self, handler):
        rule = self._build(handler, {"maxLength": 20})
        assert rule["parameters"]["conformity_type"] == "length"
        assert rule["parameters"]["max_length"] == 20

    def test_infers_charset(self, handler):
        rule = self._build(handler, {"allowedCharacters": "a-zA-Z"})
        assert rule["parameters"]["conformity_type"] == "charset"
        assert rule["parameters"]["allowed_characters"] == "a-zA-Z"

    def test_infers_case(self, handler):
        rule = self._build(handler, {"caseRule": "upper"})
        assert rule["parameters"]["conformity_type"] == "case"
        assert rule["parameters"]["case_rule"] == "upper"

    def test_infers_structural(self, handler):
        rule = self._build(handler, {"structuralFormat": "json"})
        assert rule["parameters"]["conformity_type"] == "structural"
        assert rule["parameters"]["structural_format"] == "json"

    def test_trim_whitespace_forwarded(self, handler):
        rule = self._build(handler, {"trimWhitespace": False})
        assert rule["parameters"]["trim_whitespace"] is False

    def test_null_handling_forwarded(self, handler):
        rule = self._build(handler, {"nullHandling": "fail"})
        assert rule["parameters"]["null_handling"] == "fail"

    def test_threshold_warn_forwarded(self, handler):
        rule = self._build(handler, {"thresholdWarn": 95})
        assert rule["parameters"]["threshold_warn"] == 95

    def test_filter_expression_forwarded(self, handler):
        rule = self._build(handler, {"filterExpression": "active = true"})
        assert rule["parameters"]["filter_expression"] == "active = true"

    def test_severity_forwarded(self, handler):
        rule = self._build(handler, {"severity": "warning"})
        assert rule["severity"] == "warning"

    def test_threshold_pass_forwarded(self, handler):
        rule = self._build(handler, {"pass_threshold": 98})
        assert rule["parameters"]["threshold_pass"] == 98

    def test_backward_compat_old_pattern(self, handler):
        """Old config with 'pattern' key maps to regex_pattern."""
        rule = self._build(handler, {"pattern": "^[A-Z]+$"})
        assert rule["parameters"]["regex_pattern"] == "^[A-Z]+$"
        assert rule["parameters"]["conformity_type"] == "regex"

    def test_parameters_dict_present(self, handler):
        rule = self._build(handler)
        assert "parameters" in rule
        assert isinstance(rule["parameters"], dict)

    def test_columns_forwarded(self, handler):
        rule = self._build(handler, {"columns": ["phone"]})
        assert rule["parameters"]["columns"] == ["phone"]


# ===================================================================
# B) _parse_conformity_results
# ===================================================================
class TestParseConformityResults:
    def _parse(self, handler, row_data, params_overrides=None):
        params = {"conformity_type": "regex", "threshold_pass": 100}
        if params_overrides:
            params.update(params_overrides)
        canonical = {"dimension": "conformity", "parameters": params}
        return handler._parse_conformity_results([row_data], canonical)

    def test_basic_pass(self, handler):
        result = self._parse(
            handler, {"total_rows": 100, "conforming_rows": 100, "non_conforming_rows": 0}
        )
        assert result["check_status"] == "PASS"
        assert result["rows_scanned"] == 100
        assert result["rows_passed"] == 100
        assert result["rows_failed"] == 0
        assert float(result["pass_rate"]) == 100.0

    def test_basic_fail(self, handler):
        result = self._parse(
            handler, {"total_rows": 100, "conforming_rows": 80, "non_conforming_rows": 20}
        )
        assert result["check_status"] == "FAIL"
        assert result["rows_passed"] == 80
        assert result["rows_failed"] == 20

    def test_warn_threshold(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 100, "conforming_rows": 97, "non_conforming_rows": 3},
            {"threshold_pass": 100, "threshold_warn": 95},
        )
        assert result["check_status"] == "WARN"

    def test_conformity_type_in_result(self, handler):
        result = self._parse(
            handler,
            {"total_rows": 10, "conforming_rows": 10, "non_conforming_rows": 0},
            {"conformity_type": "standard"},
        )
        assert result["conformity_type"] == "standard"

    def test_conformity_rate_in_result(self, handler):
        result = self._parse(
            handler, {"total_rows": 100, "conforming_rows": 90, "non_conforming_rows": 10}
        )
        assert "conformity_rate" in result
        assert float(result["conformity_rate"]) == 90.0

    def test_zero_rows(self, handler):
        result = self._parse(
            handler, {"total_rows": 0, "conforming_rows": 0, "non_conforming_rows": 0}
        )
        assert result["check_status"] == "PASS"
        assert result["zero_rows"] is True

    def test_pass_rate_is_decimal(self, handler):
        result = self._parse(
            handler, {"total_rows": 100, "conforming_rows": 100, "non_conforming_rows": 0}
        )
        assert isinstance(result["pass_rate"], Decimal)

    def test_all_non_conforming(self, handler):
        result = self._parse(
            handler, {"total_rows": 50, "conforming_rows": 0, "non_conforming_rows": 50}
        )
        assert result["check_status"] == "FAIL"
        assert float(result["pass_rate"]) == 0.0
        assert result["rows_passed"] == 0
