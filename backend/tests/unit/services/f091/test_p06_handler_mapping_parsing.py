"""P06 — Handler Mapping + Result Parsing Tests."""

import sys
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# Stub pyspark
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

from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    h = CheckNodeHandler.__new__(CheckNodeHandler)
    h.db = MagicMock()
    h.rule_service = MagicMock()
    return h


# ── Key Forwarding ───────────────────────────────────────────


class TestKeyForwarding:
    def _canon(self, handler, **extra):
        config = {"columns": ["amount"], "reconciliationType": "one_to_one", **extra}
        return handler._build_canonical_rule("reconciliation", config, "public", "t")

    def test_source_dataset(self, handler):
        result = self._canon(handler, sourceDataset="src_orders")
        assert result["parameters"]["source_dataset"] == "src_orders"

    def test_target_dataset(self, handler):
        result = self._canon(handler, targetDataset="tgt_orders")
        assert result["parameters"]["target_dataset"] == "tgt_orders"

    def test_reconciliation_type(self, handler):
        result = self._canon(handler)
        assert result["parameters"]["reconciliation_type"] == "one_to_one"

    def test_join_keys(self, handler):
        result = self._canon(handler, joinKeys=["id", "region"])
        assert result["parameters"]["join_keys"] == ["id", "region"]

    def test_compare_columns(self, handler):
        result = self._canon(handler, compareColumns=["name", "email"])
        assert result["parameters"]["compare_columns"] == ["name", "email"]

    def test_compare_column(self, handler):
        result = self._canon(handler, compareColumn="amount")
        assert result["parameters"]["compare_column"] == "amount"

    def test_aggregate_column(self, handler):
        result = self._canon(handler, aggregateColumn="total")
        assert result["parameters"]["aggregate_column"] == "total"

    def test_aggregate_function(self, handler):
        result = self._canon(handler, aggregateFunction="SUM")
        assert result["parameters"]["aggregate_function"] == "SUM"

    def test_tolerance_type(self, handler):
        result = self._canon(handler, toleranceType="absolute")
        assert result["parameters"]["tolerance_type"] == "absolute"

    def test_tolerance_value(self, handler):
        result = self._canon(handler, toleranceValue=0.01)
        assert result["parameters"]["tolerance_value"] == 0.01

    def test_source_filter(self, handler):
        result = self._canon(handler, sourceFilter="active = true")
        assert result["parameters"]["source_filter"] == "active = true"

    def test_target_filter(self, handler):
        result = self._canon(handler, targetFilter="valid = true")
        assert result["parameters"]["target_filter"] == "valid = true"

    def test_group_by_columns(self, handler):
        result = self._canon(handler, groupByColumns=["region"])
        assert result["parameters"]["group_by_columns"] == ["region"]

    def test_threshold_warn(self, handler):
        result = self._canon(handler, thresholdWarn=95)
        assert result["parameters"]["threshold_warn"] == 95


# ── Canonical Rule Structure ─────────────────────────────────


class TestCanonicalStructure:
    def test_dimension_is_reconciliation(self, handler):
        config = {"reconciliationType": "record_count"}
        result = handler._build_canonical_rule("reconciliation", config, "public", "t")
        assert result["dimension"] == "reconciliation"

    def test_default_severity_critical(self, handler):
        config = {"reconciliationType": "record_count"}
        result = handler._build_canonical_rule("reconciliation", config, "public", "t")
        assert result["severity"] == "critical"

    def test_custom_severity(self, handler):
        config = {"reconciliationType": "record_count", "severity": "high"}
        result = handler._build_canonical_rule("reconciliation", config, "public", "t")
        assert result["severity"] == "high"


# ── Result Parsing ───────────────────────────────────────────


class TestParseRecordCount:
    def test_pass_equal_counts(self, handler):
        row = {"source_count": 1000, "target_count": 1000}
        canonical = {"parameters": {"reconciliation_type": "record_count", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"
        assert result["match_rate"] == Decimal(100)

    def test_fail_unequal_counts(self, handler):
        row = {"source_count": 1000, "target_count": 900}
        canonical = {"parameters": {"reconciliation_type": "record_count", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"
        assert result["match_rate"] == Decimal(90)

    def test_zero_counts(self, handler):
        row = {"source_count": 0, "target_count": 0}
        canonical = {"parameters": {"reconciliation_type": "record_count", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["match_rate"] == Decimal(100)
        assert result["zero_rows"] is True


class TestParseOneToOne:
    def test_pass(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "one_to_one", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"
        assert result["match_rate"] == Decimal(100)

    def test_fail_with_missing(self, handler):
        row = {
            "source_count": 100,
            "target_count": 90,
            "matched_count": 90,
            "missing_in_target": 10,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "one_to_one", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"
        assert result["missing_in_target"] == 10

    def test_extra_in_target(self, handler):
        row = {
            "source_count": 100,
            "target_count": 110,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 10,
        }
        canonical = {"parameters": {"reconciliation_type": "one_to_one", "threshold_pass": 90}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["extra_in_target"] == 10


class TestParseAggregate:
    def test_pass_equal(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "source_agg": 50000,
            "target_agg": 50000,
        }
        canonical = {"parameters": {"reconciliation_type": "aggregate", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"
        assert result["match_rate"] == Decimal(100)

    def test_fail_unequal(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "source_agg": 50000,
            "target_agg": 49000,
        }
        canonical = {"parameters": {"reconciliation_type": "aggregate", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"
        assert result["match_rate"] == Decimal(0)

    def test_pass_within_absolute_tolerance(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "source_agg": 10000,
            "target_agg": 10005,
        }
        canonical = {
            "parameters": {
                "reconciliation_type": "aggregate",
                "threshold_pass": 100,
                "tolerance_type": "absolute",
                "tolerance_value": 10,
            }
        }
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"


class TestParseFieldLevel:
    def test_pass(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "field_match_count": 98,
            "field_mismatch_count": 2,
        }
        canonical = {"parameters": {"reconciliation_type": "field_level", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"
        assert result["match_rate"] == Decimal(98)

    def test_fail(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "field_match_count": 80,
            "field_mismatch_count": 20,
        }
        canonical = {"parameters": {"reconciliation_type": "field_level", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"


class TestParseTolerance:
    def test_pass(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 200,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "within_tolerance": 195,
            "outside_tolerance": 5,
        }
        canonical = {"parameters": {"reconciliation_type": "tolerance", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"

    def test_fail(self, handler):
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "within_tolerance": 80,
            "outside_tolerance": 20,
        }
        canonical = {"parameters": {"reconciliation_type": "tolerance", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"


class TestParseMissingExtra:
    def test_pass_no_missing_or_extra(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "missing_extra", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "PASS"

    def test_fail_missing(self, handler):
        row = {
            "source_count": 100,
            "target_count": 90,
            "matched_count": 90,
            "missing_in_target": 10,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "missing_extra", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "FAIL"


class TestParseWarn:
    def test_warn_between_thresholds(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 97,
            "missing_in_target": 3,
            "extra_in_target": 0,
        }
        canonical = {
            "parameters": {
                "reconciliation_type": "one_to_one",
                "threshold_pass": 99,
                "threshold_warn": 95,
            }
        }
        result = handler._parse_reconciliation_results([row], canonical)
        assert result["check_status"] == "WARN"


class TestParseDecimal:
    def test_match_rate_is_decimal(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 99,
            "missing_in_target": 1,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "one_to_one", "threshold_pass": 95}}
        result = handler._parse_reconciliation_results([row], canonical)
        assert isinstance(result["match_rate"], Decimal)


class TestParseResultFields:
    def test_all_fields_present(self, handler):
        row = {
            "source_count": 50,
            "target_count": 50,
            "matched_count": 50,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        canonical = {"parameters": {"reconciliation_type": "one_to_one", "threshold_pass": 100}}
        result = handler._parse_reconciliation_results([row], canonical)
        for key in (
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "pass_rate",
            "match_rate",
            "check_status",
            "reconciliation_type",
            "source_count",
            "target_count",
            "matched_count",
            "missing_in_target",
            "extra_in_target",
            "zero_rows",
            "violations",
        ):
            assert key in result, f"Missing key: {key}"
