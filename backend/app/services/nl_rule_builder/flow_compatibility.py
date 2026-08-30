"""
FlowCompatibilityValidator — final pre-flight that simulates building the DQ
flow check-node config from a rule proposal so we never accept a proposal
that will crash the flow generator.

This is the last gate of the DQ Rule Compilation Layer:

    intent → subtype resolution → config build → normalization →
    schema validation → **flow compatibility validation** → ready

If the simulated check-node build is missing a required key, has an unknown
dimension/subtype, or the dataset id is missing, the gate fails and the
parser must surface a clarification instead of a "ready" rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.nl_compiler.mappings import RULE_TYPE_MAP
from app.services.nl_compiler.subtype_schema import (
    SUBTYPE_INVENTORY,
    is_canonical_subtype,
    resolve_subtype_alias,
    validate_subtype_config,
)

# Keys that must be present on the simulated check-node config. These mirror
# what `nl_flow_generator.generator.NLFlowGenerator._build_check_node` reads
# back when wiring the runtime executor.
_REQUIRED_NODE_KEYS = ("check_dimension", "check_subtype", "columns", "dataset_id")


@dataclass(slots=True)
class FlowCompatibilityResult:
    """Outcome of FlowCompatibilityValidator.validate()."""

    can_generate_flow: bool = False
    errors: list[str] = field(default_factory=list)
    simulated_node: dict[str, Any] | None = None


class FlowCompatibilityValidator:
    """Dry-run the flow generator's check-node build to catch malformed configs."""

    def validate(
        self,
        rule_proposal: dict[str, Any] | None,
        merged_config: dict[str, Any] | None = None,
    ) -> FlowCompatibilityResult:
        """Validate that a rule proposal can be turned into a flow node.

        Args:
            rule_proposal: The flat proposal dict returned by
                `RuleProposalValidationService._build_rule_proposal`.
            merged_config: The full subtype config (sir.subtype_config merged
                with cc.config) used to populate the check node.

        Returns:
            FlowCompatibilityResult with `can_generate_flow=True` only when
            every gate passes.
        """
        result = FlowCompatibilityResult()

        if not rule_proposal:
            result.errors.append("No rule proposal supplied to flow compatibility check.")
            return result

        # Compound proposals are validated obligation-by-obligation upstream.
        if rule_proposal.get("compound") is True:
            obligations = rule_proposal.get("obligations") or []
            if not obligations:
                result.errors.append("Compound proposal has no obligations.")
                return result
            for idx, ob in enumerate(obligations):
                sub_res = self.validate(ob, None)
                if not sub_res.can_generate_flow:
                    for e in sub_res.errors:
                        result.errors.append(f"Obligation #{idx + 1}: {e}")
                    return result
            result.can_generate_flow = True
            return result

        dimension = rule_proposal.get("check_type") or rule_proposal.get("check_dimension")
        subtype = rule_proposal.get("check_subtype")
        column = rule_proposal.get("column_name")
        dataset_id = rule_proposal.get("dataset_id")

        # ── 1. Dimension / subtype must exist in the canonical inventory ──
        if not dimension or dimension not in SUBTYPE_INVENTORY:
            result.errors.append(f"Unknown check dimension '{dimension}'. Cannot build flow node.")
            return result

        canonical_subtype = resolve_subtype_alias(dimension, subtype) if subtype else None
        if not canonical_subtype or not is_canonical_subtype(dimension, canonical_subtype):
            result.errors.append(
                f"Unknown subtype '{subtype}' for dimension '{dimension}'. "
                f"Flow node factory cannot instantiate this check."
            )
            return result

        # ── 2. Dataset reference must exist ──
        if not dataset_id:
            result.errors.append("Rule proposal is missing dataset_id.")
            return result

        # ── 3. At least one target column ──
        if not column:
            # Some subtypes legitimately work without a single subject column
            # (e.g. reconciliation/record_count). Allow them through.
            no_column_ok = dimension == "reconciliation" and canonical_subtype in {
                "record_count",
                "one_to_one",
                "missing_extra",
            }
            if not no_column_ok:
                result.errors.append("Rule proposal is missing target column.")
                return result

        # ── 4. Required subtype config is satisfied ──
        config = dict(merged_config or {})
        # Echo proposal-level params back into the simulated config so we
        # validate the full payload that would land on the check node.
        for k in (
            "allowed_values",
            "min_value",
            "max_value",
            "pattern",
            "threshold_value",
            "expected_value",
            "reference_dataset",
            "reference_column",
            "scope_columns",
            "composite_columns",
        ):
            if k in rule_proposal and rule_proposal[k] not in (None, "", [], {}):
                config.setdefault(k, rule_proposal[k])

        missing = validate_subtype_config(dimension, canonical_subtype, config)
        if missing:
            keys = ", ".join(f[0] for f in missing)
            result.errors.append(
                f"Required parameter(s) missing for {dimension}/{canonical_subtype}: {keys}"
            )
            return result

        # ── 5. Build a simulated check-node config (mirrors generator) ──
        simulated_node = {
            "type": "check",
            "checkType": dimension,
            "label": rule_proposal.get("rule_name") or f"{dimension}_{canonical_subtype}",
            "config": {
                "check_dimension": dimension,
                "check_subtype": canonical_subtype,
                "columns": [column] if column else [],
                "dataset_id": dataset_id,
                "severity": rule_proposal.get("severity") or "medium",
                **config,
            },
        }

        for k in _REQUIRED_NODE_KEYS:
            v = simulated_node["config"].get(k)
            if v in (None, "", [], {}):
                # `columns` may be empty for the no-column subtypes above.
                if k == "columns" and not column:
                    continue
                result.errors.append(f"Simulated flow node is missing required key '{k}'.")
                return result

        result.simulated_node = simulated_node
        result.can_generate_flow = True
        return result

    @staticmethod
    def candidate_subtypes_for_dimension(dimension: str | None) -> list[str]:
        """Return the list of canonical subtype names for a dimension, or []."""
        if not dimension or dimension not in SUBTYPE_INVENTORY:
            return []
        return list(SUBTYPE_INVENTORY[dimension].keys())

    @staticmethod
    def derive_dimension_from_rule_type(rule_type: str | None) -> str | None:
        """Best-effort dimension lookup from a rule_type string."""
        if not rule_type:
            return None
        pair = RULE_TYPE_MAP.get(rule_type)
        return pair[0] if pair else None
