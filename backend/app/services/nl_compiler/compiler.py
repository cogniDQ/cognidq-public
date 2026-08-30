"""
NL Rule Compiler — translates resolved SIR into executable check node configs.
"""

from __future__ import annotations

from typing import Any

from app.schemas.nl_compiler import (
    CanonicalRuleOutput,
    CompilationStatus,
    CompiledCheckConfig,
    CompileRequest,
    CompileResponse,
    FallbackSuggestion,
)
from app.schemas.nl_rule_builder import (
    RuleType,
    StructuredIntermediateRepresentation,
)
from app.services.nl_compiler.mappings import (
    DIMENSION_DEFAULTS,
    OPERATOR_ALIASES,
    RULE_TYPE_MAP,
)
from app.services.nl_compiler.validators import validate_compatibility


class NLRuleCompiler:
    """Compile resolved SIR into check node configurations."""

    def compile(
        self,
        request: CompileRequest,
        column_data_types: dict[str, str] | None = None,
    ) -> CompileResponse:
        sir = request.resolved_rule
        options = request.compilation_options

        # F126: Compound → compile each obligation independently, bypassing parent type check
        if sir.is_compound and sir.obligations:
            return self._compile_compound(sir, options, column_data_types)

        # 1. Unknown → unsupported
        if sir.rule_type == RuleType.UNKNOWN:
            return CompileResponse(
                status=CompilationStatus.UNSUPPORTED,
                compiled_configs=[],
                warnings=[],
                rejection_reason="Rule type 'unknown' cannot be compiled. Rephrase the rule or select a supported type.",
                fallback_suggestions=self._suggest_fallbacks(sir),
            )

        # 2. Validate
        val_errors = validate_compatibility(sir, column_data_types)
        if val_errors:
            return CompileResponse(
                status=CompilationStatus.ERROR,
                compiled_configs=[],
                validation_errors=val_errors,
                warnings=[],
            )

        # 3. Compile
        try:
            configs = self._build_configs(sir, options)
            warnings = self._collect_warnings(sir, configs)
            status = CompilationStatus.SUCCESS
            if warnings:
                status = CompilationStatus.PARTIAL
            return CompileResponse(
                status=status,
                compiled_configs=configs,
                warnings=warnings,
            )
        except Exception as exc:
            return CompileResponse(
                status=CompilationStatus.ERROR,
                compiled_configs=[],
                warnings=[str(exc)],
            )

    # ── internal ──

    # ------------------------------------------------------------------ #
    # F126 — Compound Compilation                                          #
    # ------------------------------------------------------------------ #

    def _compile_compound(
        self,
        sir: StructuredIntermediateRepresentation,
        options: dict[str, Any],
        column_data_types: dict[str, str] | None = None,
    ) -> CompileResponse:
        """Compile a compound SIR by compiling each atomic obligation independently.

        Each compiled config gets `obligation_group_id` (a shared UUID) and
        `obligation_logic` (AND/OR/INDEPENDENT) so consumers can group and relate them.

        Partial results are kept — if some obligations fail, successful ones are returned
        with status=PARTIAL. All obligations failing → status=ERROR.
        """
        import uuid

        group_id = str(uuid.uuid4())
        all_configs: list[CompiledCheckConfig] = []
        all_warnings: list[str] = []
        has_error = False

        for obligation in sir.obligations:
            # Skip UNKNOWN obligations
            if obligation.rule_type == RuleType.UNKNOWN:
                all_warnings.append(
                    f"Obligation for '{obligation.subject.raw_text}' has unknown rule type — skipped."
                )
                has_error = True
                continue

            # Validate each obligation independently
            val_errors = validate_compatibility(obligation, column_data_types)
            if val_errors:
                all_warnings.extend(val_errors)
                has_error = True
                continue

            try:
                configs = self._build_configs(obligation, options)
                for cfg in configs:
                    cfg.obligation_group_id = group_id
                    cfg.obligation_logic = sir.obligation_logic
                all_configs.extend(configs)
                all_warnings.extend(self._collect_warnings(obligation, configs))
            except Exception as exc:
                all_warnings.append(
                    f"Obligation compile error for '{obligation.subject.raw_text}': {exc}"
                )
                has_error = True

        if not all_configs:
            return CompileResponse(
                status=CompilationStatus.ERROR,
                compiled_configs=[],
                warnings=all_warnings,
            )

        status = (
            CompilationStatus.PARTIAL if (has_error or all_warnings) else CompilationStatus.SUCCESS
        )
        return CompileResponse(
            status=status,
            compiled_configs=all_configs,
            warnings=all_warnings,
        )

    def _build_configs(
        self,
        sir: StructuredIntermediateRepresentation,
        options: dict[str, Any],
    ) -> list[CompiledCheckConfig]:
        rule_type = sir.rule_type.value

        if rule_type == "conditional_rule":
            return self._handle_conditional(sir, options)

        dimension, subtype = RULE_TYPE_MAP[rule_type]
        # Honor explicit dimension/subtype on the SIR (populated by the
        # NL parser from the LLM output or via clarification answers). They
        # take precedence over the rule_type → (dimension, subtype) mapping.
        if getattr(sir, "check_dimension", None):
            dimension = sir.check_dimension
        if getattr(sir, "check_subtype", None):
            subtype = sir.check_subtype
        config = self._build_single_config(sir, dimension, subtype, options)
        return [config]

    def _build_single_config(
        self,
        sir: StructuredIntermediateRepresentation,
        dimension: str,
        subtype: str,
        options: dict[str, Any],
    ) -> CompiledCheckConfig:
        rule_type = sir.rule_type.value
        subject_col = sir.subject.resolved_column or sir.subject.raw_text
        dataset_id = sir.subject.dataset_id
        dataset_name = sir.subject.resolved_dataset or ""
        severity = options.get("severity", "medium")
        defaults = DIMENSION_DEFAULTS.get(dimension, {})

        # Base config — include check_dimension for F128 CheckTypeConfig discriminator
        check_config: dict[str, Any] = {
            "check_dimension": dimension,
            "columns": [subject_col],
            "threshold_pass": options.get("threshold_pass", defaults.get("threshold_pass", 100)),
            "threshold_warn": options.get("threshold_warn", defaults.get("threshold_warn", 95)),
            "null_handling": options.get("null_handling", defaults.get("null_handling", "skip")),
        }

        # Normalise operator
        canonical_op = None
        if sir.operator:
            canonical_op = OPERATOR_ALIASES.get(sir.operator, sir.operator)

        # Rule-type-specific config
        builder = getattr(self, f"_config_{rule_type}", None)
        if builder:
            builder(sir, check_config, canonical_op)

        # Merge SIR.subtype_config (exhaustive snake_case keys captured during
        # parse-time, including clarification answers) on top so they always
        # win over rule-type-derived defaults.
        sir_subtype_config = getattr(sir, "subtype_config", None) or {}
        for key, value in sir_subtype_config.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            if isinstance(value, (list, tuple, dict)) and len(value) == 0:
                continue
            check_config[key] = value

        # Build canonical rule
        canonical_rule = self._build_canonical_rule(
            sir,
            dimension,
            subtype,
            subject_col,
            dataset_name,
            check_config,
            severity,
        )

        # Auto-generate name
        rule_name = self._generate_name(sir, dimension, subtype)

        return CompiledCheckConfig(
            check_type=dimension,
            subtype=subtype,
            dataset_id=dataset_id,
            rule_name=rule_name,
            severity=severity,
            description=f"Auto-compiled from: {sir.subject.raw_text}",
            config=check_config,
            canonical_rule=canonical_rule,
        )

    # ── per-type config builders ──

    def _config_null_check(self, sir, cfg, op):
        cfg["check_mode"] = "null"
        cfg["condition"] = "IS NULL"

    def _config_not_null(self, sir, cfg, op):
        cfg["check_mode"] = "null"
        cfg["condition"] = "IS NOT NULL"

    def _config_column_comparison(self, sir, cfg, op):
        if sir.object and sir.object.resolved_column:
            cfg["right_column"] = sir.object.resolved_column
        cfg["operator"] = op or "="

    def _config_numeric_threshold(self, sir, cfg, op):
        cfg["operator"] = op or ">="
        if sir.constraints:
            vals = sir.constraints
            if len(vals) >= 2:
                cfg["min_value"] = vals[0]
                cfg["max_value"] = vals[1]
            elif len(vals) == 1:
                cfg["threshold_value"] = vals[0]

    def _config_date_comparison(self, sir, cfg, op):
        if sir.object and sir.object.resolved_column:
            cfg["right_column"] = sir.object.resolved_column
        cfg["operator"] = op or ">"

    def _config_value_in_list(self, sir, cfg, op):
        cfg["allowed_values"] = sir.constraints if sir.constraints else []

    def _config_regex_format(self, sir, cfg, op):
        if sir.constraints:
            cfg["pattern"] = (
                sir.constraints[0]
                if isinstance(sir.constraints[0], str)
                else str(sir.constraints[0])
            )

    def _config_length_check(self, sir, cfg, op):
        if sir.constraints:
            vals = sir.constraints
            if len(vals) >= 2:
                cfg["min_length"] = vals[0]
                cfg["max_length"] = vals[1]
            elif len(vals) == 1:
                cfg["max_length"] = vals[0]

    def _config_uniqueness(self, sir, cfg, op):
        pass  # columns already set

    def _config_composite_uniqueness(self, sir, cfg, op):
        cols = list(cfg.get("columns", []))
        if sir.object and sir.object.resolved_column:
            cols.append(sir.object.resolved_column)
        if sir.constraints:
            for c in sir.constraints:
                if isinstance(c, str) and c not in cols:
                    cols.append(c)
        cfg["columns"] = cols

    def _config_reference_lookup(self, sir, cfg, op):
        if sir.object:
            cfg["reference_column"] = sir.object.resolved_column
            cfg["reference_dataset"] = sir.object.resolved_dataset
            cfg["reference_dataset_id"] = sir.object.dataset_id

    def _config_arithmetic_comparison(self, sir, cfg, op):
        if sir.object and sir.object.resolved_column:
            cfg["right_column"] = sir.object.resolved_column
        cfg["operator"] = op or "="
        if sir.constraints:
            cfg["formula_components"] = sir.constraints

    # ── conditional ──

    def _handle_conditional(
        self,
        sir: StructuredIntermediateRepresentation,
        options: dict[str, Any],
    ) -> list[CompiledCheckConfig]:
        """Conditional rules compile to a single config with embedded conditions."""
        dimension, subtype = RULE_TYPE_MAP["conditional_rule"]
        config = self._build_single_config(sir, dimension, subtype, options)

        # Embed conditions
        conditions = []
        for cond in sir.conditions:
            conditions.append(
                {
                    "field": cond.field.resolved_column or cond.field.raw_text,
                    "operator": OPERATOR_ALIASES.get(cond.operator, cond.operator),
                    "value": cond.value,
                }
            )
        config.config["conditions"] = conditions
        config.config["check_mode"] = "conditional"
        return [config]

    # ── canonical rule bridge ──

    def _build_canonical_rule(
        self,
        sir: StructuredIntermediateRepresentation,
        dimension: str,
        subtype: str,
        column: str,
        dataset: str,
        check_config: dict[str, Any],
        severity: str,
    ) -> CanonicalRuleOutput:
        entity = f"{dataset}.{column}" if dataset else column
        condition = self._derive_condition(sir, check_config)
        expectation = f"{check_config.get('threshold_pass', 100)}%"

        # F128: return typed CanonicalRuleOutput — extra fields (dimension, entity, etc.)
        # are captured by extra='allow' and accessible via canonical_rule["key"]
        return CanonicalRuleOutput(
            rule_type=sir.rule_type.value,
            subject=column,
            operator=sir.operator or "",
            severity=severity,
            threshold_pass=check_config.get("threshold_pass"),
            threshold_warn=check_config.get("threshold_warn"),
            # Legacy fields preserved as extras for backward compat
            dimension=dimension,
            entity=entity,
            condition=condition,
            expectation=expectation,
            parameters={
                "subtype": subtype,
                **{
                    k: v
                    for k, v in check_config.items()
                    if k
                    not in (
                        "columns",
                        "threshold_pass",
                        "threshold_warn",
                        "null_handling",
                        "check_dimension",
                    )
                },
            },
        )

    def _derive_condition(
        self,
        sir: StructuredIntermediateRepresentation,
        check_config: dict[str, Any],
    ) -> str:
        rule_type = sir.rule_type.value
        col = sir.subject.resolved_column or sir.subject.raw_text

        if rule_type == "null_check":
            return f"{col} IS NULL"
        if rule_type == "not_null":
            return f"{col} IS NOT NULL"
        if rule_type in ("column_comparison", "date_comparison", "arithmetic_comparison"):
            op = check_config.get("operator", "=")
            right = check_config.get("right_column", "?")
            return f"{col} {op} {right}"
        if rule_type == "numeric_threshold":
            op = check_config.get("operator", ">=")
            val = check_config.get("threshold_value", check_config.get("min_value", "?"))
            return f"{col} {op} {val}"
        if rule_type == "value_in_list":
            vals = check_config.get("allowed_values", [])
            return f"{col} IN ({', '.join(repr(v) for v in vals)})"
        if rule_type == "regex_format":
            pat = check_config.get("pattern", "?")
            return f"{col} ~ '{pat}'"
        if rule_type == "length_check":
            max_l = check_config.get("max_length", "?")
            min_l = check_config.get("min_length")
            if min_l is not None:
                return f"length({col}) BETWEEN {min_l} AND {max_l}"
            return f"length({col}) <= {max_l}"
        if rule_type == "uniqueness":
            return f"{col} IS UNIQUE"
        if rule_type == "composite_uniqueness":
            cols = check_config.get("columns", [col])
            return f"({', '.join(cols)}) IS UNIQUE"
        if rule_type == "reference_lookup":
            ref = check_config.get("reference_column", "?")
            return f"{col} IN (SELECT {ref} FROM reference)"
        if rule_type == "conditional_rule":
            return f"IF conditions THEN {col} IS NOT NULL"
        return f"{col} check"

    # ── helpers ──

    def _generate_name(
        self,
        sir: StructuredIntermediateRepresentation,
        dimension: str,
        subtype: str,
    ) -> str:
        col = sir.subject.resolved_column or sir.subject.raw_text
        return f"{dimension}_{subtype}_{col}".replace(" ", "_").lower()

    def _suggest_fallbacks(
        self,
        sir: StructuredIntermediateRepresentation,
    ) -> list[FallbackSuggestion]:
        suggestions = []
        text = sir.subject.raw_text.lower()

        if any(w in text for w in ("null", "empty", "blank", "missing")):
            suggestions.append(
                FallbackSuggestion(
                    suggested_type="not_null",
                    reason="The rule mentions null/empty values — try a completeness check.",
                    confidence=0.7,
                )
            )
        if any(w in text for w in ("unique", "distinct", "duplicate")):
            suggestions.append(
                FallbackSuggestion(
                    suggested_type="uniqueness",
                    reason="The rule mentions uniqueness — try a uniqueness check.",
                    confidence=0.7,
                )
            )
        if any(w in text for w in ("format", "pattern", "match")):
            suggestions.append(
                FallbackSuggestion(
                    suggested_type="regex_format",
                    reason="The rule mentions format/pattern — try a conformity check.",
                    confidence=0.6,
                )
            )

        # Always suggest the most common types
        if not suggestions:
            suggestions.append(
                FallbackSuggestion(
                    suggested_type="not_null",
                    reason="Most common check type — ensure the field is not null.",
                    confidence=0.3,
                )
            )
        return suggestions

    def _collect_warnings(
        self,
        sir: StructuredIntermediateRepresentation,
        configs: list[CompiledCheckConfig],
    ) -> list[str]:
        warnings: list[str] = []
        if sir.confidence < 0.7:
            warnings.append(
                f"Low parse confidence ({sir.confidence:.2f}). Review the compiled rule carefully."
            )
        if sir.parse_warnings:
            warnings.extend(sir.parse_warnings)
        return warnings
