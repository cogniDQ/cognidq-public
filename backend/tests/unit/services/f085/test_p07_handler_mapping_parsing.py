"""P07 — CheckNodeHandler validity mapping & result-parsing tests."""

import sys
import types
from unittest.mock import MagicMock

# Stub out pyspark and heavy deps before importing check_node
for mod_name in ["pyspark", "pyspark.sql", "pyspark.sql.functions"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)
_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)
_rn = types.ModuleType("app.services.execution.result_normalizer")
_rn.normalize_summary = MagicMock(return_value={})
_rn.normalize_violations = MagicMock(return_value=[])
sys.modules.setdefault("app.services.execution.result_normalizer", _rn)

from decimal import Decimal

import pytest
from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


# ===================================================================
# A) _build_canonical_rule — Validity branch mapping
# ===================================================================
class TestValidityCanonicalRuleMapping:
    """Verify camelCase config → snake_case canonical rule forwarding."""

    def _build(self, handler, config_overrides=None):
        config = {
            "columns": ["email"],
            "pass_threshold": 95,
        }
        if config_overrides:
            config.update(config_overrides)
        return handler._build_canonical_rule("validity", config, "public", "customers")

    def test_validation_type_forwarded(self, handler):
        rule = self._build(
            handler, {"validationType": "allowed_values", "allowedValues": ["A", "B"]}
        )
        assert rule["parameters"]["validation_type"] == "allowed_values"
        assert rule["parameters"]["allowed_values"] == ["A", "B"]

    def test_infers_regex_from_pattern(self, handler):
        rule = self._build(handler, {"pattern": "^[A-Z]+$"})
        assert rule["parameters"]["validation_type"] == "regex"
        assert rule["parameters"]["regex_pattern"] == "^[A-Z]+$"

    def test_infers_range_from_min_max(self, handler):
        rule = self._build(handler, {"min_value": 0, "max_value": 100})
        assert rule["parameters"]["validation_type"] == "range"

    def test_infers_allowed_values(self, handler):
        rule = self._build(handler, {"allowedValues": ["A", "B"]})
        assert rule["parameters"]["validation_type"] == "allowed_values"

    def test_reference_lookup_mapping(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "reference_lookup",
                "referenceDataset": "ref.countries",
                "referenceColumn": "code",
            },
        )
        assert rule["parameters"]["validation_type"] == "reference_lookup"
        assert rule["parameters"]["reference_dataset"] == "ref.countries"
        assert rule["parameters"]["reference_column"] == "code"

    def test_business_rule_mapping(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "business_rule",
                "businessRuleExpression": "amount > 0",
            },
        )
        assert rule["parameters"]["validation_type"] == "business_rule"
        assert rule["parameters"]["business_rule_expression"] == "amount > 0"

    def test_cross_field_mapping(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "cross_field",
                "comparisonColumn": "col_b",
                "comparisonOperator": "=",
            },
        )
        assert rule["parameters"]["validation_type"] == "cross_field"
        assert rule["parameters"]["comparison_column"] == "col_b"
        assert rule["parameters"]["comparison_operator"] == "="

    def test_date_logic_mapping(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "date_logic",
                "comparisonColumn": "end_date",
                "comparisonOperator": "<=",
            },
        )
        assert rule["parameters"]["validation_type"] == "date_logic"

    def test_negative_mapping(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "negative",
                "negativeExpression": "status = 'DELETED'",
            },
        )
        assert rule["parameters"]["validation_type"] == "negative"
        assert rule["parameters"]["negative_expression"] == "status = 'DELETED'"

    def test_null_handling_forwarded(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "regex",
                "pattern": "^\\d+$",
                "nullHandling": "skip",
            },
        )
        assert rule["parameters"]["null_handling"] == "skip"

    def test_case_sensitive_forwarded(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "allowed_values",
                "allowedValues": ["A"],
                "caseSensitive": False,
            },
        )
        assert rule["parameters"]["case_sensitive"] is False

    def test_threshold_warn_forwarded(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "regex",
                "pattern": "^\\d+$",
                "thresholdWarn": 80,
            },
        )
        assert rule["parameters"]["threshold_warn"] == 80

    def test_filter_expression_forwarded(self, handler):
        rule = self._build(
            handler,
            {
                "validationType": "regex",
                "pattern": "^\\d+$",
                "filterExpression": "active = true",
            },
        )
        assert rule["parameters"]["filter_expression"] == "active = true"

    def test_backward_compat_old_config(self, handler):
        """Old config structure (no validationType) still produces a valid rule."""
        rule = self._build(handler, {"pattern": "^[A-Z]+$"})
        assert rule["dimension"] == "validity"
        assert rule["parameters"]["validation_type"] == "regex"

    def test_infer_reference_lookup_from_keys(self, handler):
        """When no validationType but referenceDataset is set, infer reference_lookup."""
        rule = self._build(
            handler,
            {
                "referenceDataset": "countries",
                "referenceColumn": "code",
            },
        )
        assert rule["parameters"]["validation_type"] == "reference_lookup"

    def test_infer_business_rule_from_keys(self, handler):
        rule = self._build(handler, {"businessRuleExpression": "amount > 0"})
        assert rule["parameters"]["validation_type"] == "business_rule"

    def test_infer_negative_from_keys(self, handler):
        rule = self._build(handler, {"negativeExpression": "status = 'DELETED'"})
        assert rule["parameters"]["validation_type"] == "negative"


# ===================================================================
# B) _parse_validity_results
# ===================================================================
class TestParseValidityResults:
    def _make_canonical(self, **overrides):
        params = {
            "validation_type": "regex",
            "threshold_pass": 100,
            "threshold_warn": None,
            "null_handling": "fail",
        }
        params.update(overrides)
        return {"dimension": "validity", "parameters": params}

    def test_basic_pass(self, handler):
        rows = [{"total_rows": 100, "valid_rows": 100, "invalid_rows": 0}]
        result = handler._parse_validity_results(rows, self._make_canonical())
        assert result["check_status"] == "PASS"
        assert result["rows_scanned"] == 100
        assert result["rows_passed"] == 100
        assert result["rows_failed"] == 0
        assert result["validation_type"] == "regex"

    def test_basic_fail(self, handler):
        rows = [{"total_rows": 100, "valid_rows": 80, "invalid_rows": 20}]
        result = handler._parse_validity_results(rows, self._make_canonical(threshold_pass=90))
        assert result["check_status"] == "FAIL"
        assert result["rows_failed"] == 20

    def test_warn_threshold(self, handler):
        rows = [{"total_rows": 100, "valid_rows": 85, "invalid_rows": 15}]
        result = handler._parse_validity_results(
            rows, self._make_canonical(threshold_pass=90, threshold_warn=80)
        )
        assert result["check_status"] == "WARN"

    def test_skip_null_handling(self, handler):
        rows = [{"total_rows": 90, "valid_rows": 90, "invalid_rows": 0, "skipped_rows": 10}]
        result = handler._parse_validity_results(rows, self._make_canonical(null_handling="skip"))
        assert result["skipped_rows"] == 10
        assert result["rows_scanned"] == 100  # total + skipped
        assert result["check_status"] == "PASS"

    def test_zero_rows(self, handler):
        rows = [{"total_rows": 0, "valid_rows": 0, "invalid_rows": 0}]
        result = handler._parse_validity_results(rows, self._make_canonical())
        assert result["zero_rows"] is True
        assert result["check_status"] == "PASS"

    def test_validation_type_in_result(self, handler):
        rows = [{"total_rows": 10, "valid_rows": 10, "invalid_rows": 0}]
        result = handler._parse_validity_results(
            rows, self._make_canonical(validation_type="reference_lookup")
        )
        assert result["validation_type"] == "reference_lookup"

    def test_pass_rate_decimal(self, handler):
        rows = [{"total_rows": 3, "valid_rows": 2, "invalid_rows": 1}]
        result = handler._parse_validity_results(rows, self._make_canonical(threshold_pass=50))
        assert isinstance(result["pass_rate"], Decimal)
        assert float(result["pass_rate"]) > 66
        assert float(result["pass_rate"]) < 67
