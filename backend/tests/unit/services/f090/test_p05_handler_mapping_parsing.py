"""P05 — Handler Mapping & Parsing Tests (check_node.py)."""

import sys
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# Stub pyspark
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

from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    h = CheckNodeHandler.__new__(CheckNodeHandler)
    h.db = MagicMock()
    h.rule_service = MagicMock()
    return h


# ── Type Inference ───────────────────────────────────────────


class TestTypeInference:
    def test_statistical_method_infers_statistical(self, handler):
        config = {"statisticalMethod": "zscore", "columns": ["salary"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "statistical"

    def test_formula_infers_derived_value(self, handler):
        config = {"formula": '"qty" * "price"', "columns": ["total"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "derived_value"

    def test_tolerance_with_ref_infers_tolerated_deviation(self, handler):
        config = {
            "referenceDataset": "ref",
            "toleranceValue": 5.0,
            "joinKeys": ["id"],
            "columns": ["price"],
        }
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "tolerated_deviation"

    def test_ref_dataset_infers_reference_comparison(self, handler):
        config = {"referenceDataset": "ref", "joinKeys": ["id"], "columns": ["price"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "reference_comparison"

    def test_empty_config_infers_reference_comparison(self, handler):
        config = {"columns": ["price"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "reference_comparison"

    def test_explicit_type_preserved(self, handler):
        config = {"accuracyType": "derived_value", "formula": "x+y", "columns": ["total"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "derived_value"

    def test_explicit_type_overrides_inference(self, handler):
        config = {
            "accuracyType": "statistical",
            "statisticalMethod": "zscore",
            "referenceDataset": "ref",
            "columns": ["val"],
        }
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "statistical"

    def test_statistical_priority_over_formula(self, handler):
        config = {"statisticalMethod": "iqr", "formula": "a+b", "columns": ["val"]}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["parameters"]["accuracy_type"] == "statistical"


# ── Key Forwarding ───────────────────────────────────────────


class TestKeyForwarding:
    def _canon(self, handler, **config_overrides):
        config = {"accuracyType": "reference_comparison", "columns": ["price"]}
        config.update(config_overrides)
        return handler._build_canonical_rule("accuracy", config, "public", "t")

    def test_reference_dataset(self, handler):
        result = self._canon(handler, referenceDataset="master.table")
        assert result["parameters"]["reference_dataset"] == "master.table"

    def test_reference_column(self, handler):
        result = self._canon(handler, referenceColumn="ref_price")
        assert result["parameters"]["reference_column"] == "ref_price"

    def test_join_keys(self, handler):
        result = self._canon(handler, joinKeys=["id", "region"])
        assert result["parameters"]["join_keys"] == ["id", "region"]

    def test_tolerance_type(self, handler):
        result = self._canon(handler, toleranceType="absolute")
        assert result["parameters"]["tolerance_type"] == "absolute"

    def test_tolerance_value(self, handler):
        result = self._canon(handler, toleranceValue=0.5)
        assert result["parameters"]["tolerance_value"] == 0.5

    def test_statistical_method(self, handler):
        result = self._canon(handler, statisticalMethod="iqr")
        assert result["parameters"]["statistical_method"] == "iqr"

    def test_statistical_threshold(self, handler):
        result = self._canon(handler, statisticalThreshold=2.5)
        assert result["parameters"]["statistical_threshold"] == 2.5

    def test_formula(self, handler):
        result = self._canon(handler, formula='"a" + "b"')
        assert result["parameters"]["formula"] == '"a" + "b"'

    def test_null_handling(self, handler):
        result = self._canon(handler, nullHandling="skip")
        assert result["parameters"]["null_handling"] == "skip"

    def test_threshold_warn(self, handler):
        result = self._canon(handler, thresholdWarn=90)
        assert result["parameters"]["threshold_warn"] == 90

    def test_filter_expression(self, handler):
        result = self._canon(handler, filterExpression="active = true")
        assert result["parameters"]["filter_expression"] == "active = true"


# ── Entity Format ────────────────────────────────────────────


class TestEntityFormat:
    def test_entity_has_table_and_column(self, handler):
        result = handler._build_canonical_rule(
            "accuracy", {"columns": ["price"]}, "public", "orders"
        )
        assert "orders" in result["entity"]
        assert "price" in result["entity"]


# ── Canonical Rule Structure ─────────────────────────────────


class TestCanonicalRuleStructure:
    def test_dimension_is_accuracy(self, handler):
        result = handler._build_canonical_rule("accuracy", {"columns": ["price"]}, "public", "t")
        assert result["dimension"] == "accuracy"

    def test_default_severity(self, handler):
        result = handler._build_canonical_rule("accuracy", {"columns": ["price"]}, "public", "t")
        assert result["severity"] == "high"

    def test_custom_severity(self, handler):
        config = {"columns": ["price"], "severity": "critical"}
        result = handler._build_canonical_rule("accuracy", config, "public", "t")
        assert result["severity"] == "critical"


# ── Result Parsing ───────────────────────────────────────────


class TestParseAccuracyResults:
    def _parse(self, handler, row, **param_overrides):
        params = {"accuracy_type": "reference_comparison", "threshold_pass": 95}
        params.update(param_overrides)
        canonical = {"parameters": params}
        return handler._parse_accuracy_results([row], canonical)

    def test_pass_status(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 98,
            "inaccurate_rows": 2,
        }
        result = self._parse(handler, row)
        assert result["check_status"] == "PASS"

    def test_fail_status(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 90,
            "inaccurate_rows": 10,
        }
        result = self._parse(handler, row)
        assert result["check_status"] == "FAIL"

    def test_warn_status(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 92,
            "inaccurate_rows": 8,
        }
        result = self._parse(handler, row, threshold_warn=90)
        assert result["check_status"] == "WARN"

    def test_accuracy_rate_decimal(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 80,
            "unverifiable_rows": 20,
            "accurate_rows": 76,
            "inaccurate_rows": 4,
        }
        result = self._parse(handler, row)
        assert isinstance(result["accuracy_rate"], Decimal)
        assert result["accuracy_rate"] == Decimal(76) / Decimal(80) * Decimal(100)

    def test_accuracy_type_forwarded(self, handler):
        row = {
            "total_rows": 10,
            "verified_rows": 10,
            "unverifiable_rows": 0,
            "accurate_rows": 10,
            "inaccurate_rows": 0,
        }
        result = self._parse(handler, row, accuracy_type="statistical")
        assert result["accuracy_type"] == "statistical"

    def test_verified_and_unverifiable_rows(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 80,
            "unverifiable_rows": 20,
            "accurate_rows": 80,
            "inaccurate_rows": 0,
        }
        result = self._parse(handler, row)
        assert result["verified_rows"] == 80
        assert result["unverifiable_rows"] == 20

    def test_zero_rows_flag(self, handler):
        row = {
            "total_rows": 0,
            "verified_rows": 0,
            "unverifiable_rows": 0,
            "accurate_rows": 0,
            "inaccurate_rows": 0,
        }
        result = self._parse(handler, row)
        assert result["zero_rows"] is True
        assert result["accuracy_rate"] == Decimal(100)

    def test_rows_scanned_and_passed(self, handler):
        row = {
            "total_rows": 50,
            "verified_rows": 50,
            "unverifiable_rows": 0,
            "accurate_rows": 48,
            "inaccurate_rows": 2,
        }
        result = self._parse(handler, row)
        assert result["rows_scanned"] == 50
        assert result["rows_passed"] == 48
        assert result["rows_failed"] == 2

    def test_pass_rate_same_as_accuracy_rate(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 95,
            "inaccurate_rows": 5,
        }
        result = self._parse(handler, row)
        assert result["pass_rate"] == result["accuracy_rate"]
