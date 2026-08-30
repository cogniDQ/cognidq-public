"""P06 — Integration tests: E2E config → canonical → compiled → parsed."""

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
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

from app.services.flows.node_handlers.check_node import CheckNodeHandler
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


@pytest.fixture
def compiler():
    return RuleCompiler()


def _e2e(handler, compiler, config, schema="s", table="t"):
    """Run full pipeline: config → canonical → compiled → parsed (with mock rows)."""
    canonical = handler._build_canonical_rule("consistency", config, schema, table)
    compiled = compiler.compile_rule(canonical, target_schema=schema, target_table=table)
    return canonical, compiled


# ── E2E Per Type ────────────────────────────────────────────────


class TestEndToEndIntraRecord:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["price"],
                "consistencyType": "intra_record",
                "ruleExpression": "\"country\" = 'US' AND \"currency\" = 'USD'",
            },
        )
        assert "error" not in r
        assert "country" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["price"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a" = "b"',
                "pass_threshold": 90,
            },
        )
        rows = [{"total_rows": 100, "consistent_rows": 95, "inconsistent_rows": 5}]
        result = handler._parse_consistency_results(rows, c)
        assert result["check_status"] == "PASS"
        assert result["consistency_type"] == "intra_record"


class TestEndToEndFormula:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["total"],
                "consistencyType": "formula",
                "ruleExpression": '"subtotal" + "tax"',
                "expectedColumn": "total",
            },
        )
        assert "error" not in r
        assert "subtotal" in r["compiled_sql"]
        assert "total" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["total"],
                "consistencyType": "formula",
                "ruleExpression": '"a" + "b"',
                "expectedColumn": "total",
                "toleranceType": "absolute",
                "toleranceValue": 0.5,
            },
        )
        rows = [{"total_rows": 50, "consistent_rows": 48, "inconsistent_rows": 2}]
        result = handler._parse_consistency_results(rows, c)
        assert result["rows_passed"] == 48


class TestEndToEndTemporal:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["end_date"],
                "consistencyType": "temporal",
                "comparisonColumn": "start_date",
            },
        )
        assert "error" not in r
        assert ">=" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["end_date"],
                "consistencyType": "temporal",
                "comparisonColumn": "start_date",
                "operator": ">",
            },
        )
        rows = [{"total_rows": 200, "consistent_rows": 200, "inconsistent_rows": 0}]
        result = handler._parse_consistency_results(rows, c)
        assert result["check_status"] == "PASS"


class TestEndToEndInterRecord:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["email"],
                "consistencyType": "inter_record",
                "groupByColumns": ["customer_id"],
                "comparisonColumns": ["email"],
            },
        )
        assert "error" not in r
        assert "group_stats" in r["compiled_sql"]
        assert "DISTINCT" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["email"],
                "consistencyType": "inter_record",
                "groupByColumns": ["cid"],
                "comparisonColumns": ["email"],
            },
        )
        rows = [{"total_rows": 500, "consistent_rows": 480, "inconsistent_rows": 20}]
        result = handler._parse_consistency_results(rows, c)
        assert result["consistency_type"] == "inter_record"


class TestEndToEndCrossTable:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["status"],
                "consistencyType": "cross_table",
                "comparisonDataset": "billing.customers",
                "joinKeys": ["customer_id"],
                "comparisonColumns": ["status"],
            },
        )
        assert "error" not in r
        assert "INNER JOIN" in r["compiled_sql"]
        assert "billing.customers" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["status"],
                "consistencyType": "cross_table",
                "comparisonDataset": "b",
                "joinKeys": ["id"],
                "comparisonColumns": ["status"],
            },
        )
        rows = [{"total_rows": 100, "consistent_rows": 90, "inconsistent_rows": 10}]
        result = handler._parse_consistency_results(rows, c)
        assert result["consistency_type"] == "cross_table"


class TestEndToEndAggregation:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["amount"],
                "consistencyType": "aggregation",
                "groupByColumns": ["order_id"],
                "aggregationFunction": "SUM",
                "expectedColumn": "order_total",
            },
        )
        assert "error" not in r
        assert "SUM" in r["compiled_sql"]
        assert "order_total" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["amount"],
                "consistencyType": "aggregation",
                "groupByColumns": ["oid"],
                "aggregationFunction": "SUM",
                "expectedColumn": "total",
            },
        )
        rows = [{"total_rows": 30, "consistent_rows": 28, "inconsistent_rows": 2}]
        result = handler._parse_consistency_results(rows, c)
        assert result["rows_failed"] == 2


# ── Backward Compat ─────────────────────────────────────────────


class TestBackwardCompat:
    def test_old_reference_column(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["price"],
                "referenceColumn": "expected_price",
            },
        )
        assert "error" not in r
        assert c["parameters"]["consistency_type"] == "intra_record"

    def test_old_reference_column_with_operator(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "referenceColumn": "b",
                "operator": ">=",
            },
        )
        assert "error" not in r


# ── Error Paths ─────────────────────────────────────────────────


class TestErrorPaths:
    def test_unknown_type(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "bogus",
            },
        )
        assert "error" in r

    def test_missing_rule_expression_intra(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
            },
        )
        assert "error" in r

    def test_missing_expected_column_formula(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "formula",
                "ruleExpression": "a + b",
            },
        )
        assert "error" in r

    def test_missing_comparison_column_temporal(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "temporal",
            },
        )
        assert "error" in r

    def test_missing_group_by_inter_record(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "inter_record",
                "comparisonColumns": ["email"],
            },
        )
        assert "error" in r

    def test_missing_comparison_dataset_cross_table(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "cross_table",
                "joinKeys": ["id"],
                "comparisonColumns": ["s"],
            },
        )
        assert "error" in r

    def test_missing_aggregation_function(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "aggregation",
                "groupByColumns": ["g"],
                "expectedColumn": "t",
            },
        )
        assert "error" in r

    def test_dangerous_expression(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": "1; DROP TABLE x",
            },
        )
        assert "error" in r


# ── Spark Output ────────────────────────────────────────────────


class TestSparkOutput:
    @pytest.mark.parametrize(
        "config",
        [
            {"consistencyType": "intra_record", "ruleExpression": '"a" = "b"'},
            {"consistencyType": "formula", "ruleExpression": '"a"+"b"', "expectedColumn": "c"},
            {"consistencyType": "temporal", "comparisonColumn": "end"},
            {
                "consistencyType": "inter_record",
                "groupByColumns": ["g"],
                "comparisonColumns": ["c"],
            },
            {
                "consistencyType": "cross_table",
                "comparisonDataset": "x",
                "joinKeys": ["k"],
                "comparisonColumns": ["c"],
            },
            {
                "consistencyType": "aggregation",
                "groupByColumns": ["g"],
                "aggregationFunction": "SUM",
                "expectedColumn": "t",
            },
        ],
    )
    def test_spark_present(self, handler, compiler, config):
        config["columns"] = ["col"]
        c, r = _e2e(handler, compiler, config)
        assert "compiled_spark" in r
        assert "pyspark" in r["compiled_spark"] or "spark" in r["compiled_spark"].lower()


# ── WARN Threshold ──────────────────────────────────────────────


class TestWarnThreshold:
    def test_pass_above_threshold(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a"="b"',
                "pass_threshold": 90,
                "thresholdWarn": 80,
            },
        )
        rows = [{"total_rows": 100, "consistent_rows": 95, "inconsistent_rows": 5}]
        r = handler._parse_consistency_results(rows, c)
        assert r["check_status"] == "PASS"

    def test_warn_between(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a"="b"',
                "pass_threshold": 95,
                "thresholdWarn": 85,
            },
        )
        rows = [{"total_rows": 100, "consistent_rows": 90, "inconsistent_rows": 10}]
        r = handler._parse_consistency_results(rows, c)
        assert r["check_status"] == "WARN"

    def test_fail_below_warn(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a"="b"',
                "pass_threshold": 95,
                "thresholdWarn": 85,
            },
        )
        rows = [{"total_rows": 100, "consistent_rows": 70, "inconsistent_rows": 30}]
        r = handler._parse_consistency_results(rows, c)
        assert r["check_status"] == "FAIL"


# ── Filter Expression ───────────────────────────────────────────


class TestFilterExpression:
    def test_filter_in_compiled_sql(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "intra_record",
                "ruleExpression": '"a"="b"',
                "filterExpression": "status = 'active'",
            },
        )
        assert "active" in r["compiled_sql"]


# ── Null Handling ───────────────────────────────────────────────


class TestNullHandling:
    def test_skip_default(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "temporal",
                "comparisonColumn": "b",
                "nullHandling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_fail_mode(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "temporal",
                "comparisonColumn": "b",
                "nullHandling": "fail",
            },
        )
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_pass_mode(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "consistencyType": "temporal",
                "comparisonColumn": "b",
                "nullHandling": "pass",
            },
        )
        assert "COALESCE" in r["compiled_sql"]


# ── Tolerance ───────────────────────────────────────────────────


class TestTolerance:
    def test_absolute(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["t"],
                "consistencyType": "formula",
                "ruleExpression": '"a"+"b"',
                "expectedColumn": "t",
                "toleranceType": "absolute",
                "toleranceValue": 0.5,
            },
        )
        assert "0.5" in r["compiled_sql"]

    def test_percentage(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["t"],
                "consistencyType": "formula",
                "ruleExpression": '"a"+"b"',
                "expectedColumn": "t",
                "toleranceType": "percentage",
                "toleranceValue": 2.0,
            },
        )
        assert "NULLIF" in r["compiled_sql"]

    def test_none(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["t"],
                "consistencyType": "formula",
                "ruleExpression": '"a"+"b"',
                "expectedColumn": "t",
                "toleranceType": "none",
            },
        )
        assert "ABS" not in r["compiled_sql"]


# ── Result Structure ────────────────────────────────────────────


class TestResultStructure:
    def test_all_required_fields(self, handler):
        rows = [{"total_rows": 10, "consistent_rows": 8, "inconsistent_rows": 2}]
        rule = {"parameters": {"consistency_type": "formula", "threshold_pass": 90}}
        r = handler._parse_consistency_results(rows, rule)
        for key in [
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "pass_rate",
            "consistency_rate",
            "check_status",
            "consistency_type",
            "zero_rows",
            "violations",
        ]:
            assert key in r

    def test_pass_rate_is_decimal(self, handler):
        rows = [{"total_rows": 3, "consistent_rows": 2, "inconsistent_rows": 1}]
        rule = {"parameters": {"consistency_type": "intra_record", "threshold_pass": 50}}
        r = handler._parse_consistency_results(rows, rule)
        assert isinstance(r["pass_rate"], Decimal)
