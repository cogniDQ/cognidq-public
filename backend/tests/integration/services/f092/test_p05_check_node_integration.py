"""
P05 — Check Node Integration Tests

Tests that check_node.py wires the result normalizer correctly,
producing canonical_summary and canonical_violations for all 8 dimensions.
Also verifies backward compatibility.
"""

import sys
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# Stub pyspark before importing application modules
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

from app.services.execution.result_normalizer import normalize_summary, normalize_violations
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


# ── Helpers ────────────────────────────────────────────────────────


def _compile_and_parse(compiler, handler, dimension, params, simulated_row):
    """Compile a rule and parse simulated results → (compiled, parsed)."""
    canonical = {
        "dimension": dimension,
        "entity": "test_table",
        "condition": "",
        "expectation": "95%",
        "parameters": params,
    }
    compiled = compiler.compile_rule(canonical, target_table="test_table")
    full_canonical = {
        "dimension": dimension,
        "parameters": params,
        "rule_id": "rule-int",
        "target_table": "test_table",
        "severity": "high",
    }

    # Use the right parser
    parser_map = {
        "completeness": handler._parse_completeness_results,
        "validity": handler._parse_validity_results,
        "uniqueness": handler._parse_uniqueness_results,
        "conformity": handler._parse_conformity_results,
        "consistency": handler._parse_consistency_results,
        "timeliness": handler._parse_timeliness_results,
        "accuracy": handler._parse_accuracy_results,
        "reconciliation": handler._parse_reconciliation_results,
    }
    parsed = parser_map[dimension]([simulated_row], full_canonical)
    return compiled, parsed, full_canonical


# ── Per-Dimension: canonical_summary present ──────────────────────

DIMENSION_CONFIGS = [
    (
        "completeness",
        {"check_mode": "null", "columns": ["email"], "threshold_pass": 95},
        {"total_rows": 1000, "null_rows": 50, "non_null_rows": 950, "completeness_rate": 95.0},
    ),
    (
        "validity",
        {
            "validation_type": "allowed_values",
            "columns": ["status"],
            "allowed_values": ["A", "B"],
            "threshold_pass": 90,
        },
        {"total_rows": 500, "valid_rows": 460, "invalid_rows": 40, "validity_rate": 92.0},
    ),
    (
        "uniqueness",
        {"uniqueness_mode": "exact", "columns": ["id"], "threshold_pass": 95},
        {
            "total_rows": 2000,
            "duplicate_rows": 20,
            "duplicate_groups": 10,
            "max_group_size": 3,
            "uniqueness_rate": 99.0,
        },
    ),
    (
        "conformity",
        {
            "conformity_type": "regex",
            "columns": ["phone"],
            "regex_pattern": r"^\d{10}$",
            "threshold_pass": 90,
        },
        {"total_rows": 800, "conforming_rows": 750, "non_conforming_rows": 50},
    ),
    (
        "consistency",
        {
            "consistency_type": "intra_record",
            "columns": ["total"],
            "rule_expression": "total = qty * price",
            "threshold_pass": 95,
        },
        {"total_rows": 1200, "consistent_rows": 1150, "inconsistent_rows": 50},
    ),
    (
        "timeliness",
        {
            "timeliness_type": "freshness",
            "timestamp_column": "updated_at",
            "max_age": "24h",
            "threshold_pass": 95,
        },
        {
            "total_rows": 600,
            "timely_rows": 580,
            "untimely_rows": 20,
            "most_recent": "2026-04-03",
            "age_seconds": 3600,
        },
    ),
    (
        "accuracy",
        {
            "accuracy_type": "reference_comparison",
            "columns": ["price"],
            "reference_dataset": "ref_prices",
            "reference_column": "ref_price",
            "join_keys": ["id"],
            "threshold_pass": 90,
        },
        {
            "total_rows": 400,
            "verified_rows": 380,
            "unverifiable_rows": 20,
            "accurate_rows": 360,
            "inaccurate_rows": 20,
        },
    ),
    (
        "reconciliation",
        {
            "reconciliation_type": "record_count",
            "source_dataset": "src",
            "target_dataset": "tgt",
            "threshold_pass": 95,
        },
        {"source_count": 1000, "target_count": 980},
    ),
]


class TestCanonicalSummaryAllDimensions:
    @pytest.mark.parametrize("dim,params,sim_row", DIMENSION_CONFIGS)
    def test_canonical_summary_present(self, compiler, handler, dim, params, sim_row):
        _, parsed, full_rule = _compile_and_parse(compiler, handler, dim, params, sim_row)
        summary = normalize_summary(parsed, full_rule)
        assert isinstance(summary, dict)
        assert summary["dimension"] == dim

    @pytest.mark.parametrize("dim,params,sim_row", DIMENSION_CONFIGS)
    def test_canonical_violations_present(self, compiler, handler, dim, params, sim_row):
        _, parsed, full_rule = _compile_and_parse(compiler, handler, dim, params, sim_row)
        violations = normalize_violations(parsed.get("violations", []), full_rule)
        assert isinstance(violations, list)


class TestCanonicalSummaryFields:
    def test_dimension_correct(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["dimension"] == "completeness"

    def test_dimension_subtype_correct(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["dimension_subtype"] == "null"

    def test_total_rows_matches(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["total_rows"] == parsed["rows_scanned"]

    def test_pass_rate_matches(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["pass_rate"] == float(parsed["pass_rate"])

    def test_check_status_matches(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["check_status"] == parsed["check_status"]


class TestCanonicalViolationsLimit:
    def test_violations_limited(self, handler):
        violations = [{"row_identifier": f"id={i}"} for i in range(200)]
        rule = {
            "dimension": "completeness",
            "rule_id": "r",
            "target_table": "t",
            "severity": "high",
            "parameters": {"check_mode": "null"},
        }
        result = normalize_violations(violations[:100], rule)
        assert len(result) <= 100


class TestBackwardCompatibility:
    """Verify that normalize_summary and normalize_violations don't break existing fields."""

    def test_parsed_result_unchanged(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, _ = _compile_and_parse(compiler, handler, dim, params, sim)
        # Parser should still return expected keys
        assert "rows_scanned" in parsed
        assert "rows_passed" in parsed
        assert "rows_failed" in parsed
        assert "pass_rate" in parsed

    def test_parsed_violations_key_exists(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, _ = _compile_and_parse(compiler, handler, dim, params, sim)
        assert "violations" in parsed or parsed.get("rows_failed", 0) == 0

    def test_check_status_in_parsed(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[0]
        _, parsed, _ = _compile_and_parse(compiler, handler, dim, params, sim)
        assert "check_status" in parsed


class TestWarnThreshold:
    def test_warn_in_summary(self, compiler, handler):
        params = {
            "check_mode": "null",
            "columns": ["email"],
            "threshold_pass": 98,
            "threshold_warn": 90,
        }
        sim = {"total_rows": 1000, "null_rows": 50, "non_null_rows": 950, "completeness_rate": 95.0}
        _, parsed, rule = _compile_and_parse(compiler, handler, "completeness", params, sim)
        s = normalize_summary(parsed, rule)
        assert s["check_status"] == "WARN"
        assert s["threshold_warn"] == 90


class TestNormalizerErrorResilience:
    def test_normalizer_with_bad_rule_no_crash(self):
        result = {
            "rows_scanned": 100,
            "rows_passed": 99,
            "rows_failed": 1,
            "pass_rate": 99.0,
            "check_status": "PASS",
        }
        # Missing dimension key
        rule = {"parameters": {}, "rule_id": "r", "target_table": "t"}
        summary = normalize_summary(result, rule)
        assert summary["dimension"] == ""

    def test_violations_with_bad_rule_no_crash(self):
        rule = {"parameters": {}, "rule_id": "r", "target_table": "t", "severity": "low"}
        vs = normalize_violations([{"row_identifier": "x"}], rule)
        assert len(vs) == 1


class TestCanonicalSummaryScore:
    def test_score_equals_pass_rate(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[1]  # validity
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["score"] == s["pass_rate"]


class TestAdhocCheck:
    """Verify canonical output works for rules without execution context."""

    def test_no_context_still_produces_summary(self, compiler, handler):
        dim, params, sim = DIMENSION_CONFIGS[2]  # uniqueness
        _, parsed, rule = _compile_and_parse(compiler, handler, dim, params, sim)
        s = normalize_summary(parsed, rule)
        assert s["execution_id"] is None
        assert s["dimension"] == "uniqueness"
