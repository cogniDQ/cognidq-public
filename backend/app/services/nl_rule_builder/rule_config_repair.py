"""
RuleConfigRepairService — automatic repair pass for incomplete subtype configs.

Implements the "repair before clarify" loop of the DQ Rule Compilation
Layer: when validation flags missing required fields, try to fill them
deterministically from:

1. Subtype defaults (`SUBTYPE_DEFAULTS`).
2. Dataset metadata (e.g. infer the timestamp_column when only one date
   column exists).
3. SIR-extracted constraints (operator, allowed values list).

If the repair succeeds and the config now passes
`validate_subtype_config`, the parser can proceed without bothering the
user. Otherwise we fall back to a clarifying question.

The repair pass NEVER invents:
- Column names not present in the dataset metadata
- Value lists that the user did not supply
- Patterns / regexes
- Reference datasets

Anything risky → defer to clarification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.nl_compiler.subtype_schema import (
    apply_subtype_defaults,
    get_subtype_meta,
    resolve_subtype_alias,
    validate_subtype_config,
)
from app.services.nl_rule_builder.dataset_metadata import DatasetMeta

RepairStatus = Literal["repaired", "needs_clarification", "no_repair_needed", "failed"]


@dataclass(slots=True)
class RepairResult:
    """Outcome of RuleConfigRepairService.repair()."""

    status: RepairStatus
    repaired_config: dict[str, Any] = field(default_factory=dict)
    applied: list[str] = field(default_factory=list)
    remaining_missing: list[str] = field(default_factory=list)


# Time-related fields whose unit can be reasonably inferred when not given.
_TIME_UNIT_FALLBACK = {
    "max_age_unit": "days",
    "max_latency_unit": "hours",
    "max_delay_unit": "minutes",
    "expected_frequency_unit": "hours",
    "temporal_window_unit": "days",
}


class RuleConfigRepairService:
    """One-pass deterministic repair for missing subtype config keys."""

    def repair(
        self,
        dimension: str,
        subtype: str,
        config: dict[str, Any] | None,
        dataset_meta: DatasetMeta | None = None,
        target_column: str | None = None,
    ) -> RepairResult:
        """Attempt to repair a config for a (dimension, subtype) pair.

        Args:
            dimension: Canonical DQ dimension.
            subtype: Canonical inventory subtype (alias-resolved upstream).
            config: The current (possibly incomplete) subtype config.
            dataset_meta: Metadata for the dataset the rule applies to,
                used to infer single-candidate columns.
            target_column: The subject column already chosen for the rule.

        Returns:
            A RepairResult describing what was filled in, what remains
            missing, and whether the config now satisfies the inventory.
        """
        canonical_sub = resolve_subtype_alias(dimension, subtype) if subtype else subtype
        meta = get_subtype_meta(dimension, canonical_sub) if canonical_sub else None
        repaired: dict[str, Any] = dict(config or {})

        # Short-circuit when subtype is unknown to inventory.
        if not meta:
            return RepairResult(
                status="failed",
                repaired_config=repaired,
                remaining_missing=["unknown_subtype"],
            )

        # 1. Apply static defaults (case_sensitive, inclusive bounds, etc.)
        before_keys = set(repaired.keys())
        repaired = apply_subtype_defaults(dimension, canonical_sub, repaired)
        applied = sorted(set(repaired.keys()) - before_keys)

        # 2. Infer columns from dataset metadata when there is exactly one
        #    obvious candidate. Conservative: never overwrite an existing
        #    value, never guess between multiple candidates.
        if dataset_meta is not None:
            applied.extend(
                self._infer_columns_from_dataset(
                    dimension, canonical_sub, repaired, dataset_meta, target_column
                )
            )

        # 3. Infer reasonable units for time-window fields
        for key, fallback in _TIME_UNIT_FALLBACK.items():
            if self._field_belongs_to_subtype(meta, key) and self._is_empty(repaired.get(key)):
                # Only fill the unit when the matching value is also present
                # (i.e. user supplied the number but not the unit).
                value_key = key.replace("_unit", "_value")
                if value_key in repaired and not self._is_empty(repaired[value_key]):
                    repaired[key] = fallback
                    applied.append(key)

        # 4. Re-validate. Strip duplicates from `applied`.
        applied = sorted(set(applied))
        missing_specs = validate_subtype_config(dimension, canonical_sub, repaired)
        remaining = [f[0] for f in missing_specs]

        if not remaining:
            status: RepairStatus = "repaired" if applied else "no_repair_needed"
            return RepairResult(
                status=status,
                repaired_config=repaired,
                applied=applied,
                remaining_missing=[],
            )

        return RepairResult(
            status="needs_clarification",
            repaired_config=repaired,
            applied=applied,
            remaining_missing=remaining,
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, (list, tuple, dict)) and len(value) == 0:
            return True
        return False

    @staticmethod
    def _field_belongs_to_subtype(meta: dict[str, Any], key: str) -> bool:
        for field_spec in meta.get("fields", []):
            if field_spec[0] == key:
                return True
        return False

    def _infer_columns_from_dataset(
        self,
        dimension: str,
        subtype: str,
        repaired: dict[str, Any],
        dataset_meta: DatasetMeta,
        target_column: str | None,
    ) -> list[str]:
        """Fill in `*_column` config keys when the dataset has exactly one
        compatible candidate and the user has not supplied one explicitly.

        Never overwrites an existing value. Never guesses between multiple
        candidates — we'd rather emit a clarifying question than commit to
        the wrong column.
        """
        applied: list[str] = []
        date_keys = {
            "timestamp_column",
            "event_timestamp_column",
            "load_timestamp_column",
            "start_timestamp_column",
            "end_timestamp_column",
            "start_column",
            "end_column",
        }
        column_keys = {
            "condition_column",
            "comparison_column",
            "compare_column",
            "reference_column",
            "temporal_column",
            "expected_column",
        }

        date_candidates = [
            c.name
            for c in dataset_meta.columns
            if (c.data_type or "").lower().startswith(("date", "timestamp", "datetime", "time"))
            and c.name != target_column
        ]
        non_subject_candidates = [c.name for c in dataset_meta.columns if c.name != target_column]

        for spec in get_subtype_meta(dimension, subtype).get("fields", []):
            key, _type, required, _opts = spec
            if not required or not self._is_empty(repaired.get(key)):
                continue
            if key in date_keys and len(date_candidates) == 1:
                repaired[key] = date_candidates[0]
                applied.append(key)
            elif key in column_keys and len(non_subject_candidates) == 1:
                repaired[key] = non_subject_candidates[0]
                applied.append(key)

        return applied
