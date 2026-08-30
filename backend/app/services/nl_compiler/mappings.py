"""
Static mapping from SIR rule_type to DQ dimension, subtype, and defaults.
Covers all 47 check type+subtype combinations from dq_expected_results.
"""

from __future__ import annotations

from typing import Any

# (dimension, subtype)
RULE_TYPE_MAP: dict[str, tuple[str, str]] = {
    # ── Completeness ──
    "null_check": ("completeness", "null"),
    "not_null": ("completeness", "null"),
    "empty_check": ("completeness", "empty"),
    "placeholder_check": ("completeness", "placeholder"),
    "multi_field_completeness": ("completeness", "multi_field"),
    "conditional_completeness": ("completeness", "conditional"),
    "group_completeness": ("completeness", "group"),
    "population_completeness": ("completeness", "population"),
    # ── Uniqueness ──
    "uniqueness": ("uniqueness", "exact"),
    "composite_uniqueness": ("uniqueness", "composite"),
    "scoped_uniqueness": ("uniqueness", "scoped"),
    "fuzzy_uniqueness": ("uniqueness", "fuzzy"),
    "temporal_uniqueness": ("uniqueness", "temporal"),
    # ── Conformity ──
    "regex_format": ("conformity", "regex"),
    "length_check": ("conformity", "length"),
    "case_check": ("conformity", "case"),
    "charset_check": ("conformity", "charset"),
    "standard_format": ("conformity", "standard"),
    "structural_pattern": ("conformity", "structural"),
    # ── Consistency ──
    "column_comparison": ("consistency", "intra_record"),
    "formula_check": ("consistency", "formula"),
    "temporal_consistency": ("consistency", "temporal"),
    "inter_record": ("consistency", "inter_record"),
    "aggregation_consistency": ("consistency", "aggregation"),
    # ── Validity ──
    "value_in_list": ("validity", "allowed_values"),
    "numeric_range": ("validity", "range"),
    "date_logic": ("validity", "date_logic"),
    "reference_lookup": ("validity", "reference_lookup"),
    "business_rule": ("validity", "business_rule"),
    "cross_field": ("validity", "cross_field"),
    "negative_pattern": ("validity", "negative"),
    "regex_validation": ("validity", "regex"),
    # ── Accuracy ──
    "reference_comparison": ("accuracy", "reference_comparison"),
    "tolerated_deviation": ("accuracy", "tolerated_deviation"),
    "statistical_outlier": ("accuracy", "statistical"),
    "derived_value": ("accuracy", "derived_value"),
    # ── Timeliness ──
    "freshness": ("timeliness", "freshness"),
    "record_age": ("timeliness", "record_age"),
    "latency": ("timeliness", "latency"),
    "processing_delay": ("timeliness", "processing_delay"),
    "delivery_window": ("timeliness", "delivery_window"),
    "heartbeat": ("timeliness", "heartbeat"),
    # ── Reconciliation ──
    "record_count": ("reconciliation", "record_count"),
    "one_to_one": ("reconciliation", "one_to_one"),
    "field_level_recon": ("reconciliation", "field_level"),
    "aggregate_recon": ("reconciliation", "aggregate"),
    "tolerance_recon": ("reconciliation", "tolerance"),
    "missing_extra": ("reconciliation", "missing_extra"),
    # ── Backward compat aliases ──
    "date_comparison": ("consistency", "temporal"),
    "numeric_threshold": ("validity", "range"),
    "conditional_rule": ("completeness", "conditional"),
    "arithmetic_comparison": ("consistency", "formula"),
}

# Default config values per dimension
DIMENSION_DEFAULTS: dict[str, dict[str, Any]] = {
    "completeness": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "fail",
    },
    "validity": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
    "conformity": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
    "consistency": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "fail",
    },
    "uniqueness": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
    "accuracy": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
    "timeliness": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
    "reconciliation": {
        "threshold_pass": 100,
        "threshold_warn": 95,
        "null_handling": "skip",
    },
}

# Operator aliases — normalise NL operators to canonical form
OPERATOR_ALIASES: dict[str, str] = {
    "greater_than": ">",
    "less_than": "<",
    "greater_than_or_equal": ">=",
    "less_than_or_equal": "<=",
    "equal": "=",
    "equals": "=",
    "not_equal": "!=",
    "not_equals": "!=",
    "between": "BETWEEN",
    "in": "IN",
    "not_in": "NOT IN",
    "is_null": "IS NULL",
    "is_not_null": "IS NOT NULL",
    "contains": "LIKE",
    "starts_with": "LIKE",
    "ends_with": "LIKE",
    "matches": "REGEXP",
    ">": ">",
    "<": "<",
    ">=": ">=",
    "<=": "<=",
    "=": "=",
    "!=": "!=",
    # F126: natural-language phrase aliases
    "at least": ">=",
    "at most": "<=",
    "no more than": "<=",
    "no fewer than": ">=",
    "exactly": "=",
    "greater than": ">",
    "less than": "<",
    "after": ">",
    "before": "<",
    "not equal to": "!=",
    "different from": "!=",
    "more than": ">",
    "fewer than": "<",
}

# Data-type compatibility matrix
# Key = operator category, Value = set of compatible data-type prefixes
TYPE_COMPAT: dict[str, set] = {
    "numeric": {
        "integer",
        "int",
        "bigint",
        "smallint",
        "numeric",
        "decimal",
        "float",
        "double",
        "real",
        "number",
    },
    "date": {"date", "timestamp", "datetime", "time"},
    "string": {"varchar", "text", "char", "character", "string", "nvarchar", "nchar"},
}

# Which rule types need which type categories
RULE_TYPE_REQUIRED_TYPES: dict[str, str] = {
    "numeric_threshold": "numeric",
    "date_comparison": "date",
    "length_check": "string",
}
