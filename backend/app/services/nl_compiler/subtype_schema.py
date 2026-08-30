"""
Canonical inventory of DQ check subtypes and their required configuration fields.

This file is the **backend mirror** of `frontend/src/schemas/dq-checks/*.ts`.
It must stay in sync with the frontend dimension schemas. When the frontend
adds/removes a subtype or required field, update this file too.

Used by:
- `nl_rule_builder.parser` to decide whether the parsed SIR has enough
  configuration to build a fully-specified check node, and to emit
  clarifying questions when a required field is missing.
- `nl_rule_builder.prompts` to inject the catalogue into the LLM prompt so
  the model knows the exact subtypes + fields it must populate.
- `nl_compiler.compiler` (optional) to validate compiled configs.

Each subtype entry:
    label        — short human-readable label (matches frontend)
    description  — what the subtype checks (matches frontend)
    fields       — tuple of (key, type_hint, required, options_or_None)
                   * key          : config field name in snake_case
                   * type_hint    : "string"|"number"|"bool"|"list"|"column"|"columns"|"expression"|"duration"
                   * required     : True when the field MUST be populated
                   * options      : tuple of allowed values for enum-style fields, else None
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# ----------------------------------------------------------------------------
# Type alias for a single field descriptor: (key, type, required, options)
# ----------------------------------------------------------------------------
FieldSpec = tuple[str, str, bool, tuple[str, ...] | None]


# ----------------------------------------------------------------------------
# Canonical inventory
# ----------------------------------------------------------------------------
# Ordering of dimensions/subtypes mirrors the frontend dimension files.
SUBTYPE_INVENTORY: dict[str, dict[str, dict[str, Any]]] = {
    # ── Completeness ────────────────────────────────────────────────────────
    "completeness": {
        "null": {
            "label": "NULL Check",
            "description": "Ensures values are not NULL",
            "fields": [
                ("include_empty_strings", "bool", False, None),
            ],
        },
        "empty": {
            "label": "Empty String Check",
            "description": "Detects empty or whitespace-only values",
            "fields": [],
        },
        "placeholder": {
            "label": "Placeholder Detection",
            "description": "Flags placeholder/sentinel values (N/A, TBD, etc.)",
            "fields": [
                ("placeholder_values", "list", True, None),
                ("case_sensitive", "bool", False, None),
            ],
        },
        "conditional": {
            "label": "Conditional Completeness",
            "description": "Column must be filled only when a condition is met",
            "fields": [
                ("condition_column", "column", True, None),
                (
                    "condition_operator",
                    "string",
                    True,
                    ("equals", "not_equals", "in", "not_null", "is_null"),
                ),
                ("condition_value", "string", False, None),
            ],
        },
        "multi_field": {
            "label": "Multi-Field Completeness",
            "description": "Check completeness across multiple columns together",
            "fields": [
                ("multi_field_mode", "string", True, ("all", "any")),
            ],
        },
        "population": {
            "label": "Population Coverage",
            "description": "Measures how many rows have non-null values",
            "fields": [],
        },
        "group": {
            "label": "Group-Level Completeness",
            "description": "Check completeness within groups defined by group-by columns",
            "fields": [
                ("group_by_columns", "columns", True, None),
            ],
        },
    },
    # ── Validity ────────────────────────────────────────────────────────────
    "validity": {
        "allowed_values": {
            "label": "Allowed Values",
            "description": "Values must be within a defined set",
            "fields": [
                ("allowed_values", "list", True, None),
                ("case_sensitive", "bool", False, None),
            ],
        },
        "range": {
            "label": "Range Check",
            "description": "Values must be within a numeric range",
            "fields": [
                # Either min_value or max_value must be supplied; enforced in
                # custom validation below (see `validate_subtype_config`).
                ("min_value", "number", False, None),
                ("max_value", "number", False, None),
                ("inclusive_min", "bool", False, None),
                ("inclusive_max", "bool", False, None),
            ],
        },
        "regex": {
            "label": "Pattern Match (Regex)",
            "description": "Values must match a regular expression",
            "fields": [
                ("pattern", "expression", True, None),
            ],
        },
        "reference_lookup": {
            "label": "Reference Lookup",
            "description": "Values must exist in a reference dataset column",
            "fields": [
                ("reference_column", "string", True, None),
            ],
        },
        "business_rule": {
            "label": "Business Rule",
            "description": "Values must satisfy a custom business rule expression",
            "fields": [
                ("business_rule_expression", "expression", True, None),
            ],
        },
        "cross_field": {
            "label": "Cross-Field Validation",
            "description": "Compare a column against another column in the same row",
            "fields": [
                ("comparison_column", "column", True, None),
                (
                    "comparison_operator",
                    "string",
                    True,
                    (
                        "equals",
                        "not_equals",
                        "greater_than",
                        "less_than",
                        "greater_equal",
                        "less_equal",
                    ),
                ),
            ],
        },
        "date_logic": {
            "label": "Date Logic",
            "description": "Validate date relationships between columns",
            "fields": [
                ("comparison_column", "column", True, None),
                ("date_operator", "string", True, ("before", "after", "same_day", "within")),
            ],
        },
        "negative": {
            "label": "Negative Pattern",
            "description": "Values must NOT match a given pattern or set",
            "fields": [
                ("negative_pattern", "expression", True, None),
                ("negative_match_mode", "string", True, ("regex", "exact", "contains")),
            ],
        },
    },
    # ── Conformity ──────────────────────────────────────────────────────────
    "conformity": {
        "standard": {
            "label": "Standard Format",
            "description": "Values must conform to a well-known standard",
            "fields": [
                (
                    "standard_name",
                    "string",
                    True,
                    (
                        "email",
                        "phone",
                        "date_iso",
                        "url",
                        "uuid",
                        "ip_address",
                        "credit_card",
                        "postal_code",
                        "ssn",
                    ),
                ),
            ],
        },
        "regex": {
            "label": "Regex Pattern",
            "description": "Values must match a custom regular expression",
            "fields": [
                ("pattern", "expression", True, None),
            ],
        },
        "length": {
            "label": "Length Constraint",
            "description": "String length must be within specified bounds",
            "fields": [
                # at-least-one enforced in custom validator
                ("min_length", "number", False, None),
                ("max_length", "number", False, None),
            ],
        },
        "charset": {
            "label": "Character Set",
            "description": "Values must only contain specified character sets",
            "fields": [
                (
                    "allowed_charset",
                    "string",
                    True,
                    ("alpha", "numeric", "alphanumeric", "ascii", "printable", "custom"),
                ),
                ("custom_charset_pattern", "expression", False, None),
            ],
        },
        "case": {
            "label": "Case Convention",
            "description": "Values must follow a specific casing convention",
            "fields": [
                ("expected_case", "string", True, ("upper", "lower", "title")),
            ],
        },
        "structural": {
            "label": "Structural Pattern",
            "description": "Values must follow a structural template (e.g., XX-9999)",
            "fields": [
                ("structural_pattern", "string", True, None),
            ],
        },
    },
    # ── Uniqueness ──────────────────────────────────────────────────────────
    "uniqueness": {
        "exact": {
            "label": "Exact Uniqueness",
            "description": "No duplicate values in the selected columns",
            "fields": [],
        },
        "composite": {
            "label": "Composite Key",
            "description": "Unique combination of multiple columns",
            "fields": [],
        },
        "scoped": {
            "label": "Scoped Uniqueness",
            "description": "Unique within groups defined by scope columns",
            "fields": [
                ("scope_columns", "columns", True, None),
            ],
        },
        "cross_dataset": {
            "label": "Cross-Dataset Uniqueness",
            "description": "Values must be unique across both this and a reference dataset",
            "fields": [
                ("cross_dataset_column", "string", True, None),
            ],
        },
        "fuzzy": {
            "label": "Fuzzy Duplicate Detection",
            "description": "Detect near-duplicates using similarity algorithms",
            "fields": [
                (
                    "fuzzy_algorithm",
                    "string",
                    True,
                    ("levenshtein", "jaro_winkler", "soundex", "ngram"),
                ),
                ("fuzzy_threshold", "number", True, None),
            ],
        },
        "temporal": {
            "label": "Temporal Uniqueness",
            "description": "Unique within a time window",
            "fields": [
                ("temporal_column", "column", True, None),
                ("temporal_window_value", "number", True, None),
                ("temporal_window_unit", "string", True, ("minutes", "hours", "days", "weeks")),
            ],
        },
    },
    # ── Consistency ─────────────────────────────────────────────────────────
    "consistency": {
        "intra_record": {
            "label": "Intra-Record Consistency",
            "description": "Validate relationships between fields within the same row",
            "fields": [
                ("rule_expression", "expression", True, None),
            ],
        },
        "formula": {
            "label": "Formula Consistency",
            "description": "Derived column must equal a formula of other columns",
            "fields": [
                ("rule_expression", "expression", True, None),
                ("tolerance_type", "string", False, ("none", "absolute", "percentage")),
                ("tolerance_value", "number", False, None),
            ],
        },
        "temporal": {
            "label": "Temporal Consistency",
            "description": "Validate temporal ordering between date/time columns",
            "fields": [
                ("start_column", "column", True, None),
                ("end_column", "column", True, None),
            ],
        },
        "inter_record": {
            "label": "Inter-Record Consistency",
            "description": "Validate consistency across related rows within the same table",
            "fields": [
                ("group_by_columns", "columns", True, None),
                ("comparison_columns", "columns", True, None),
            ],
        },
        "cross_table": {
            "label": "Cross-Table Consistency",
            "description": "Validate consistency between this dataset and a reference dataset",
            "fields": [
                ("comparison_columns", "columns", True, None),
            ],
        },
        "aggregation": {
            "label": "Aggregation Consistency",
            "description": "Aggregate values must match expected totals or constraints",
            "fields": [
                ("aggregate_function", "string", True, ("SUM", "COUNT", "AVG", "MIN", "MAX")),
                ("expected_column", "column", False, None),
                ("group_by_columns", "columns", False, None),
            ],
        },
    },
    # ── Accuracy ────────────────────────────────────────────────────────────
    "accuracy": {
        "reference_comparison": {
            "label": "Reference Comparison",
            "description": "Compare values against a trusted reference dataset",
            "fields": [
                ("compare_columns", "columns", True, None),
            ],
        },
        "trusted_source": {
            "label": "Trusted Source Match",
            "description": "Values must match a master/golden record dataset",
            "fields": [
                ("compare_columns", "columns", True, None),
                ("match_type", "string", True, ("exact", "case_insensitive", "trimmed")),
            ],
        },
        "tolerated_deviation": {
            "label": "Tolerated Deviation",
            "description": "Values may deviate from reference within a tolerance",
            "fields": [
                ("compare_column", "column", True, None),
                ("tolerance_type", "string", True, ("absolute", "percentage")),
                ("tolerance_value", "number", True, None),
            ],
        },
        "statistical": {
            "label": "Statistical Outlier",
            "description": "Detect outliers using statistical methods",
            "fields": [
                ("method", "string", True, ("z_score", "iqr")),
                ("outlier_threshold", "number", True, None),
            ],
        },
        "derived_value": {
            "label": "Derived Value Check",
            "description": "A column value must equal a formula applied to other columns",
            "fields": [
                ("formula", "expression", True, None),
                ("tolerance_type", "string", False, ("none", "absolute", "percentage")),
                ("tolerance_value", "number", False, None),
            ],
        },
    },
    # ── Timeliness ──────────────────────────────────────────────────────────
    "timeliness": {
        "freshness": {
            "label": "Data Freshness",
            "description": "Ensures data is not older than a maximum age",
            "fields": [
                ("timestamp_column", "column", True, None),
                ("max_age_value", "number", True, None),
                ("max_age_unit", "string", True, ("minutes", "hours", "days", "weeks")),
            ],
        },
        "record_age": {
            "label": "Record Age",
            "description": "Each record must be fresher than a specified duration",
            "fields": [
                ("timestamp_column", "column", True, None),
                ("max_age_value", "number", True, None),
                ("max_age_unit", "string", True, ("minutes", "hours", "days", "weeks")),
            ],
        },
        "latency": {
            "label": "Data Latency",
            "description": "Measures delay between event time and load time",
            "fields": [
                ("event_timestamp_column", "column", True, None),
                ("load_timestamp_column", "column", True, None),
                ("max_latency_value", "number", True, None),
                ("max_latency_unit", "string", True, ("minutes", "hours", "days")),
            ],
        },
        "processing_delay": {
            "label": "Processing Delay",
            "description": "Measures time between processing stages",
            "fields": [
                ("start_timestamp_column", "column", True, None),
                ("end_timestamp_column", "column", True, None),
                ("max_delay_value", "number", True, None),
                ("max_delay_unit", "string", True, ("seconds", "minutes", "hours")),
            ],
        },
        "delivery_window": {
            "label": "Delivery Window",
            "description": "Data must arrive within a specified time window",
            "fields": [
                ("delivery_window_start", "string", True, None),
                ("delivery_window_end", "string", True, None),
                ("timestamp_column", "column", True, None),
            ],
        },
        "heartbeat": {
            "label": "Heartbeat Monitor",
            "description": "Expects data at a regular frequency",
            "fields": [
                ("timestamp_column", "column", True, None),
                ("expected_frequency_value", "number", True, None),
                ("expected_frequency_unit", "string", True, ("minutes", "hours", "days")),
                ("metric_type", "string", True, ("row_count", "timestamp", "file_arrival")),
            ],
        },
    },
    # ── Reconciliation ──────────────────────────────────────────────────────
    "reconciliation": {
        "record_count": {
            "label": "Record Count",
            "description": "Source and target must have the same number of records",
            "fields": [],  # source_filter / target_filter are optional
        },
        "one_to_one": {
            "label": "One-to-One Matching",
            "description": "Every source record has exactly one match in the target",
            "fields": [],
        },
        "aggregate": {
            "label": "Aggregate Reconciliation",
            "description": "Aggregated values must match between datasets",
            "fields": [
                ("aggregate_column", "column", True, None),
                ("aggregate_function", "string", True, ("SUM", "COUNT", "AVG", "MIN", "MAX")),
            ],
        },
        "field_level": {
            "label": "Field-Level Comparison",
            "description": "Individual field values must match between mapped records",
            "fields": [
                ("compare_columns", "columns", True, None),
            ],
        },
        "tolerance": {
            "label": "Tolerance-Based Match",
            "description": "Values can differ within a defined tolerance",
            "fields": [
                ("tolerance_type", "string", True, ("absolute", "percentage")),
                ("tolerance_value", "number", True, None),
            ],
        },
        "missing_extra": {
            "label": "Missing & Extra Records",
            "description": "Identify records present in source but missing from target, and vice versa",
            "fields": [],
        },
    },
}


# ----------------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------------


def get_dimensions() -> list[str]:
    """Return the list of canonical dimension names."""
    return list(SUBTYPE_INVENTORY.keys())


def get_subtypes(dimension: str) -> list[str]:
    """Return the canonical list of subtype names for a dimension.

    Returns [] when the dimension is unknown.
    """
    return list(SUBTYPE_INVENTORY.get(dimension, {}).keys())


def get_subtype_meta(dimension: str, subtype: str) -> dict[str, Any] | None:
    """Return the full metadata dict for a (dimension, subtype) pair, or None."""
    dim = SUBTYPE_INVENTORY.get(dimension)
    if not dim:
        return None
    return dim.get(subtype)


def get_required_fields(dimension: str, subtype: str) -> list[FieldSpec]:
    """Return only the required field specs for a subtype."""
    meta = get_subtype_meta(dimension, subtype)
    if not meta:
        return []
    return [f for f in meta.get("fields", []) if f[2] is True]


def _is_empty(value: Any) -> bool:
    """Return True when the supplied value is considered "missing" for clarification purposes."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


def validate_subtype_config(
    dimension: str,
    subtype: str,
    config: dict[str, Any],
) -> list[FieldSpec]:
    """Return the list of REQUIRED fields that are missing from `config`.

    Special compound rules implemented here that the simple required-flag
    cannot capture:
        - validity/range : at least one of (min_value, max_value) must be set.
        - conformity/length : at least one of (min_length, max_length) must be set.
        - conformity/charset : if allowed_charset == "custom", custom_charset_pattern is required.

    Returns an empty list when the config is complete.
    """
    meta = get_subtype_meta(dimension, subtype)
    if not meta:
        return []

    config = config or {}
    missing: list[FieldSpec] = []

    # 1. Standard required-field check
    for field in meta.get("fields", []):
        key, _type, required, _opts = field
        if not required:
            continue
        if _is_empty(config.get(key)):
            missing.append(field)

    # 2. Compound rules — at-least-one
    if dimension == "validity" and subtype == "range":
        if _is_empty(config.get("min_value")) and _is_empty(config.get("max_value")):
            missing.append(("min_value", "number", True, None))
            missing.append(("max_value", "number", True, None))
    if dimension == "conformity" and subtype == "length":
        if _is_empty(config.get("min_length")) and _is_empty(config.get("max_length")):
            missing.append(("min_length", "number", True, None))
            missing.append(("max_length", "number", True, None))
    if dimension == "conformity" and subtype == "charset":
        if config.get("allowed_charset") == "custom" and _is_empty(
            config.get("custom_charset_pattern")
        ):
            missing.append(("custom_charset_pattern", "expression", True, None))

    # De-duplicate while preserving order
    seen: set = set()
    unique: list[FieldSpec] = []
    for f in missing:
        if f[0] not in seen:
            seen.add(f[0])
            unique.append(f)
    return unique


# ----------------------------------------------------------------------------
# Subtype aliases and defaults (DQ Rule Compilation Layer)
# ----------------------------------------------------------------------------
# Tolerated subtype aliases produced by the LLM or upstream compatibility
# code. Mapped back to the canonical inventory subtype names. Keys are
# (dimension, alias) → canonical_subtype.
SUBTYPE_ALIASES: dict[tuple[str, str], str] = {
    ("completeness", "not_null"): "null",
    ("completeness", "not-null"): "null",
    ("completeness", "non_null"): "null",
    ("completeness", "presence"): "null",
    ("validity", "value_in_list"): "allowed_values",
    ("validity", "in_list"): "allowed_values",
    ("validity", "numeric_range"): "range",
    ("validity", "email_format"): "regex",  # canonical email handled via conformity/standard
    ("conformity", "email"): "standard",
    ("conformity", "phone"): "standard",
    ("uniqueness", "unique"): "exact",
    ("uniqueness", "exact_match"): "exact",
    ("consistency", "column_comparison"): "intra_record",
    ("consistency", "arithmetic_comparison"): "formula",
    ("consistency", "date_comparison"): "temporal",
    ("accuracy", "statistical_outlier"): "statistical",
    ("reconciliation", "field_level_recon"): "field_level",
    ("reconciliation", "aggregate_recon"): "aggregate",
    ("reconciliation", "tolerance_recon"): "tolerance",
}


# Sensible defaults per (dimension, subtype). Applied by the repair service
# *before* declaring a config invalid. These are safe, conservative defaults
# that match the most common business intent for each subtype.
SUBTYPE_DEFAULTS: dict[tuple[str, str], dict[str, Any]] = {
    ("completeness", "null"): {"include_empty_strings": False},
    ("completeness", "placeholder"): {"case_sensitive": False},
    ("validity", "allowed_values"): {"case_sensitive": True},
    ("validity", "range"): {"inclusive_min": True, "inclusive_max": True},
    ("conformity", "case"): {},
    ("conformity", "charset"): {"allowed_charset": "alphanumeric"},
    ("uniqueness", "fuzzy"): {"fuzzy_algorithm": "jaro_winkler", "fuzzy_threshold": 0.85},
    ("uniqueness", "temporal"): {"temporal_window_unit": "days"},
    ("consistency", "formula"): {"tolerance_type": "none"},
    ("accuracy", "tolerated_deviation"): {"tolerance_type": "percentage"},
    ("accuracy", "statistical"): {"method": "z_score", "outlier_threshold": 3.0},
    ("timeliness", "freshness"): {"max_age_unit": "days"},
    ("timeliness", "record_age"): {"max_age_unit": "days"},
    ("timeliness", "latency"): {"max_latency_unit": "hours"},
    ("timeliness", "processing_delay"): {"max_delay_unit": "minutes"},
    ("timeliness", "heartbeat"): {"expected_frequency_unit": "hours", "metric_type": "row_count"},
    ("reconciliation", "tolerance"): {"tolerance_type": "percentage"},
}


def resolve_subtype_alias(dimension: str, subtype: str) -> str:
    """Return the canonical inventory subtype name for a (dimension, subtype)
    pair, applying common aliases when the LLM/upstream emits a variant name.

    If the pair is already canonical or unknown, the input is returned
    unchanged so callers can detect the unknown case.
    """
    if not dimension or not subtype:
        return subtype
    if get_subtype_meta(dimension, subtype) is not None:
        return subtype
    return SUBTYPE_ALIASES.get((dimension, subtype), subtype)


def is_canonical_subtype(dimension: str, subtype: str) -> bool:
    """Return True when (dimension, subtype) is a canonical inventory pair."""
    return get_subtype_meta(dimension, subtype) is not None


def get_subtype_defaults(dimension: str, subtype: str) -> dict[str, Any]:
    """Return the default param map for a (dimension, subtype) pair.

    Returns {} when no defaults are defined.
    """
    return dict(SUBTYPE_DEFAULTS.get((dimension, subtype), {}))


def apply_subtype_defaults(
    dimension: str,
    subtype: str,
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a new config dict with subtype defaults filled in for any keys
    that are currently missing or empty. Existing values are preserved.
    """
    out: dict[str, Any] = dict(config or {})
    for key, value in get_subtype_defaults(dimension, subtype).items():
        if _is_empty(out.get(key)):
            out[key] = value
    return out


def format_inventory_for_prompt(
    dimensions: Iterable[str] | None = None,
    *,
    indent: str = "  ",
) -> str:
    """Produce a compact human/LLM-readable catalogue of (dimension → subtypes → required fields).

    Used by the LLM prompt so the model knows exactly which subtypes exist
    and which config keys must accompany each one.
    """
    selected = list(dimensions) if dimensions else list(SUBTYPE_INVENTORY.keys())
    lines: list[str] = []
    for dim in selected:
        if dim not in SUBTYPE_INVENTORY:
            continue
        lines.append(f"- {dim}:")
        for sub, meta in SUBTYPE_INVENTORY[dim].items():
            req = [f for f in meta.get("fields", []) if f[2]]
            opt = [f for f in meta.get("fields", []) if not f[2]]
            req_str = ", ".join(_field_to_str(f) for f in req) if req else "(no required fields)"
            opt_str = ", ".join(_field_to_str(f) for f in opt)
            line = f"{indent}- {sub} — required: {req_str}"
            if opt_str:
                line += f"; optional: {opt_str}"
            lines.append(line)
    return "\n".join(lines)


def _field_to_str(spec: FieldSpec) -> str:
    key, type_hint, _required, options = spec
    if options:
        return f"{key} ({type_hint}: {'|'.join(options)})"
    return f"{key} ({type_hint})"
