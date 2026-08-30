"""
P04 — Row-Level Violation Normalization

Tests normalize_violations() canonical structure, issue_reason generation,
observed/expected extraction, and deviation computation for all 8 dimensions.
"""

import sys
import types
import uuid
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
    _build_issue_reason,
    _build_violation_metadata,
    _extract_observed_expected,
    normalize_violations,
)


def _rule(dim, subtype_val="test_sub", **extra):
    key = DIMENSION_SUBTYPE_KEY.get(dim, "check_mode")
    params = {key: subtype_val, **extra}
    return {
        "dimension": dim,
        "rule_id": "rule-004",
        "target_table": "public.orders",
        "severity": "high",
        "parameters": params,
    }


REQUIRED_KEYS = {
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


# ── Core structure ─────────────────────────────────────────────────


class TestViolationStructure:
    def test_has_all_canonical_keys(self):
        v = normalize_violations([{"row_identifier": "id=1"}], _rule("completeness"))[0]
        assert REQUIRED_KEYS.issubset(v.keys())

    def test_result_id_valid_uuid(self):
        v = normalize_violations([{"row_identifier": "id=1"}], _rule("completeness"))[0]
        uuid.UUID(v["result_id"])  # should not raise

    def test_execution_id_from_context(self):
        ctx = {"execution_id": "exec-99"}
        v = normalize_violations([{"row_identifier": "x"}], _rule("completeness"), ctx)[0]
        assert v["execution_id"] == "exec-99"

    def test_rule_id_from_canonical_rule(self):
        v = normalize_violations([{}], _rule("completeness"))[0]
        assert v["rule_id"] == "rule-004"

    def test_dimension_subtype_matches_summary(self):
        v = normalize_violations([{}], _rule("validity", "regex"))[0]
        assert v["dimension"] == "validity"
        assert v["dimension_subtype"] == "regex"

    def test_dataset_name_from_target_table(self):
        v = normalize_violations([{}], _rule("completeness"))[0]
        assert v["dataset_name"] == "public.orders"

    def test_column_name_from_columns_param(self):
        v = normalize_violations([{}], _rule("completeness", columns=["email"]))[0]
        assert v["column_name"] == "email"

    def test_column_name_none_when_no_columns(self):
        v = normalize_violations([{}], _rule("completeness"))[0]
        assert v["column_name"] is None

    def test_column_name_none_when_multiple_columns(self):
        v = normalize_violations([{}], _rule("completeness", columns=["a", "b"]))[0]
        assert v["column_name"] is None


# ── Issue reason per dimension ─────────────────────────────────────


class TestIssueReason:
    def test_completeness_null(self):
        reason = _build_issue_reason("completeness", "null", {"column": "email"})
        assert "NULL" in reason
        assert "email" in reason

    def test_completeness_empty(self):
        reason = _build_issue_reason("completeness", "empty", {"column": "name"})
        assert "empty" in reason

    def test_completeness_placeholder(self):
        reason = _build_issue_reason("completeness", "placeholder", {"column": "addr"})
        assert "placeholder" in reason

    def test_validity_with_subtype(self):
        reason = _build_issue_reason("validity", "regex", {})
        assert "regex" in reason

    def test_uniqueness_with_count(self):
        reason = _build_issue_reason("uniqueness", "exact", {"duplicate_count": 5})
        assert "5" in reason

    def test_uniqueness_without_count(self):
        reason = _build_issue_reason("uniqueness", "exact", {})
        assert "Duplicate" in reason

    def test_conformity_with_subtype(self):
        reason = _build_issue_reason("conformity", "standard", {})
        assert "standard" in reason

    def test_consistency(self):
        reason = _build_issue_reason("consistency", "formula", {})
        assert "Inconsistent" in reason

    def test_timeliness_with_age(self):
        reason = _build_issue_reason("timeliness", "freshness", {"age_seconds": 7200})
        assert "7200" in reason

    def test_timeliness_without_age(self):
        reason = _build_issue_reason("timeliness", "freshness", {})
        assert "age" in reason.lower()

    def test_accuracy(self):
        reason = _build_issue_reason("accuracy", "reference_comparison", {})
        assert "reference" in reason.lower()

    def test_reconciliation_with_status(self):
        reason = _build_issue_reason(
            "reconciliation", "one_to_one", {"match_status": "missing_in_target"}
        )
        assert "missing_in_target" in reason

    def test_reconciliation_without_status(self):
        reason = _build_issue_reason("reconciliation", "one_to_one", {})
        assert "mismatch" in reason.lower() or "Reconciliation" in reason

    def test_unknown_dimension(self):
        reason = _build_issue_reason("unknown", "sub", {})
        assert len(reason) > 0


# ── Observed / Expected / Deviation extraction ─────────────────────


class TestObservedExpected:
    def test_completeness_null_not_null(self):
        obs, exp, dev = _extract_observed_expected("completeness", {})
        assert obs == "NULL"
        assert exp == "NOT NULL"
        assert dev is None

    def test_validity_observed_from_violation(self):
        obs, exp, dev = _extract_observed_expected("validity", {"value": "abc"})
        assert obs == "abc"

    def test_uniqueness_duplicate_key(self):
        obs, exp, dev = _extract_observed_expected("uniqueness", {"duplicate_key": "dup@test.com"})
        assert obs == "dup@test.com"
        assert exp == "unique"

    def test_conformity_observed(self):
        obs, exp, dev = _extract_observed_expected("conformity", {"value": "12345"})
        assert obs == "12345"

    def test_consistency_deviation_computed(self):
        obs, exp, dev = _extract_observed_expected(
            "consistency", {"actual_value": 100, "expected_value": 90}
        )
        assert obs == 100
        assert exp == 90
        assert dev == 10.0

    def test_consistency_deviation_none_when_non_numeric(self):
        obs, exp, dev = _extract_observed_expected(
            "consistency", {"actual_value": "foo", "expected_value": "bar"}
        )
        assert dev is None

    def test_timeliness_observed(self):
        obs, exp, dev = _extract_observed_expected(
            "timeliness", {"timestamp": "2026-04-01", "max_age": "24h", "age_seconds": 90000}
        )
        assert obs == "2026-04-01"
        assert exp == "24h"
        assert dev == 90000.0

    def test_accuracy_deviation_computed(self):
        obs, exp, dev = _extract_observed_expected(
            "accuracy", {"actual_value": 105.0, "reference_value": 100.0}
        )
        assert obs == 105.0
        assert exp == 100.0
        assert dev == 5.0

    def test_accuracy_deviation_none_non_numeric(self):
        obs, exp, dev = _extract_observed_expected(
            "accuracy", {"actual_value": "abc", "reference_value": "def"}
        )
        assert dev is None

    def test_reconciliation_source_key(self):
        obs, exp, dev = _extract_observed_expected("reconciliation", {"source_key": "order-123"})
        assert obs == "order-123"


# ── Multiple violations ────────────────────────────────────────────


class TestMultipleViolations:
    def test_multiple_normalized(self):
        violations = [{"row_identifier": f"id={i}"} for i in range(5)]
        result = normalize_violations(violations, _rule("completeness"))
        assert len(result) == 5

    def test_each_unique_result_id(self):
        violations = [{"row_identifier": f"id={i}"} for i in range(3)]
        result = normalize_violations(violations, _rule("completeness"))
        ids = {r["result_id"] for r in result}
        assert len(ids) == 3


# ── Metadata ───────────────────────────────────────────────────────


class TestViolationMetadata:
    def test_metadata_is_dict(self):
        v = normalize_violations([{"row_identifier": "x"}], _rule("completeness"))[0]
        assert isinstance(v["metadata"], dict)

    def test_severity_from_rule(self):
        v = normalize_violations([{}], _rule("completeness"))[0]
        assert v["severity"] == "high"

    def test_execution_timestamp_from_context(self):
        ctx = {"execution_timestamp": "2026-04-03T12:00:00Z"}
        v = normalize_violations([{}], _rule("completeness"), ctx)[0]
        assert v["execution_timestamp"] == "2026-04-03T12:00:00Z"

    def test_violation_with_minimal_fields_no_crash(self):
        v = normalize_violations([{}], _rule("completeness"))[0]
        assert v["check_status"] == "FAIL"

    def test_extra_violation_fields_in_metadata(self):
        violation = {"row_identifier": "x", "extra_field": "extra_val"}
        v = normalize_violations([violation], _rule("completeness"))[0]
        assert v["metadata"].get("extra_field") == "extra_val"
