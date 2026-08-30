"""
F092 — Canonical DQ Output Model — Result Normalizer

Pure-function module that transforms dimension-specific parser output
into a unified canonical schema for all 8 DQ dimensions.
"""

import uuid
from typing import Any

# ── Dimension → subtype parameter key ──────────────────────────────

DIMENSION_SUBTYPE_KEY: dict[str, str] = {
    "completeness": "check_mode",
    "validity": "validation_type",
    "uniqueness": "uniqueness_mode",
    "conformity": "conformity_type",
    "consistency": "consistency_type",
    "timeliness": "timeliness_type",
    "accuracy": "accuracy_type",
    "reconciliation": "reconciliation_type",
}

# ── Dimension → native rate field name ─────────────────────────────

DIMENSION_RATE_NAMES: dict[str, str] = {
    "completeness": "completeness_rate",
    "validity": "validity_rate",
    "uniqueness": "uniqueness_rate",
    "conformity": "conformity_rate",
    "consistency": "consistency_rate",
    "timeliness": "timeliness_rate",
    "accuracy": "accuracy_rate",
    "reconciliation": "match_rate",
}


# ── Dataset-level summary normalizer ──────────────────────────────


def normalize_summary(
    execution_result: dict,
    canonical_rule: dict,
    execution_context: dict | None = None,
) -> dict:
    """
    Map parsed dimension result → canonical dataset-level summary.

    Parameters
    ----------
    execution_result : dict
        Output from a _parse_*_results() method.
    canonical_rule : dict
        The canonical rule dict used for compilation.
    execution_context : dict, optional
        Runtime context with execution_id, execution_timestamp, execution_duration_ms.

    Returns
    -------
    dict  — canonical dataset-level summary with all required fields.
    """
    ctx = execution_context or {}
    params = canonical_rule.get("parameters", {})
    dimension = canonical_rule.get("dimension", "")
    subtype_key = DIMENSION_SUBTYPE_KEY.get(dimension, "")
    dimension_subtype = params.get(subtype_key, "unknown") if subtype_key else "unknown"

    rows_scanned = execution_result.get("rows_scanned", 0)
    rows_passed = execution_result.get("rows_passed", 0)
    rows_failed = execution_result.get("rows_failed", 0)
    pass_rate = float(execution_result.get("pass_rate", 0.0))
    check_status = execution_result.get("check_status", "FAIL")
    skipped_rows = execution_result.get("skipped_rows", 0)

    return {
        "execution_id": ctx.get("execution_id"),
        "rule_id": canonical_rule.get("rule_id"),
        "dimension": dimension,
        "dimension_subtype": dimension_subtype,
        "dataset_name": canonical_rule.get("target_table", ""),
        "total_rows": rows_scanned,
        "passed_rows": rows_passed,
        "failed_rows": rows_failed,
        "skipped_rows": skipped_rows,
        "pass_rate": pass_rate,
        "threshold_pass": params.get("threshold_pass"),
        "threshold_warn": params.get("threshold_warn"),
        "check_status": check_status,
        "score": pass_rate,
        "execution_timestamp": ctx.get("execution_timestamp"),
        "execution_duration_ms": ctx.get("execution_duration_ms"),
        "summary_metadata": _build_summary_metadata(dimension, execution_result, params),
    }


# ── Per-dimension summary metadata extraction ─────────────────────


def _build_summary_metadata(
    dimension: str,
    execution_result: dict,
    params: dict,
) -> dict:
    """Extract dimension-specific summary metadata fields."""

    if dimension == "completeness":
        meta: dict[str, Any] = {
            "check_mode": execution_result.get("check_mode", params.get("check_mode")),
            "zero_rows": execution_result.get("zero_rows", False),
        }
        if "group_results" in execution_result.get("metadata", {}):
            meta["group_results"] = execution_result["metadata"]["group_results"]
        return meta

    if dimension == "validity":
        return {
            "validation_type": execution_result.get(
                "validation_type", params.get("validation_type")
            ),
            "skipped_rows": execution_result.get("skipped_rows", 0),
        }

    if dimension == "uniqueness":
        return {
            "uniqueness_mode": execution_result.get(
                "uniqueness_mode", params.get("uniqueness_mode")
            ),
            "duplicate_groups": execution_result.get("duplicate_groups", 0),
            "max_group_size": execution_result.get("max_group_size", 0),
            "avg_group_size": execution_result.get("avg_group_size", 0),
        }

    if dimension == "conformity":
        return {
            "conformity_type": execution_result.get(
                "conformity_type", params.get("conformity_type")
            ),
        }

    if dimension == "consistency":
        return {
            "consistency_type": execution_result.get(
                "consistency_type", params.get("consistency_type")
            ),
        }

    if dimension == "timeliness":
        meta = {
            "timeliness_type": execution_result.get(
                "timeliness_type", params.get("timeliness_type")
            ),
        }
        # Timeliness stashes extra fields in a nested metadata dict
        inner = execution_result.get("metadata", {})
        if "data_age_seconds" in inner or "data_age_seconds" in execution_result:
            meta["data_age_seconds"] = inner.get(
                "data_age_seconds", execution_result.get("data_age_seconds")
            )
        if "most_recent" in inner or "most_recent" in execution_result:
            meta["most_recent"] = inner.get("most_recent", execution_result.get("most_recent"))
        return meta

    if dimension == "accuracy":
        return {
            "accuracy_type": execution_result.get("accuracy_type", params.get("accuracy_type")),
            "verified_rows": execution_result.get("verified_rows", 0),
            "unverifiable_rows": execution_result.get("unverifiable_rows", 0),
        }

    if dimension == "reconciliation":
        return {
            "reconciliation_type": execution_result.get(
                "reconciliation_type", params.get("reconciliation_type")
            ),
            "source_count": execution_result.get("source_count", 0),
            "target_count": execution_result.get("target_count", 0),
            "matched_count": execution_result.get("matched_count", 0),
            "missing_in_target": execution_result.get("missing_in_target", 0),
            "extra_in_target": execution_result.get("extra_in_target", 0),
        }

    # Unknown dimension — empty metadata
    return {}


# ── Row-level violation normalizer ────────────────────────────────


def normalize_violations(
    violations: list,
    canonical_rule: dict,
    execution_context: dict | None = None,
) -> list:
    """
    Map dimension-specific violation dicts → canonical row-level results.

    Parameters
    ----------
    violations : list[dict]
        Raw violations from execution_result["violations"].
    canonical_rule : dict
        Canonical rule used for compilation.
    execution_context : dict, optional
        Runtime context (execution_id, execution_timestamp).

    Returns
    -------
    list[dict]  — canonical row-level violation dicts.
    """
    if not violations:
        return []

    ctx = execution_context or {}
    params = canonical_rule.get("parameters", {})
    dimension = canonical_rule.get("dimension", "")
    subtype_key = DIMENSION_SUBTYPE_KEY.get(dimension, "")
    dimension_subtype = params.get(subtype_key, "unknown") if subtype_key else "unknown"
    severity = canonical_rule.get("severity", "medium")
    target_table = canonical_rule.get("target_table", "")

    # Column name: first column if single-column check
    columns = params.get("columns", [])
    column_name = columns[0] if len(columns) == 1 else None

    result = []
    for v in violations:
        observed, expected, deviation = _extract_observed_expected(dimension, v)
        reason = _build_issue_reason(dimension, dimension_subtype, v)
        business_key = v.get("row_identifier") or v.get("business_key") or v.get("key")

        result.append(
            {
                "result_id": str(uuid.uuid4()),
                "execution_id": ctx.get("execution_id"),
                "rule_id": canonical_rule.get("rule_id"),
                "dimension": dimension,
                "dimension_subtype": dimension_subtype,
                "dataset_name": target_table,
                "column_name": column_name,
                "business_key": str(business_key) if business_key is not None else None,
                "check_status": "FAIL",
                "observed_value": str(observed) if observed is not None else None,
                "expected_value": str(expected) if expected is not None else None,
                "deviation": deviation,
                "issue_reason": reason,
                "severity": severity,
                "execution_timestamp": ctx.get("execution_timestamp"),
                "metadata": _build_violation_metadata(dimension, v),
            }
        )
    return result


# ── Per-dimension observed / expected / deviation extraction ──────


def _extract_observed_expected(dimension: str, violation: dict):
    """Return (observed_value, expected_value, deviation) per dimension."""

    if dimension == "completeness":
        return ("NULL", "NOT NULL", None)

    if dimension == "validity":
        return (
            violation.get("observed_value") or violation.get("value"),
            violation.get("expected_value") or "valid per rule",
            None,
        )

    if dimension == "uniqueness":
        return (
            violation.get("duplicate_key") or violation.get("value"),
            "unique",
            None,
        )

    if dimension == "conformity":
        return (
            violation.get("observed_value") or violation.get("value"),
            violation.get("expected_pattern") or "conforming to format",
            None,
        )

    if dimension == "consistency":
        actual = violation.get("actual_value") or violation.get("observed_value")
        expected = violation.get("expected_value")
        deviation = None
        if actual is not None and expected is not None:
            try:
                deviation = float(actual) - float(expected)
            except (ValueError, TypeError):
                pass
        return (actual, expected, deviation)

    if dimension == "timeliness":
        return (
            violation.get("timestamp") or violation.get("observed_value"),
            violation.get("max_age") or violation.get("expected_value"),
            _safe_float(violation.get("age_seconds") or violation.get("deviation")),
        )

    if dimension == "accuracy":
        actual = violation.get("actual_value") or violation.get("observed_value")
        reference = violation.get("reference_value") or violation.get("expected_value")
        deviation = None
        if actual is not None and reference is not None:
            try:
                deviation = float(actual) - float(reference)
            except (ValueError, TypeError):
                pass
        return (actual, reference, deviation)

    if dimension == "reconciliation":
        return (
            violation.get("source_key") or violation.get("key") or violation.get("value"),
            violation.get("match_status") or "matched in target",
            None,
        )

    return (violation.get("observed_value"), violation.get("expected_value"), None)


# ── Per-dimension issue reason builder ────────────────────────────


def _build_issue_reason(dimension: str, subtype: str, violation: dict) -> str:
    """Build a human-readable issue reason string."""

    if dimension == "completeness":
        col = violation.get("column") or violation.get("column_name") or ""
        mode = subtype or "null"
        if mode in ("null", "unknown"):
            return f"Column '{col}' is NULL" if col else "Value is NULL"
        if mode == "empty":
            return f"Column '{col}' is empty" if col else "Value is empty"
        if mode == "placeholder":
            return (
                f"Column '{col}' contains a placeholder value"
                if col
                else "Placeholder value detected"
            )
        return f"Completeness {mode} check failed" + (f" on column '{col}'" if col else "")

    if dimension == "validity":
        return (
            f"Value does not satisfy {subtype} validation"
            if subtype != "unknown"
            else "Invalid value"
        )

    if dimension == "uniqueness":
        count = violation.get("duplicate_count") or violation.get("count")
        if count:
            return f"Duplicate value found ({count} occurrences)"
        return "Duplicate value found"

    if dimension == "conformity":
        return (
            f"Value does not conform to {subtype} format"
            if subtype != "unknown"
            else "Non-conforming value"
        )

    if dimension == "consistency":
        return "Inconsistent value detected"

    if dimension == "timeliness":
        age = violation.get("age_seconds") or violation.get("deviation")
        if age is not None:
            return f"Record exceeds maximum allowed age ({age}s)"
        return "Record exceeds maximum allowed age"

    if dimension == "accuracy":
        return "Value deviates from reference"

    if dimension == "reconciliation":
        status = violation.get("match_status") or violation.get("side")
        if status:
            return f"Record {status}"
        return "Reconciliation mismatch"

    return "Data quality check failed"


# ── Per-dimension violation metadata ──────────────────────────────


def _build_violation_metadata(dimension: str, violation: dict) -> dict:
    """Collect remaining dimension-specific fields into metadata."""
    # Pass through any extra keys not already consumed
    skip_keys = {
        "row_identifier",
        "business_key",
        "key",
        "value",
        "observed_value",
        "expected_value",
        "actual_value",
        "reference_value",
        "duplicate_key",
        "source_key",
        "column",
        "column_name",
        "timestamp",
        "max_age",
        "age_seconds",
        "expected_pattern",
        "deviation",
        "duplicate_count",
        "count",
        "match_status",
        "side",
    }
    return {k: v for k, v in violation.items() if k not in skip_keys}


# ── Helpers ───────────────────────────────────────────────────────


def _safe_float(value) -> float | None:
    """Convert value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
