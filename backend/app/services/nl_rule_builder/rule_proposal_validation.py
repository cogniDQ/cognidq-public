"""
RuleProposalValidationService — the hard gate for NL Rule Builder proposals.

Spec §7, §12, §13:
- Validates dataset existence
- Validates column existence (case-insensitive)
- Validates check-type support
- Validates operator support
- Validates required parameters per check type
- Validates type compatibility
- Validates that the proposal can be converted into an executable DQ flow
  (`dq_flow_convertible`)

A proposal can ONLY be persisted / submitted when ``dq_flow_convertible`` is True.
This service is called by:
  * The /parse endpoint to attach `validation` + `proposal_status` + `refinement`
  * The /validate endpoint to gate marking a parse as user-validated
  * The /create-flow endpoint as a final pre-flight
  * ProposalEngine.propose to reject invalid submissions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.schemas.nl_rule_builder import (
    CheckConfigOutput,
    ProposalValidation,
    RefinementGuidance,
    RefinementSuggestion,
    StructuredIntermediateRepresentation,
)
from app.services.nl_compiler.mappings import (
    OPERATOR_ALIASES,
    RULE_TYPE_MAP,
    RULE_TYPE_REQUIRED_TYPES,
    TYPE_COMPAT,
)
from app.services.nl_compiler.subtype_schema import (
    is_canonical_subtype,
    resolve_subtype_alias,
    validate_subtype_config,
)
from app.services.nl_rule_builder.dataset_metadata import ColumnMeta, DatasetMeta
from app.services.nl_rule_builder.flow_compatibility import (
    FlowCompatibilityValidator,
)
from app.services.nl_rule_builder.rule_config_repair import RuleConfigRepairService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Resolved:
    rule_type: str
    dimension: str
    subtype: str
    column_name: str | None
    column_meta: ColumnMeta | None
    operator: str | None
    subtype_config: dict
    threshold_value: float | None
    allowed_values: list | None


class RuleProposalValidationService:
    """The single source of truth for "is this rule proposal flow-convertible?".

    Pipeline (DQ Rule Compilation Layer):
        rule_type supported → dataset exists → column exists → type compat
        → operator supported → required params (canonical inventory) →
        repair pass → confidence gate → flow compatibility gate.

    A proposal is only marked `dq_flow_convertible=True` when every gate
    passes. Failing gates produce a `RefinementGuidance` with the
    machine-readable reason and (where applicable) candidate values.
    """

    def __init__(self) -> None:
        self._repair = RuleConfigRepairService()
        self._flow_compat = FlowCompatibilityValidator()

    def validate(
        self,
        sir: StructuredIntermediateRepresentation | None,
        dataset_meta: DatasetMeta | None,
        check_configs: list[CheckConfigOutput] | None = None,
    ) -> tuple[ProposalValidation, RefinementGuidance | None, dict | None]:
        """Run full validation on a parser output.

        Returns:
            (validation, refinement_or_none, rule_proposal_or_none)

        ``rule_proposal`` is the flat frontend-friendly dict (spec §11) populated
        only when validation passes (``dq_flow_convertible = True``).
        """
        v = ProposalValidation()
        if sir is None:
            v.errors.append("Parser could not interpret the rule.")
            return (
                v,
                RefinementGuidance(
                    reason="unknown_intent",
                    message="I could not interpret this as a data quality rule. Please rephrase.",
                    field="rule_text",
                ),
                None,
            )

        # Compound rules: validate each obligation, AND together. We treat the
        # proposal as valid only when every obligation is flow-convertible.
        if sir.is_compound and sir.obligations:
            return self._validate_compound(sir, dataset_meta, check_configs)

        return self._validate_atomic(sir, dataset_meta, check_configs)

    # ── single-obligation path ─────────────────────────────────────────────

    def _validate_atomic(
        self,
        sir: StructuredIntermediateRepresentation,
        dataset_meta: DatasetMeta | None,
        check_configs: list[CheckConfigOutput] | None,
    ) -> tuple[ProposalValidation, RefinementGuidance | None, dict | None]:
        v = ProposalValidation()

        # Resolve dimension/subtype/column from SIR + check_configs
        cc = check_configs[0] if check_configs else None
        rule_type = sir.rule_type.value if sir.rule_type else "unknown"
        if rule_type == "unknown":
            v.check_type_supported = False
            v.errors.append("Rule type is unknown.")
            ref = RefinementGuidance(
                reason="unsupported_check_type",
                message=(
                    "I understand you want to define a check, but I cannot map "
                    "this prompt to a supported Data Quality check type yet. "
                    "Please be more specific (e.g. 'must not be null', "
                    "'must be unique', 'must be greater than 0', "
                    "'must be one of …')."
                ),
                field="check_type",
            )
            return v, ref, None

        if rule_type in RULE_TYPE_MAP:
            dimension, subtype = RULE_TYPE_MAP[rule_type]
        else:
            v.check_type_supported = False
            v.errors.append(f"Rule type '{rule_type}' is not supported.")
            return (
                v,
                RefinementGuidance(
                    reason="unsupported_check_type",
                    message=f"Rule type '{rule_type}' is not supported.",
                    field="check_type",
                ),
                None,
            )

        if cc:
            dimension = cc.check_dimension or dimension
            subtype = cc.check_subtype or subtype
        elif sir.check_dimension and sir.check_subtype:
            dimension = sir.check_dimension
            subtype = sir.check_subtype

        v.check_type_supported = True

        # ── 1. Dataset existence ──
        if dataset_meta is None:
            v.dataset_exists = False
            v.errors.append("No dataset selected or resolved.")
            return (
                v,
                RefinementGuidance(
                    reason="missing_dataset",
                    message=(
                        "I need to know which dataset this rule applies to "
                        "before creating the rule proposal. Please select a "
                        "dataset or specify one in your request."
                    ),
                    next_question="Which dataset should this rule apply to?",
                    field="dataset",
                ),
                None,
            )
        v.dataset_exists = True

        # ── 2. Column existence ──
        column_raw = (sir.subject.raw_text or "").strip() if sir.subject else ""
        column_resolved = (sir.subject.resolved_column or "").strip() if sir.subject else ""
        # Prefer the parser-resolved name, fall back to raw text matching.
        candidate = column_resolved or column_raw
        col_meta = dataset_meta.column_by_name(candidate)
        if col_meta is None and cc and cc.columns:
            col_meta = dataset_meta.column_by_name(cc.columns[0])
            if col_meta:
                candidate = cc.columns[0]
        if col_meta is None:
            v.column_exists = False
            v.errors.append(
                f"Column '{candidate or '<unspecified>'}' was not found in dataset "
                f"'{dataset_meta.dataset_name}'."
            )
            suggestions = self._suggest_columns(candidate, dataset_meta)
            return (
                v,
                RefinementGuidance(
                    reason="unknown_column" if candidate else "missing_column",
                    message=(
                        f"I could not find a column named '{candidate}' in the "
                        f"selected dataset '{dataset_meta.dataset_name}'."
                        if candidate
                        else "Please specify which column this rule applies to."
                    ),
                    suggestions=suggestions,
                    next_question=(
                        f"Did you mean '{suggestions[0].value}'?"
                        if suggestions
                        else "Which column should this rule apply to?"
                    ),
                    field="column",
                ),
                None,
            )
        v.column_exists = True

        # ── 3. Type compatibility ──
        type_compat_ok, type_error = self._check_type_compat(
            rule_type, dimension, subtype, col_meta
        )
        v.type_compatible = type_compat_ok
        if not type_compat_ok:
            v.incompatible_fields.append("subject.data_type")
            v.errors.append(type_error or "Column type is incompatible with check type.")
            return (
                v,
                RefinementGuidance(
                    reason="type_incompatible",
                    message=type_error
                    or (
                        f"The column '{col_meta.name}' is a {col_meta.data_type} column, "
                        f"so this check is not compatible."
                    ),
                    suggestions=self._suggest_compatible_checks(col_meta),
                    field="check_type",
                ),
                None,
            )

        # ── 4. Operator supported ──
        op = sir.operator
        if op:
            op_norm = OPERATOR_ALIASES.get(str(op).strip().lower(), op)
            if op_norm.upper() not in {
                ">",
                "<",
                ">=",
                "<=",
                "=",
                "!=",
                "BETWEEN",
                "IN",
                "NOT IN",
                "IS NULL",
                "IS NOT NULL",
                "LIKE",
                "REGEXP",
            }:
                v.operator_supported = False
                v.errors.append(f"Operator '{op}' is not supported.")
                return (
                    v,
                    RefinementGuidance(
                        reason="invalid_operator",
                        message=f"Operator '{op}' is not supported.",
                        field="operator",
                    ),
                    None,
                )
        v.operator_supported = True

        # ── 5. Required params for the chosen subtype ──
        # Resolve aliases (e.g. cc.check_subtype="not_null" → canonical "null")
        # so we validate against the canonical inventory.
        canonical_subtype = resolve_subtype_alias(dimension, subtype) or subtype
        if not is_canonical_subtype(dimension, canonical_subtype):
            # Subtype is unknown to the canonical inventory → cannot build a
            # flow node. Surface an unsupported error rather than silently
            # passing.
            v.check_type_supported = False
            v.errors.append(
                f"Subtype '{subtype}' is not in the canonical inventory for "
                f"dimension '{dimension}'."
            )
            return (
                v,
                RefinementGuidance(
                    reason="unsupported_check_type",
                    message=(
                        f"The check '{dimension}/{subtype}' cannot be turned into "
                        "an executable DQ flow. Please pick a different check type."
                    ),
                    suggestions=[
                        RefinementSuggestion(
                            type="check_type",
                            value=s,
                            confidence=0.6,
                        )
                        for s in self._flow_compat.candidate_subtypes_for_dimension(dimension)[:5]
                    ],
                    field="check_subtype",
                ),
                None,
            )

        config = self._merge_config(sir, cc)

        # Repair pass — fill in safe defaults / single-candidate columns
        # before declaring the config invalid.
        repair_result = self._repair.repair(
            dimension=dimension,
            subtype=canonical_subtype,
            config=config,
            dataset_meta=dataset_meta,
            target_column=col_meta.name,
        )
        if repair_result.applied:
            config = repair_result.repaired_config
            logger.info(
                "Repaired %s/%s config: filled %s",
                dimension,
                canonical_subtype,
                repair_result.applied,
            )

        missing_specs = validate_subtype_config(dimension, canonical_subtype, config)
        if missing_specs:
            missing = [f[0] for f in missing_specs]
            v.missing_fields.extend(missing)
            v.required_params_present = False
            v.errors.append(
                f"Missing required parameter(s) for {dimension}/{canonical_subtype}: "
                f"{', '.join(missing)}"
            )
            return (
                v,
                self._refinement_for_missing_params(dimension, canonical_subtype, missing),
                None,
            )
        v.required_params_present = True

        # Persist canonical subtype back so downstream consumers see the
        # alias-resolved name.
        subtype = canonical_subtype

        # ── 6. Confidence / disambiguation gate ──
        if sir.requires_disambiguation or sir.confidence < 0.70:
            v.errors.append(
                "Parser confidence is below the threshold required to auto-create a proposal."
            )
            return (
                v,
                RefinementGuidance(
                    reason="low_confidence",
                    message=(
                        "I'm not confident enough about this interpretation to "
                        "create the rule proposal automatically. Please review "
                        "and answer the clarifying questions."
                    ),
                    field="confidence",
                ),
                None,
            )

        # ── 7. Flow compatibility — final pre-flight ──
        rule_proposal = self._build_rule_proposal(
            sir=sir,
            dataset_meta=dataset_meta,
            col_meta=col_meta,
            dimension=dimension,
            subtype=subtype,
            operator=op,
            config=config,
            cc=cc,
        )
        flow_compat = self._flow_compat.validate(rule_proposal, merged_config=config)
        if not flow_compat.can_generate_flow:
            v.errors.extend(flow_compat.errors)
            v.dq_flow_convertible = False
            return (
                v,
                RefinementGuidance(
                    reason="invalid_rule_structure",
                    message=(
                        "The rule passed individual checks but cannot be converted "
                        "into an executable DQ flow: " + "; ".join(flow_compat.errors)
                    ),
                    field="check_type",
                ),
                None,
            )

        v.dq_flow_convertible = True
        return v, None, rule_proposal

    # ── compound path ──────────────────────────────────────────────────────

    def _validate_compound(
        self,
        sir: StructuredIntermediateRepresentation,
        dataset_meta: DatasetMeta | None,
        check_configs: list[CheckConfigOutput] | None,
    ) -> tuple[ProposalValidation, RefinementGuidance | None, dict | None]:
        v = ProposalValidation()
        sub_proposals: list[dict] = []
        for idx, ob in enumerate(sir.obligations):
            sub_cc = [check_configs[idx]] if check_configs and idx < len(check_configs) else None
            ob_v, ob_ref, ob_prop = self._validate_atomic(ob, dataset_meta, sub_cc)
            if not ob_v.dq_flow_convertible:
                # Surface the first failure as the active refinement, but include
                # the index so the UI can route it to the right obligation card.
                if ob_ref is not None:
                    ob_ref.message = f"Obligation #{idx + 1}: {ob_ref.message}"
                v.errors.extend(f"Obligation #{idx + 1}: {e}" for e in ob_v.errors)
                v.missing_fields.extend(f"obligation_{idx}.{f}" for f in ob_v.missing_fields)
                return v, ob_ref, None
            sub_proposals.append(ob_prop or {})
            # Aggregate the booleans (AND-style)
            if idx == 0:
                v.dataset_exists = ob_v.dataset_exists
                v.column_exists = ob_v.column_exists
                v.check_type_supported = ob_v.check_type_supported
                v.operator_supported = ob_v.operator_supported
                v.type_compatible = ob_v.type_compatible
                v.required_params_present = ob_v.required_params_present
            else:
                v.dataset_exists = v.dataset_exists and ob_v.dataset_exists
                v.column_exists = v.column_exists and ob_v.column_exists
                v.check_type_supported = v.check_type_supported and ob_v.check_type_supported
                v.operator_supported = v.operator_supported and ob_v.operator_supported
                v.type_compatible = v.type_compatible and ob_v.type_compatible
                v.required_params_present = (
                    v.required_params_present and ob_v.required_params_present
                )
        v.dq_flow_convertible = True
        return (
            v,
            None,
            {
                "compound": True,
                "obligation_logic": sir.obligation_logic,
                "obligations": sub_proposals,
            },
        )

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_config(
        sir: StructuredIntermediateRepresentation, cc: CheckConfigOutput | None
    ) -> dict:
        config: dict = {}
        if sir.subtype_config:
            config.update(sir.subtype_config)
        if cc and cc.config:
            config.update(cc.config)
        # Top-level inline-extracted bits
        if getattr(sir, "threshold_pass", None) is not None:
            config.setdefault("threshold_pass", sir.threshold_pass)
        return config

    @staticmethod
    def _refinement_for_missing_params(
        dimension: str, subtype: str, missing: list[str]
    ) -> RefinementGuidance:
        # Map common missing params to a friendlier reason code
        first = missing[0]
        readable = first.replace("_", " ")
        reason = "missing_threshold"
        next_q = f"Please provide a value for: {readable}"
        msg = (
            f"This {dimension}/{subtype} check is missing required information: "
            f"{', '.join(missing)}."
        )
        if first in {"allowed_values", "placeholder_values"}:
            reason = "missing_allowed_values"
            next_q = f"Please list the {readable}."
        elif first in {
            "min_value",
            "max_value",
            "min_length",
            "max_length",
            "threshold_value",
            "fuzzy_threshold",
            "outlier_threshold",
            "max_age_value",
            "max_latency_value",
            "max_delay_value",
            "expected_frequency_value",
            "temporal_window_value",
            "tolerance_value",
        }:
            reason = "missing_threshold"
            next_q = f"Please provide a value for {readable}."
        elif first in {
            "pattern",
            "structural_pattern",
            "negative_pattern",
            "custom_charset_pattern",
        }:
            reason = "missing_threshold"
            next_q = f"Please provide the {readable}."
        elif first in {
            "scope_columns",
            "composite_columns",
            "compare_columns",
            "comparison_columns",
            "group_by_columns",
        }:
            reason = "missing_threshold"
            next_q = f"Please specify which columns are part of the {readable}."
        elif first.endswith("_column") or first in {
            "reference_column",
            "timestamp_column",
            "event_timestamp_column",
            "load_timestamp_column",
            "start_timestamp_column",
            "end_timestamp_column",
            "start_column",
            "end_column",
            "comparison_column",
            "compare_column",
            "condition_column",
            "temporal_column",
            "expected_column",
            "aggregate_column",
        }:
            reason = "missing_column"
            next_q = f"Which column should we use as the {readable}?"
        elif first in {"rule_expression", "business_rule_expression", "formula"}:
            reason = "missing_threshold"
            next_q = f"Please provide the {readable}."
        return RefinementGuidance(
            reason=reason,
            message=msg,
            next_question=next_q,
            field=first,
        )

    @staticmethod
    def _check_type_compat(
        rule_type: str, dimension: str, subtype: str, col: ColumnMeta
    ) -> tuple[bool, str | None]:
        # Numeric range / threshold need numeric column
        col_type = (col.data_type or "").lower()

        def _matches(category: str) -> bool:
            allowed = TYPE_COMPAT.get(category, set())
            return any(col_type.startswith(t) for t in allowed)

        # Explicit table for numeric/date/length-style checks
        if (dimension == "validity" and subtype == "range") or rule_type in (
            "numeric_threshold",
            "numeric_range",
        ):
            if not _matches("numeric"):
                return False, (
                    f"The column '{col.name}' is a {col.data_type} column, so a "
                    "numeric range/comparison check is not compatible. Try "
                    "'not null', 'allowed values', 'regex', or 'length' instead."
                )
        if (dimension == "consistency" and subtype == "temporal") or rule_type == "date_comparison":
            if not _matches("date"):
                return False, (
                    f"The column '{col.name}' is a {col.data_type} column, so a "
                    "date-comparison check is not compatible."
                )
        if dimension == "conformity" and subtype in (
            "regex",
            "length",
            "case",
            "charset",
            "structural",
        ):
            if not _matches("string"):
                return False, (
                    f"The column '{col.name}' is a {col.data_type} column, so a "
                    "text/format check is not compatible. Use a numeric or date "
                    "check instead."
                )
        # validity/regex on numeric column → not compatible
        if dimension == "validity" and subtype == "regex" and not _matches("string"):
            return False, (
                f"The column '{col.name}' is a {col.data_type} column, so a "
                "regex/text-pattern check is not compatible."
            )
        # Generic legacy mapping
        required_category = RULE_TYPE_REQUIRED_TYPES.get(rule_type)
        if required_category and not _matches(required_category):
            return False, (
                f"The column '{col.name}' has type '{col.data_type}' which is "
                f"incompatible with rule type '{rule_type}' "
                f"(expected {required_category})."
            )
        return True, None

    @staticmethod
    def _suggest_columns(
        target: str, dataset_meta: DatasetMeta, top_k: int = 3
    ) -> list[RefinementSuggestion]:
        """Suggest closest column names by simple character-level similarity."""
        if not target:
            return [
                RefinementSuggestion(
                    type="column",
                    value=c.name,
                    confidence=0.5,
                    rationale=f"{c.data_type}",
                )
                for c in dataset_meta.columns[:top_k]
            ]
        # Use difflib for cheap similarity scoring (no extra deps).
        import difflib

        scored: list[tuple[float, ColumnMeta]] = []
        target_l = target.lower()
        for c in dataset_meta.columns:
            ratio = difflib.SequenceMatcher(None, target_l, c.name.lower()).ratio()
            # Substring boost
            if target_l in c.name.lower() or c.name.lower() in target_l:
                ratio = max(ratio, 0.85)
            scored.append((ratio, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for ratio, c in scored[:top_k]:
            if ratio < 0.3:
                continue
            out.append(
                RefinementSuggestion(
                    type="column",
                    value=c.name,
                    confidence=round(ratio, 2),
                    rationale=f"{c.data_type}",
                )
            )
        return out

    @staticmethod
    def _suggest_compatible_checks(col: ColumnMeta) -> list[RefinementSuggestion]:
        col_type = (col.data_type or "").lower()
        is_numeric = any(col_type.startswith(t) for t in TYPE_COMPAT["numeric"])
        is_date = any(col_type.startswith(t) for t in TYPE_COMPAT["date"])
        if is_numeric:
            opts = ["not_null", "numeric_range", "value_in_list"]
        elif is_date:
            opts = ["not_null", "date_logic", "freshness"]
        else:
            opts = ["not_null", "regex_format", "value_in_list", "length_check"]
        return [RefinementSuggestion(type="check_type", value=o, confidence=0.7) for o in opts]

    @staticmethod
    def _build_rule_proposal(
        sir: StructuredIntermediateRepresentation,
        dataset_meta: DatasetMeta,
        col_meta: ColumnMeta,
        dimension: str,
        subtype: str,
        operator: str | None,
        config: dict,
        cc: CheckConfigOutput | None,
    ) -> dict:
        op_norm = (
            OPERATOR_ALIASES.get(str(operator).strip().lower(), operator) if operator else None
        )
        rule_name = (cc.rule_name if cc and cc.rule_name else None) or (
            f"{col_meta.name} {subtype.replace('_', ' ')}"
        )
        description = (cc.description if cc else None) or (
            f"Auto-generated {dimension}/{subtype} rule on "
            f"{dataset_meta.dataset_name}.{col_meta.name}"
        )
        proposal = {
            "rule_name": rule_name,
            "rule_description": description,
            "dataset_id": dataset_meta.dataset_id,
            "dataset_name": dataset_meta.dataset_name,
            "column_name": col_meta.name,
            "column_type": col_meta.data_type,
            "check_type": dimension,
            "check_subtype": subtype,
            "operator": op_norm,
            "severity": (cc.severity if cc else None) or "medium",
            "dq_flow_convertible": True,
        }
        # Echo any concrete value parameters
        for k in (
            "allowed_values",
            "min_value",
            "max_value",
            "pattern",
            "threshold_value",
            "expected_value",
            "reference_dataset",
            "scope_columns",
            "composite_columns",
        ):
            if k in config and config[k] not in (None, "", [], {}):
                proposal[k] = config[k]
        return proposal
