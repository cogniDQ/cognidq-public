"""P07 — Reconciliation Integration Tests (E2E compile+parse, error paths, Spark, WARN)."""

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


BASE = {"source_dataset": "src", "target_dataset": "tgt", "threshold_pass": 95}


def _compile(compiler, params):
    return compiler.compile_rule(
        {
            "dimension": "reconciliation",
            "entity": "src",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="src",
    )


def _e2e(compiler, handler, params, simulated_row):
    compiled = _compile(compiler, params)
    canonical = {"dimension": "reconciliation", "parameters": params}
    result = handler._parse_reconciliation_results([simulated_row], canonical)
    return compiled, result


# ── E2E Per Type ─────────────────────────────────────────────


class TestE2ERecordCount:
    def test_pass(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "record_count"}
        row = {"source_count": 1000, "target_count": 1000}
        compiled, result = _e2e(compiler, handler, params, row)
        assert "COUNT" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "record_count"}
        row = {"source_count": 1000, "target_count": 800}
        _, result = _e2e(compiler, handler, params, row)
        assert result["check_status"] == "FAIL"


class TestE2EOneToOne:
    def test_pass(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        compiled, result = _e2e(compiler, handler, params, row)
        assert "FULL OUTER JOIN" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "one_to_one", "join_keys": ["id"]}
        row = {
            "source_count": 100,
            "target_count": 80,
            "matched_count": 80,
            "missing_in_target": 20,
            "extra_in_target": 0,
        }
        _, result = _e2e(compiler, handler, params, row)
        assert result["check_status"] == "FAIL"


class TestE2EAggregate:
    def test_pass(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "source_agg": 50000,
            "target_agg": 50000,
        }
        compiled, result = _e2e(compiler, handler, params, row)
        assert "SUM" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"

    def test_fail(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "aggregate", "aggregate_column": "amount"}
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "source_agg": 50000,
            "target_agg": 40000,
        }
        _, result = _e2e(compiler, handler, params, row)
        assert result["check_status"] == "FAIL"


class TestE2EFieldLevel:
    def test_pass(self, compiler, handler):
        params = {
            **BASE,
            "reconciliation_type": "field_level",
            "join_keys": ["id"],
            "compare_columns": ["name"],
        }
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "field_match_count": 98,
            "field_mismatch_count": 2,
        }
        compiled, result = _e2e(compiler, handler, params, row)
        assert "INNER JOIN" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"


class TestE2ETolerance:
    def test_pass(self, compiler, handler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        row = {
            "source_count": 0,
            "target_count": 0,
            "matched_count": 200,
            "missing_in_target": 0,
            "extra_in_target": 0,
            "within_tolerance": 198,
            "outside_tolerance": 2,
        }
        compiled, result = _e2e(compiler, handler, params, row)
        assert "ABS" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"


class TestE2EMissingExtra:
    def test_pass(self, compiler, handler):
        params = {**BASE, "reconciliation_type": "missing_extra", "join_keys": ["id"]}
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 100,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        compiled, result = _e2e(compiler, handler, params, row)
        assert "LEFT JOIN" in compiled["compiled_sql"]
        assert result["check_status"] == "PASS"


# ── Error Paths ──────────────────────────────────────────────


class TestErrorPaths:
    def test_unknown_type(self, compiler):
        result = _compile(compiler, {**BASE, "reconciliation_type": "temporal"})
        assert "error" in result

    def test_missing_source_dataset(self, compiler):
        result = _compile(
            compiler,
            {"reconciliation_type": "record_count", "target_dataset": "t", "threshold_pass": 100},
        )
        assert "error" in result

    def test_missing_join_keys_one_to_one(self, compiler):
        result = _compile(compiler, {**BASE, "reconciliation_type": "one_to_one"})
        assert "error" in result

    def test_missing_aggregate_column(self, compiler):
        result = _compile(compiler, {**BASE, "reconciliation_type": "aggregate"})
        assert "error" in result

    def test_dangerous_filter(self, compiler):
        result = _compile(
            compiler,
            {**BASE, "reconciliation_type": "record_count", "source_filter": "1; DROP TABLE x"},
        )
        assert "error" in result


# ── Spark Output ─────────────────────────────────────────────


class TestSparkOutput:
    @pytest.mark.parametrize(
        "rtype,extra",
        [
            ("record_count", {}),
            ("one_to_one", {"join_keys": ["id"]}),
            ("aggregate", {"aggregate_column": "amt"}),
            ("field_level", {"join_keys": ["id"], "compare_columns": ["name"]}),
            (
                "tolerance",
                {"join_keys": ["id"], "tolerance_type": "absolute", "tolerance_value": 1},
            ),
            ("missing_extra", {"join_keys": ["id"]}),
        ],
    )
    def test_spark_generated(self, compiler, rtype, extra):
        params = {**BASE, "reconciliation_type": rtype, **extra}
        result = _compile(compiler, params)
        assert result["compiled_spark"]
        assert "error" not in result


# ── WARN Threshold ───────────────────────────────────────────


class TestWarnThreshold:
    def test_warn_between(self, handler):
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

    def test_below_warn_is_fail(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 90,
            "missing_in_target": 10,
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
        assert result["check_status"] == "FAIL"

    def test_above_pass_is_pass(self, handler):
        row = {
            "source_count": 100,
            "target_count": 100,
            "matched_count": 100,
            "missing_in_target": 0,
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
        assert result["check_status"] == "PASS"
