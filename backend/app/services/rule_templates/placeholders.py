"""
Placeholder utilities for rule template application.

Convention:
    __COLUMN__      — primary target column
    __COLUMN_2__    — secondary column (cross-field, consistency)
    __TABLE__       — target table (replaced by target_table parameter)
    __REF_TABLE__   — reference table (reference_lookup, cross_dataset)
    __REF_COLUMN__  — reference column
"""

import re
from typing import Any

# Regex matching any __PLACEHOLDER__ token
_PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")

VALID_SEVERITIES = {"blocker", "critical", "high", "medium", "low"}

VALID_DIMENSIONS = {
    "completeness",
    "validity",
    "uniqueness",
    "conformity",
    "consistency",
    "timeliness",
    "accuracy",
    "reconciliation",
}


def extract_placeholders(canonical_rule_template: dict[str, Any]) -> set[str]:
    """Return the set of placeholder tokens found anywhere in the template dict."""
    found: set[str] = set()
    _walk(canonical_rule_template, found)
    return found


def _walk(obj: Any, found: set[str]) -> None:
    if isinstance(obj, str):
        found.update(_PLACEHOLDER_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, found)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, found)


def substitute_placeholders(
    obj: Any,
    mapping: dict[str, str],
) -> Any:
    """Deep-substitute all placeholder tokens in *obj* using *mapping*."""
    if isinstance(obj, str):
        result = obj
        for token, replacement in mapping.items():
            result = result.replace(token, replacement)
        return result
    elif isinstance(obj, dict):
        return {k: substitute_placeholders(v, mapping) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_placeholders(v, mapping) for v in obj]
    return obj


def validate_mapping_complete(
    required: set[str],
    provided: dict[str, str],
) -> list[str]:
    """Return list of missing placeholder keys, empty if all present."""
    missing = sorted(required - set(provided.keys()))
    return missing
