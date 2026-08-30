"""
P03 — Summary Metadata Per Dimension

Tests _build_summary_metadata() for all 8 dimensions, verifying each
dimension's specific metadata fields are correctly extracted.
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
    _build_summary_metadata,
    normalize_summary,
)


def _rule(dim, subtype_val=None, **extra):
    key = DIMENSION_SUBTYPE_KEY.get(dim, "check_mode")
    params = {**extra}
    if subtype_val:
        params[key] = subtype_val
    return {
        "dimension": dim,
        "rule_id": "r",
        "target_table": "t",
        "severity": "medium",
        "parameters": params,
    }


# ── Completeness ───────────────────────────────────────────────────


class TestCompletenessMetadata:
    def test_check_mode_present(self):
        meta = _build_summary_metadata(
            "completeness",
            {"check_mode": "null", "zero_rows": False},
            {"check_mode": "null"},
        )
        assert meta["check_mode"] == "null"

    def test_zero_rows_present(self):
        meta = _build_summary_metadata(
            "completeness",
            {"check_mode": "null", "zero_rows": True},
            {"check_mode": "null"},
        )
        assert meta["zero_rows"] is True

    def test_group_results_included_if_present(self):
        result = {
            "check_mode": "group",
            "zero_rows": False,
            "metadata": {"group_results": [{"group": "A", "rate": 90}]},
        }
        meta = _build_summary_metadata("completeness", result, {"check_mode": "group"})
        assert "group_results" in meta
        assert meta["group_results"] == [{"group": "A", "rate": 90}]

    def test_group_results_absent_when_not_group_mode(self):
        result = {"check_mode": "null", "zero_rows": False}
        meta = _build_summary_metadata("completeness", result, {"check_mode": "null"})
        assert "group_results" not in meta


# ── Validity ───────────────────────────────────────────────────────


class TestValidityMetadata:
    def test_validation_type_present(self):
        meta = _build_summary_metadata(
            "validity",
            {"validation_type": "regex", "skipped_rows": 10},
            {"validation_type": "regex"},
        )
        assert meta["validation_type"] == "regex"

    def test_skipped_rows_present(self):
        meta = _build_summary_metadata(
            "validity",
            {"validation_type": "regex", "skipped_rows": 25},
            {"validation_type": "regex"},
        )
        assert meta["skipped_rows"] == 25


# ── Uniqueness ─────────────────────────────────────────────────────


class TestUniquenessMetadata:
    def test_four_fields_present(self):
        result = {
            "uniqueness_mode": "exact",
            "duplicate_groups": 50,
            "max_group_size": 4,
            "avg_group_size": 2.1,
        }
        meta = _build_summary_metadata("uniqueness", result, {"uniqueness_mode": "exact"})
        assert meta["uniqueness_mode"] == "exact"
        assert meta["duplicate_groups"] == 50
        assert meta["max_group_size"] == 4
        assert meta["avg_group_size"] == 2.1


# ── Conformity ─────────────────────────────────────────────────────


class TestConformityMetadata:
    def test_conformity_type_present(self):
        meta = _build_summary_metadata(
            "conformity",
            {"conformity_type": "standard"},
            {"conformity_type": "standard"},
        )
        assert meta["conformity_type"] == "standard"


# ── Consistency ────────────────────────────────────────────────────


class TestConsistencyMetadata:
    def test_consistency_type_present(self):
        meta = _build_summary_metadata(
            "consistency",
            {"consistency_type": "formula"},
            {"consistency_type": "formula"},
        )
        assert meta["consistency_type"] == "formula"


# ── Timeliness ─────────────────────────────────────────────────────


class TestTimelinessMetadata:
    def test_timeliness_type_present(self):
        meta = _build_summary_metadata(
            "timeliness",
            {"timeliness_type": "freshness", "metadata": {}},
            {"timeliness_type": "freshness"},
        )
        assert meta["timeliness_type"] == "freshness"

    def test_data_age_seconds_from_nested_metadata(self):
        result = {
            "timeliness_type": "freshness",
            "metadata": {"data_age_seconds": 7200, "most_recent": "2026-04-03T00:00:00Z"},
        }
        meta = _build_summary_metadata("timeliness", result, {"timeliness_type": "freshness"})
        assert meta["data_age_seconds"] == 7200
        assert meta["most_recent"] == "2026-04-03T00:00:00Z"

    def test_data_age_from_top_level(self):
        result = {
            "timeliness_type": "freshness",
            "data_age_seconds": 3600,
            "metadata": {},
        }
        meta = _build_summary_metadata("timeliness", result, {"timeliness_type": "freshness"})
        assert meta["data_age_seconds"] == 3600


# ── Accuracy ───────────────────────────────────────────────────────


class TestAccuracyMetadata:
    def test_three_fields_present(self):
        result = {
            "accuracy_type": "trusted_source",
            "verified_rows": 900,
            "unverifiable_rows": 100,
        }
        meta = _build_summary_metadata("accuracy", result, {"accuracy_type": "trusted_source"})
        assert meta["accuracy_type"] == "trusted_source"
        assert meta["verified_rows"] == 900
        assert meta["unverifiable_rows"] == 100


# ── Reconciliation ─────────────────────────────────────────────────


class TestReconciliationMetadata:
    def test_record_count_fields(self):
        result = {
            "reconciliation_type": "record_count",
            "source_count": 1000,
            "target_count": 980,
            "matched_count": 0,
            "missing_in_target": 0,
            "extra_in_target": 0,
        }
        meta = _build_summary_metadata(
            "reconciliation", result, {"reconciliation_type": "record_count"}
        )
        assert meta["reconciliation_type"] == "record_count"
        assert meta["source_count"] == 1000
        assert meta["target_count"] == 980

    def test_one_to_one_five_fields(self):
        result = {
            "reconciliation_type": "one_to_one",
            "source_count": 5000,
            "target_count": 4800,
            "matched_count": 4700,
            "missing_in_target": 300,
            "extra_in_target": 100,
        }
        meta = _build_summary_metadata(
            "reconciliation", result, {"reconciliation_type": "one_to_one"}
        )
        assert meta["matched_count"] == 4700
        assert meta["missing_in_target"] == 300
        assert meta["extra_in_target"] == 100


# ── Edge cases ─────────────────────────────────────────────────────


class TestMetadataEdgeCases:
    def test_missing_fields_graceful_defaults(self):
        meta = _build_summary_metadata("uniqueness", {}, {"uniqueness_mode": "exact"})
        assert meta["duplicate_groups"] == 0
        assert meta["max_group_size"] == 0

    def test_unknown_dimension_empty_metadata(self):
        meta = _build_summary_metadata("unknown_dim", {}, {})
        assert meta == {}

    def test_metadata_values_correct_types(self):
        result = {
            "uniqueness_mode": "exact",
            "duplicate_groups": 10,
            "max_group_size": 3,
            "avg_group_size": 1.5,
        }
        meta = _build_summary_metadata("uniqueness", result, {"uniqueness_mode": "exact"})
        assert isinstance(meta["duplicate_groups"], int)
        assert isinstance(meta["avg_group_size"], float)

    @pytest.mark.parametrize(
        "dim",
        [
            "completeness",
            "validity",
            "uniqueness",
            "conformity",
            "consistency",
            "timeliness",
            "accuracy",
            "reconciliation",
        ],
    )
    def test_direct_call_returns_dict(self, dim):
        meta = _build_summary_metadata(dim, {}, {})
        assert isinstance(meta, dict)
