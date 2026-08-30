"""
P01 — Normalizer Infrastructure & Constants

Tests for DIMENSION_SUBTYPE_KEY, DIMENSION_RATE_NAMES, basic
normalize_summary() and normalize_violations() structure.
"""

import sys
import types
import uuid
from unittest.mock import MagicMock

import pytest

# Stub pyspark (app.services.execution.__init__ imports SparkSessionManager)
for _mod in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# Stub only the spark sub-modules with class attributes — do NOT stub the parent package
_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

from app.services.execution.result_normalizer import (
    DIMENSION_RATE_NAMES,
    DIMENSION_SUBTYPE_KEY,
    normalize_summary,
    normalize_violations,
)

ALL_DIMS = [
    "completeness",
    "validity",
    "uniqueness",
    "conformity",
    "consistency",
    "timeliness",
    "accuracy",
    "reconciliation",
]

REQUIRED_SUMMARY_KEYS = {
    "execution_id",
    "rule_id",
    "dimension",
    "dimension_subtype",
    "dataset_name",
    "total_rows",
    "passed_rows",
    "failed_rows",
    "skipped_rows",
    "pass_rate",
    "threshold_pass",
    "threshold_warn",
    "check_status",
    "score",
    "execution_timestamp",
    "execution_duration_ms",
    "summary_metadata",
}

REQUIRED_VIOLATION_KEYS = {
    "result_id",
    "execution_id",
    "rule_id",
    "dimension",
    "dimension_subtype",
    "dataset_name",
    "column_name",
    "business_key",
    "check_status",
    "observed_value",
    "expected_value",
    "deviation",
    "issue_reason",
    "severity",
    "execution_timestamp",
    "metadata",
}


def _make_rule(dimension, subtype_value="test_sub", **extra_params):
    subtype_key = DIMENSION_SUBTYPE_KEY.get(dimension, "check_mode")
    params = {subtype_key: subtype_value, **extra_params}
    return {
        "dimension": dimension,
        "rule_id": "rule-001",
        "target_table": "public.orders",
        "severity": "high",
        "parameters": params,
    }


def _make_result(**overrides):
    base = {
        "rows_scanned": 1000,
        "rows_passed": 950,
        "rows_failed": 50,
        "pass_rate": 95.0,
        "check_status": "PASS",
    }
    base.update(overrides)
    return base


# ── Constants ──────────────────────────────────────────────────────


class TestDimensionSubtypeKey:
    def test_has_all_8_dimensions(self):
        assert len(DIMENSION_SUBTYPE_KEY) == 8
        for d in ALL_DIMS:
            assert d in DIMENSION_SUBTYPE_KEY

    def test_completeness_key(self):
        assert DIMENSION_SUBTYPE_KEY["completeness"] == "check_mode"

    def test_validity_key(self):
        assert DIMENSION_SUBTYPE_KEY["validity"] == "validation_type"

    def test_uniqueness_key(self):
        assert DIMENSION_SUBTYPE_KEY["uniqueness"] == "uniqueness_mode"

    def test_conformity_key(self):
        assert DIMENSION_SUBTYPE_KEY["conformity"] == "conformity_type"

    def test_consistency_key(self):
        assert DIMENSION_SUBTYPE_KEY["consistency"] == "consistency_type"

    def test_timeliness_key(self):
        assert DIMENSION_SUBTYPE_KEY["timeliness"] == "timeliness_type"

    def test_accuracy_key(self):
        assert DIMENSION_SUBTYPE_KEY["accuracy"] == "accuracy_type"

    def test_reconciliation_key(self):
        assert DIMENSION_SUBTYPE_KEY["reconciliation"] == "reconciliation_type"


class TestDimensionRateNames:
    def test_has_all_8_dimensions(self):
        assert len(DIMENSION_RATE_NAMES) == 8
        for d in ALL_DIMS:
            assert d in DIMENSION_RATE_NAMES


# ── normalize_summary basics ──────────────────────────────────────


class TestNormalizeSummaryBasics:
    def test_returns_dict(self):
        result = normalize_summary(_make_result(), _make_rule("completeness"))
        assert isinstance(result, dict)

    def test_has_all_required_keys(self):
        result = normalize_summary(_make_result(), _make_rule("completeness"))
        assert REQUIRED_SUMMARY_KEYS.issubset(result.keys())

    def test_dimension_field_correct(self):
        result = normalize_summary(_make_result(), _make_rule("validity"))
        assert result["dimension"] == "validity"

    @pytest.mark.parametrize("dim", ALL_DIMS)
    def test_subtype_extraction(self, dim):
        rule = _make_rule(dim, subtype_value="my_subtype")
        result = normalize_summary(_make_result(), rule)
        assert result["dimension_subtype"] == "my_subtype"

    def test_missing_params_unknown_subtype(self):
        rule = {"dimension": "completeness", "parameters": {}, "target_table": "t"}
        result = normalize_summary(_make_result(), rule)
        assert result["dimension_subtype"] == "unknown"

    def test_execution_context_propagated(self):
        ctx = {"execution_id": "exec-123", "execution_timestamp": "2026-04-03T00:00:00Z"}
        result = normalize_summary(_make_result(), _make_rule("completeness"), ctx)
        assert result["execution_id"] == "exec-123"
        assert result["execution_timestamp"] == "2026-04-03T00:00:00Z"

    def test_no_context_none_fields(self):
        result = normalize_summary(_make_result(), _make_rule("completeness"))
        assert result["execution_id"] is None
        assert result["execution_timestamp"] is None


# ── normalize_violations basics ───────────────────────────────────


class TestNormalizeViolationsBasics:
    def test_returns_list(self):
        result = normalize_violations([], _make_rule("completeness"))
        assert isinstance(result, list)

    def test_empty_input_empty_output(self):
        result = normalize_violations([], _make_rule("completeness"))
        assert len(result) == 0

    def test_single_violation_one_item(self):
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, _make_rule("completeness"))
        assert len(result) == 1
        assert REQUIRED_VIOLATION_KEYS.issubset(result[0].keys())

    def test_result_id_is_uuid(self):
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, _make_rule("completeness"))
        # Should not raise
        uuid.UUID(result[0]["result_id"])

    def test_result_ids_unique(self):
        violations = [{"row_identifier": "id=1"}, {"row_identifier": "id=2"}]
        result = normalize_violations(violations, _make_rule("completeness"))
        ids = [r["result_id"] for r in result]
        assert len(set(ids)) == 2

    def test_dimension_propagated(self):
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, _make_rule("accuracy", "reference_comparison"))
        assert result[0]["dimension"] == "accuracy"
        assert result[0]["dimension_subtype"] == "reference_comparison"

    def test_severity_propagated(self):
        rule = _make_rule("completeness")
        rule["severity"] = "critical"
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, rule)
        assert result[0]["severity"] == "critical"

    def test_check_status_always_fail(self):
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, _make_rule("completeness"))
        assert result[0]["check_status"] == "FAIL"

    def test_column_name_from_params(self):
        rule = _make_rule("completeness", columns=["email"])
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, rule)
        assert result[0]["column_name"] == "email"

    def test_column_name_none_when_no_columns(self):
        rule = _make_rule("completeness")
        violations = [{"row_identifier": "id=1"}]
        result = normalize_violations(violations, rule)
        assert result[0]["column_name"] is None

    def test_business_key_extracted(self):
        violations = [{"row_identifier": "customer_id=42"}]
        result = normalize_violations(violations, _make_rule("completeness"))
        assert result[0]["business_key"] == "customer_id=42"
