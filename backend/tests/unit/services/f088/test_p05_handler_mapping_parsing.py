"""P05 — Handler mapping and result parsing for consistency checks."""

import sys
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

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

from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


# ── Mapping: Type Inference ─────────────────────────────────────


class TestMappingTypeInference:
    def test_default_intra_record(self, handler):
        r = handler._build_canonical_rule("consistency", {"columns": ["a"]}, "s", "t")
        assert r["parameters"]["consistency_type"] == "intra_record"

    def test_explicit_type(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "formula",
                "ruleExpression": "a + b",
                "expectedColumn": "c",
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "formula"

    def test_infer_from_aggregation_function(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "aggregationFunction": "SUM",
                "groupByColumns": ["oid"],
                "expectedColumn": "total",
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "aggregation"

    def test_infer_from_comparison_dataset_join_keys(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "comparisonDataset": "other.tbl",
                "joinKeys": ["id"],
                "comparisonColumns": ["status"],
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "cross_table"

    def test_infer_from_group_by_comparison_columns(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "groupByColumns": ["cid"],
                "comparisonColumns": ["email"],
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "inter_record"

    def test_infer_from_comparison_column(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "comparisonColumn": "end_date",
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "temporal"

    def test_infer_from_expected_column(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "expectedColumn": "total",
                "ruleExpression": "a + b",
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "formula"

    def test_infer_from_reference_column(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["price"],
                "referenceColumn": "expected_price",
            },
            "s",
            "t",
        )
        assert r["parameters"]["consistency_type"] == "intra_record"


# ── Mapping: Key Forwarding ─────────────────────────────────────


class TestMappingKeyForwarding:
    def test_rule_expression(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a" = "b"',
            },
            "s",
            "t",
        )
        assert r["parameters"]["rule_expression"] == '"a" = "b"'

    def test_expected_column(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "formula",
                "ruleExpression": "a+b",
                "expectedColumn": "total",
            },
            "s",
            "t",
        )
        assert r["parameters"]["expected_column"] == "total"

    def test_comparison_dataset(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "cross_table",
                "comparisonDataset": "other.t",
                "joinKeys": ["id"],
                "comparisonColumns": ["s"],
            },
            "s",
            "t",
        )
        assert r["parameters"]["comparison_dataset"] == "other.t"

    def test_join_keys(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "cross_table",
                "comparisonDataset": "x",
                "joinKeys": ["k1", "k2"],
                "comparisonColumns": ["s"],
            },
            "s",
            "t",
        )
        assert r["parameters"]["join_keys"] == ["k1", "k2"]

    def test_group_by_columns(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "inter_record",
                "groupByColumns": ["cid"],
                "comparisonColumns": ["email"],
            },
            "s",
            "t",
        )
        assert r["parameters"]["group_by_columns"] == ["cid"]

    def test_aggregation_function(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["amt"],
                "consistencyType": "aggregation",
                "aggregationFunction": "SUM",
                "groupByColumns": ["oid"],
                "expectedColumn": "total",
            },
            "s",
            "t",
        )
        assert r["parameters"]["aggregation_function"] == "SUM"

    def test_tolerance_forwarded(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "formula",
                "ruleExpression": "a+b",
                "expectedColumn": "c",
                "toleranceType": "percentage",
                "toleranceValue": 5.0,
            },
            "s",
            "t",
        )
        assert r["parameters"]["tolerance_type"] == "percentage"
        assert r["parameters"]["tolerance_value"] == 5.0

    def test_null_handling(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": "a=b",
                "nullHandling": "skip",
            },
            "s",
            "t",
        )
        assert r["parameters"]["null_handling"] == "skip"

    def test_threshold_warn(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": "a=b",
                "thresholdWarn": 95,
            },
            "s",
            "t",
        )
        assert r["parameters"]["threshold_warn"] == 95

    def test_filter_expression(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": "a=b",
                "filterExpression": "status = 'active'",
            },
            "s",
            "t",
        )
        assert r["parameters"]["filter_expression"] == "status = 'active'"

    def test_operator(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "consistencyType": "temporal",
                "comparisonColumn": "b",
                "operator": ">",
            },
            "s",
            "t",
        )
        assert r["parameters"]["operator"] == ">"


# ── Mapping: Backward Compat ────────────────────────────────────


class TestMappingBackwardCompat:
    def test_reference_column_builds_expression(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["price"],
                "referenceColumn": "expected_price",
            },
            "s",
            "t",
        )
        assert "rule_expression" in r["parameters"]
        assert "price" in r["parameters"]["rule_expression"]
        assert "expected_price" in r["parameters"]["rule_expression"]

    def test_reference_column_with_operator(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "referenceColumn": "b",
                "operator": ">=",
            },
            "s",
            "t",
        )
        assert ">=" in r["parameters"]["rule_expression"]

    def test_dimension_is_consistency(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["a"],
                "ruleExpression": "a=b",
            },
            "s",
            "t",
        )
        assert r["dimension"] == "consistency"

    def test_entity_format(self, handler):
        r = handler._build_canonical_rule(
            "consistency",
            {
                "columns": ["price"],
                "ruleExpression": "a=b",
            },
            "s",
            "t",
        )
        assert r["entity"] == "t.price"


# ── Parsing ─────────────────────────────────────────────────────


class TestParsing:
    def test_pass(self, handler):
        rows = [{"total_rows": 100, "consistent_rows": 100, "inconsistent_rows": 0}]
        rule = {"parameters": {"consistency_type": "intra_record", "threshold_pass": 95}}
        r = handler._parse_consistency_results(rows, rule)
        assert r["check_status"] == "PASS"
        assert r["rows_passed"] == 100

    def test_fail(self, handler):
        rows = [{"total_rows": 100, "consistent_rows": 80, "inconsistent_rows": 20}]
        rule = {"parameters": {"consistency_type": "formula", "threshold_pass": 95}}
        r = handler._parse_consistency_results(rows, rule)
        assert r["check_status"] == "FAIL"

    def test_warn(self, handler):
        rows = [{"total_rows": 100, "consistent_rows": 92, "inconsistent_rows": 8}]
        rule = {
            "parameters": {
                "consistency_type": "temporal",
                "threshold_pass": 95,
                "threshold_warn": 90,
            }
        }
        r = handler._parse_consistency_results(rows, rule)
        assert r["check_status"] == "WARN"

    def test_consistency_type_in_result(self, handler):
        rows = [{"total_rows": 10, "consistent_rows": 10, "inconsistent_rows": 0}]
        rule = {"parameters": {"consistency_type": "cross_table", "threshold_pass": 100}}
        r = handler._parse_consistency_results(rows, rule)
        assert r["consistency_type"] == "cross_table"

    def test_consistency_rate(self, handler):
        rows = [{"total_rows": 200, "consistent_rows": 190, "inconsistent_rows": 10}]
        rule = {"parameters": {"consistency_type": "aggregation", "threshold_pass": 90}}
        r = handler._parse_consistency_results(rows, rule)
        assert r["consistency_rate"] == Decimal(190) / Decimal(200) * Decimal(100)

    def test_zero_rows(self, handler):
        rows = [{"total_rows": 0, "consistent_rows": 0, "inconsistent_rows": 0}]
        rule = {"parameters": {"consistency_type": "intra_record", "threshold_pass": 100}}
        r = handler._parse_consistency_results(rows, rule)
        assert r["zero_rows"] is True
        assert r["check_status"] == "PASS"

    def test_decimal_type(self, handler):
        rows = [{"total_rows": 3, "consistent_rows": 2, "inconsistent_rows": 1}]
        rule = {"parameters": {"consistency_type": "formula", "threshold_pass": 50}}
        r = handler._parse_consistency_results(rows, rule)
        assert isinstance(r["pass_rate"], Decimal)
        assert isinstance(r["consistency_rate"], Decimal)
