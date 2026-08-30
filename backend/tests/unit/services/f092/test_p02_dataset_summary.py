"""
P02 — Dataset Summary Normalization

Tests normalize_summary() with realistic parsed results for all 8 dimensions,
including metric extraction, threshold handling, and edge cases.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# Stub pyspark
for _mod in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

from app.services.execution.result_normalizer import (
    DIMENSION_SUBTYPE_KEY,
    normalize_summary,
)


def _make_rule(dimension, subtype_value=None, **extra_params):
    subtype_key = DIMENSION_SUBTYPE_KEY.get(dimension, "check_mode")
    params = {**extra_params}
    if subtype_value:
        params[subtype_key] = subtype_value
    return {
        "dimension": dimension,
        "rule_id": "rule-002",
        "target_table": "public.customers",
        "severity": "high",
        "parameters": params,
    }


# ── Realistic per-dimension results ───────────────────────────────

COMPLETENESS_RESULT = {
    "rows_scanned": 5000,
    "rows_passed": 4750,
    "rows_failed": 250,
    "pass_rate": 95.0,
    "check_status": "PASS",
    "check_mode": "null",
    "zero_rows": False,
}

VALIDITY_RESULT = {
    "rows_scanned": 3000,
    "rows_passed": 2800,
    "rows_failed": 200,
    "pass_rate": 93.33,
    "check_status": "WARN",
    "validation_type": "regex",
    "skipped_rows": 50,
}

UNIQUENESS_RESULT = {
    "rows_scanned": 10000,
    "rows_passed": 9500,
    "rows_failed": 500,
    "pass_rate": 95.0,
    "check_status": "PASS",
    "uniqueness_mode": "exact",
    "duplicate_groups": 200,
    "max_group_size": 5,
    "avg_group_size": 2.5,
}

CONFORMITY_RESULT = {
    "rows_scanned": 2000,
    "rows_passed": 1900,
    "rows_failed": 100,
    "pass_rate": 95.0,
    "check_status": "PASS",
    "conformity_type": "regex",
}

CONSISTENCY_RESULT = {
    "rows_scanned": 8000,
    "rows_passed": 7800,
    "rows_failed": 200,
    "pass_rate": 97.5,
    "check_status": "PASS",
    "consistency_type": "intra_record",
}

TIMELINESS_RESULT = {
    "rows_scanned": 6000,
    "rows_passed": 5900,
    "rows_failed": 100,
    "pass_rate": 98.33,
    "check_status": "PASS",
    "timeliness_type": "freshness",
    "metadata": {"data_age_seconds": 3600, "most_recent": "2026-04-03T00:00:00Z"},
}

ACCURACY_RESULT = {
    "rows_scanned": 4000,
    "rows_passed": 3800,
    "rows_failed": 200,
    "pass_rate": 95.0,
    "check_status": "PASS",
    "accuracy_type": "reference_comparison",
    "verified_rows": 3900,
    "unverifiable_rows": 100,
}

RECONCILIATION_RESULT = {
    "rows_scanned": 15000,
    "rows_passed": 14000,
    "rows_failed": 1000,
    "pass_rate": 93.33,
    "check_status": "WARN",
    "reconciliation_type": "one_to_one",
    "source_count": 15000,
    "target_count": 14500,
    "matched_count": 14000,
    "missing_in_target": 1000,
    "extra_in_target": 500,
}

ALL_DIMS_RESULTS = [
    ("completeness", "null", COMPLETENESS_RESULT),
    ("validity", "regex", VALIDITY_RESULT),
    ("uniqueness", "exact", UNIQUENESS_RESULT),
    ("conformity", "regex", CONFORMITY_RESULT),
    ("consistency", "intra_record", CONSISTENCY_RESULT),
    ("timeliness", "freshness", TIMELINESS_RESULT),
    ("accuracy", "reference_comparison", ACCURACY_RESULT),
    ("reconciliation", "one_to_one", RECONCILIATION_RESULT),
]


class TestSummaryPerDimension:
    @pytest.mark.parametrize("dim,subtype,result", ALL_DIMS_RESULTS)
    def test_total_rows_correct(self, dim, subtype, result):
        s = normalize_summary(result, _make_rule(dim, subtype))
        assert s["total_rows"] == result["rows_scanned"]

    @pytest.mark.parametrize("dim,subtype,result", ALL_DIMS_RESULTS)
    def test_passed_rows_correct(self, dim, subtype, result):
        s = normalize_summary(result, _make_rule(dim, subtype))
        assert s["passed_rows"] == result["rows_passed"]

    @pytest.mark.parametrize("dim,subtype,result", ALL_DIMS_RESULTS)
    def test_failed_rows_correct(self, dim, subtype, result):
        s = normalize_summary(result, _make_rule(dim, subtype))
        assert s["failed_rows"] == result["rows_failed"]

    @pytest.mark.parametrize("dim,subtype,result", ALL_DIMS_RESULTS)
    def test_pass_rate_correct(self, dim, subtype, result):
        s = normalize_summary(result, _make_rule(dim, subtype))
        assert s["pass_rate"] == result["pass_rate"]


class TestSummaryCheckStatus:
    def test_pass_status_propagated(self):
        s = normalize_summary(
            {**COMPLETENESS_RESULT, "check_status": "PASS"},
            _make_rule("completeness", "null"),
        )
        assert s["check_status"] == "PASS"

    def test_warn_status_propagated(self):
        s = normalize_summary(
            {**VALIDITY_RESULT, "check_status": "WARN"},
            _make_rule("validity", "regex"),
        )
        assert s["check_status"] == "WARN"

    def test_fail_status_propagated(self):
        s = normalize_summary(
            {**COMPLETENESS_RESULT, "check_status": "FAIL"},
            _make_rule("completeness", "null"),
        )
        assert s["check_status"] == "FAIL"


class TestSummaryScore:
    def test_score_equals_pass_rate(self):
        s = normalize_summary(COMPLETENESS_RESULT, _make_rule("completeness", "null"))
        assert s["score"] == s["pass_rate"]


class TestSummaryThresholds:
    def test_threshold_pass_from_params(self):
        rule = _make_rule("completeness", "null", threshold_pass=95.0)
        s = normalize_summary(COMPLETENESS_RESULT, rule)
        assert s["threshold_pass"] == 95.0

    def test_threshold_warn_from_params(self):
        rule = _make_rule("completeness", "null", threshold_warn=90.0)
        s = normalize_summary(COMPLETENESS_RESULT, rule)
        assert s["threshold_warn"] == 90.0

    def test_threshold_warn_missing_is_none(self):
        rule = _make_rule("completeness", "null")
        s = normalize_summary(COMPLETENESS_RESULT, rule)
        assert s["threshold_warn"] is None


class TestSummarySkippedRows:
    def test_skipped_rows_from_validity_parser(self):
        s = normalize_summary(VALIDITY_RESULT, _make_rule("validity", "regex"))
        assert s["skipped_rows"] == 50

    def test_skipped_rows_default_zero(self):
        s = normalize_summary(COMPLETENESS_RESULT, _make_rule("completeness", "null"))
        assert s["skipped_rows"] == 0


class TestSummaryEdgeCases:
    def test_zero_rows_dataset(self):
        result = {
            "rows_scanned": 0,
            "rows_passed": 0,
            "rows_failed": 0,
            "pass_rate": 0.0,
            "check_status": "PASS",
        }
        s = normalize_summary(result, _make_rule("completeness", "null"))
        assert s["total_rows"] == 0
        assert s["pass_rate"] == 0.0

    def test_execution_duration_from_context(self):
        ctx = {"execution_duration_ms": 1500}
        s = normalize_summary(COMPLETENESS_RESULT, _make_rule("completeness", "null"), ctx)
        assert s["execution_duration_ms"] == 1500

    def test_dataset_name_from_target_table(self):
        s = normalize_summary(COMPLETENESS_RESULT, _make_rule("completeness", "null"))
        assert s["dataset_name"] == "public.customers"

    def test_rule_id_from_canonical_rule(self):
        s = normalize_summary(COMPLETENESS_RESULT, _make_rule("completeness", "null"))
        assert s["rule_id"] == "rule-002"


class TestSummaryMetadataPresence:
    @pytest.mark.parametrize("dim,subtype,result", ALL_DIMS_RESULTS)
    def test_summary_metadata_is_dict(self, dim, subtype, result):
        s = normalize_summary(result, _make_rule(dim, subtype))
        assert isinstance(s["summary_metadata"], dict)
