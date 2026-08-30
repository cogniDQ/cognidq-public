"""P06 — Accuracy Integration Tests (E2E compile+parse per type, error paths, Spark, WARN, filter, null)."""

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
def compiler():
    return RuleCompiler()


@pytest.fixture
def handler():
    h = CheckNodeHandler.__new__(CheckNodeHandler)
    h.db = MagicMock()
    h.rule_service = MagicMock()
    return h


def _compile(compiler, column, params):
    """Compile an accuracy rule using the canonical dict pattern."""
    return compiler.compile_rule(
        {
            "dimension": "accuracy",
            "entity": f"t.{column}",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="t",
    )


def _e2e(compiler, handler, column, params, simulated_row):
    """End-to-end: compile → simulate row → parse."""
    compiled = _compile(compiler, column, params)
    canonical = {"dimension": "accuracy", "parameters": params}
    result = handler._parse_accuracy_results([simulated_row], canonical)
    return compiled, result


# ── E2E Per Type ─────────────────────────────────────────────


class TestEndToEndReferenceComparison:
    def test_pass(self, compiler, handler):
        params = {
            "accuracy_type": "reference_comparison",
            "reference_dataset": "master.products",
            "reference_column": "ref_price",
            "join_keys": ["product_id"],
            "threshold_pass": 95,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 90,
            "unverifiable_rows": 10,
            "accurate_rows": 88,
            "inaccurate_rows": 2,
        }
        compiled, result = _e2e(compiler, handler, "price", params, row)
        assert "LEFT JOIN" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"
        assert result["verified_rows"] == 90

    def test_fail(self, compiler, handler):
        params = {
            "accuracy_type": "reference_comparison",
            "reference_dataset": "ref",
            "reference_column": "rc",
            "join_keys": ["id"],
            "threshold_pass": 95,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 80,
            "inaccurate_rows": 20,
        }
        _, result = _e2e(compiler, handler, "col", params, row)
        assert result["check_status"] == "FAIL"


class TestEndToEndTrustedSource:
    def test_pass(self, compiler, handler):
        params = {
            "accuracy_type": "trusted_source",
            "reference_dataset": "verified",
            "reference_column": "v_email",
            "join_keys": ["cust_id"],
            "threshold_pass": 90,
        }
        row = {
            "total_rows": 50,
            "verified_rows": 50,
            "unverifiable_rows": 0,
            "accurate_rows": 48,
            "inaccurate_rows": 2,
        }
        compiled, result = _e2e(compiler, handler, "email", params, row)
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {
            "accuracy_type": "trusted_source",
            "reference_dataset": "verified",
            "reference_column": "v_email",
            "join_keys": ["cust_id"],
            "threshold_pass": 99,
        }
        row = {
            "total_rows": 50,
            "verified_rows": 50,
            "unverifiable_rows": 0,
            "accurate_rows": 48,
            "inaccurate_rows": 2,
        }
        _, result = _e2e(compiler, handler, "email", params, row)
        assert result["check_status"] == "FAIL"


class TestEndToEndToleratedDeviation:
    def test_absolute_pass(self, compiler, handler):
        params = {
            "accuracy_type": "tolerated_deviation",
            "reference_dataset": "ref_geo",
            "reference_column": "ref_lat",
            "join_keys": ["store_id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.001,
            "threshold_pass": 90,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 95,
            "unverifiable_rows": 5,
            "accurate_rows": 92,
            "inaccurate_rows": 3,
        }
        compiled, result = _e2e(compiler, handler, "lat", params, row)
        assert "ABS" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_percentage_fail(self, compiler, handler):
        params = {
            "accuracy_type": "tolerated_deviation",
            "reference_dataset": "ref",
            "reference_column": "rp",
            "join_keys": ["id"],
            "tolerance_type": "percentage",
            "tolerance_value": 1.0,
            "threshold_pass": 99,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 95,
            "inaccurate_rows": 5,
        }
        _, result = _e2e(compiler, handler, "price", params, row)
        assert result["check_status"] == "FAIL"


class TestEndToEndStatisticalZscore:
    def test_pass(self, compiler, handler):
        params = {
            "accuracy_type": "statistical",
            "statistical_method": "zscore",
            "threshold_pass": 90,
        }
        row = {
            "total_rows": 1000,
            "verified_rows": 1000,
            "unverifiable_rows": 0,
            "accurate_rows": 970,
            "inaccurate_rows": 30,
        }
        compiled, result = _e2e(compiler, handler, "salary", params, row)
        assert "AVG" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {
            "accuracy_type": "statistical",
            "statistical_method": "zscore",
            "threshold_pass": 99,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 90,
            "inaccurate_rows": 10,
        }
        _, result = _e2e(compiler, handler, "salary", params, row)
        assert result["check_status"] == "FAIL"


class TestEndToEndStatisticalIqr:
    def test_pass(self, compiler, handler):
        params = {
            "accuracy_type": "statistical",
            "statistical_method": "iqr",
            "threshold_pass": 90,
        }
        row = {
            "total_rows": 500,
            "verified_rows": 500,
            "unverifiable_rows": 0,
            "accurate_rows": 480,
            "inaccurate_rows": 20,
        }
        compiled, result = _e2e(compiler, handler, "amount", params, row)
        assert "percentile_cont" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {
            "accuracy_type": "statistical",
            "statistical_method": "iqr",
            "threshold_pass": 98,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 90,
            "inaccurate_rows": 10,
        }
        _, result = _e2e(compiler, handler, "amount", params, row)
        assert result["check_status"] == "FAIL"


class TestEndToEndDerivedValue:
    def test_pass(self, compiler, handler):
        params = {
            "accuracy_type": "derived_value",
            "formula": '"quantity" * "unit_price"',
            "threshold_pass": 95,
        }
        row = {
            "total_rows": 200,
            "verified_rows": 200,
            "unverifiable_rows": 0,
            "accurate_rows": 198,
            "inaccurate_rows": 2,
        }
        compiled, result = _e2e(compiler, handler, "total", params, row)
        assert "quantity" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {
            "accuracy_type": "derived_value",
            "formula": '"a" + "b"',
            "threshold_pass": 99,
        }
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 90,
            "inaccurate_rows": 10,
        }
        _, result = _e2e(compiler, handler, "sum", params, row)
        assert result["check_status"] == "FAIL"


# ── Error Paths ──────────────────────────────────────────────


class TestErrorPaths:
    def test_unknown_type(self, compiler):
        result = _compile(compiler, "c", {"accuracy_type": "external_api", "threshold_pass": 95})
        assert "error" in result

    def test_missing_reference_dataset(self, compiler):
        result = _compile(
            compiler,
            "c",
            {"accuracy_type": "reference_comparison", "join_keys": ["id"], "threshold_pass": 95},
        )
        assert "error" in result

    def test_missing_join_keys(self, compiler):
        result = _compile(
            compiler,
            "c",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "threshold_pass": 95,
            },
        )
        assert "error" in result

    def test_missing_formula(self, compiler):
        result = _compile(compiler, "c", {"accuracy_type": "derived_value", "threshold_pass": 95})
        assert "error" in result

    def test_invalid_statistical_method(self, compiler):
        result = _compile(
            compiler,
            "c",
            {"accuracy_type": "statistical", "statistical_method": "nope", "threshold_pass": 95},
        )
        assert "error" in result

    def test_dangerous_filter(self, compiler):
        result = _compile(
            compiler,
            "c",
            {
                "accuracy_type": "statistical",
                "statistical_method": "zscore",
                "threshold_pass": 95,
                "filter_expression": "x; DROP TABLE y",
            },
        )
        assert "error" in result

    def test_dangerous_formula(self, compiler):
        result = _compile(
            compiler,
            "c",
            {"accuracy_type": "derived_value", "formula": "1; DROP TABLE x", "threshold_pass": 95},
        )
        assert "error" in result

    def test_tolerated_deviation_missing_tolerance(self, compiler):
        result = _compile(
            compiler,
            "c",
            {
                "accuracy_type": "tolerated_deviation",
                "reference_dataset": "ref",
                "join_keys": ["id"],
                "tolerance_type": "none",
                "threshold_pass": 95,
            },
        )
        assert "error" in result


# ── Spark Output ─────────────────────────────────────────────


class TestSparkOutput:
    def _spark(self, compiler, accuracy_type, extra=None):
        params = {"accuracy_type": accuracy_type, "threshold_pass": 95}
        if extra:
            params.update(extra)
        return _compile(compiler, "c", params)

    def test_reference_spark(self, compiler):
        result = self._spark(
            compiler,
            "reference_comparison",
            {"reference_dataset": "ref", "reference_column": "rc", "join_keys": ["id"]},
        )
        assert "pyspark" in result["compiled_spark"]
        assert "join" in result["compiled_spark"]

    def test_trusted_source_spark(self, compiler):
        result = self._spark(
            compiler,
            "trusted_source",
            {"reference_dataset": "ref", "reference_column": "rc", "join_keys": ["id"]},
        )
        assert "left" in result["compiled_spark"]

    def test_tolerated_deviation_spark(self, compiler):
        result = self._spark(
            compiler,
            "tolerated_deviation",
            {
                "reference_dataset": "ref",
                "reference_column": "rc",
                "join_keys": ["id"],
                "tolerance_type": "absolute",
                "tolerance_value": 0.1,
            },
        )
        assert "pyspark" in result["compiled_spark"]

    def test_zscore_spark(self, compiler):
        result = self._spark(compiler, "statistical", {"statistical_method": "zscore"})
        assert "avg" in result["compiled_spark"]
        assert "stddev" in result["compiled_spark"]

    def test_iqr_spark(self, compiler):
        result = self._spark(compiler, "statistical", {"statistical_method": "iqr"})
        assert "percentile_approx" in result["compiled_spark"]

    def test_derived_value_spark(self, compiler):
        result = self._spark(compiler, "derived_value", {"formula": '"a" * "b"'})
        assert "pyspark" in result["compiled_spark"]


# ── WARN Threshold ───────────────────────────────────────────


class TestWarnThreshold:
    def test_warn_between_thresholds(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 92,
            "inaccurate_rows": 8,
        }
        canonical = {
            "parameters": {
                "accuracy_type": "reference_comparison",
                "threshold_pass": 95,
                "threshold_warn": 90,
            }
        }
        result = handler._parse_accuracy_results([row], canonical)
        assert result["check_status"] == "WARN"

    def test_below_warn_is_fail(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 85,
            "inaccurate_rows": 15,
        }
        canonical = {
            "parameters": {
                "accuracy_type": "reference_comparison",
                "threshold_pass": 95,
                "threshold_warn": 90,
            }
        }
        result = handler._parse_accuracy_results([row], canonical)
        assert result["check_status"] == "FAIL"

    def test_above_pass_is_pass(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 100,
            "unverifiable_rows": 0,
            "accurate_rows": 96,
            "inaccurate_rows": 4,
        }
        canonical = {
            "parameters": {
                "accuracy_type": "reference_comparison",
                "threshold_pass": 95,
                "threshold_warn": 90,
            }
        }
        result = handler._parse_accuracy_results([row], canonical)
        assert result["check_status"] == "PASS"


# ── Filter Expression ────────────────────────────────────────


class TestFilterExpression:
    def test_filter_in_reference_sql(self, compiler):
        result = _compile(
            compiler,
            "c",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "reference_column": "rc",
                "join_keys": ["id"],
                "threshold_pass": 95,
                "filter_expression": "region = 'US'",
            },
        )
        assert "region = 'US'" in result["compiled_sql"]


# ── Null Handling ────────────────────────────────────────────


class TestNullHandling:
    def test_skip_in_reference(self, compiler):
        result = _compile(
            compiler,
            "price",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "reference_column": "rp",
                "join_keys": ["id"],
                "threshold_pass": 95,
                "null_handling": "skip",
            },
        )
        assert '"price" IS NOT NULL' in result["compiled_sql"]

    def test_pass_in_derived(self, compiler):
        result = _compile(
            compiler,
            "total",
            {
                "accuracy_type": "derived_value",
                "formula": '"qty" * "price"',
                "threshold_pass": 95,
                "null_handling": "pass",
            },
        )
        assert '"total" IS NULL OR' in result["compiled_sql"]

    def test_skip_in_statistical(self, compiler):
        result = _compile(
            compiler,
            "salary",
            {
                "accuracy_type": "statistical",
                "statistical_method": "zscore",
                "threshold_pass": 95,
                "null_handling": "skip",
            },
        )
        assert '"salary" IS NOT NULL' in result["compiled_sql"]


# ── Tolerance Modes ──────────────────────────────────────────


class TestToleranceModes:
    def test_none_exact_match(self, compiler):
        result = _compile(
            compiler,
            "c",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "reference_column": "rc",
                "join_keys": ["id"],
                "threshold_pass": 95,
                "tolerance_type": "none",
            },
        )
        sql = result["compiled_sql"]
        assert '(a."c") = (b."rc")' in sql

    def test_absolute_tolerance(self, compiler):
        result = _compile(
            compiler,
            "price",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "reference_column": "rp",
                "join_keys": ["id"],
                "threshold_pass": 95,
                "tolerance_type": "absolute",
                "tolerance_value": 0.5,
            },
        )
        assert "ABS" in result["compiled_sql"]
        assert "<= 0.5" in result["compiled_sql"]

    def test_percentage_tolerance(self, compiler):
        result = _compile(
            compiler,
            "price",
            {
                "accuracy_type": "reference_comparison",
                "reference_dataset": "ref",
                "reference_column": "rp",
                "join_keys": ["id"],
                "threshold_pass": 95,
                "tolerance_type": "percentage",
                "tolerance_value": 5.0,
            },
        )
        assert "NULLIF" in result["compiled_sql"]
        assert "<= 5.0" in result["compiled_sql"]


# ── Result Structure ─────────────────────────────────────────


class TestResultStructure:
    def test_all_fields_present(self, handler):
        row = {
            "total_rows": 100,
            "verified_rows": 90,
            "unverifiable_rows": 10,
            "accurate_rows": 85,
            "inaccurate_rows": 5,
        }
        canonical = {"parameters": {"accuracy_type": "reference_comparison", "threshold_pass": 95}}
        result = handler._parse_accuracy_results([row], canonical)
        for key in (
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "pass_rate",
            "accuracy_rate",
            "check_status",
            "accuracy_type",
            "verified_rows",
            "unverifiable_rows",
            "zero_rows",
            "violations",
        ):
            assert key in result, f"Missing key: {key}"

    def test_unverifiable_excluded_from_rate(self, handler):
        """accuracy_rate = accurate / verified, not accurate / total."""
        row = {
            "total_rows": 100,
            "verified_rows": 50,
            "unverifiable_rows": 50,
            "accurate_rows": 50,
            "inaccurate_rows": 0,
        }
        canonical = {"parameters": {"accuracy_type": "reference_comparison", "threshold_pass": 95}}
        result = handler._parse_accuracy_results([row], canonical)
        assert result["accuracy_rate"] == Decimal(100)
        assert result["check_status"] == "PASS"
