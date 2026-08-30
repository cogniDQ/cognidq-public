"""
F104 — NL Rule Compiler Tests
40+ tests covering schemas, mappings, validators, compiler, and endpoint.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.schemas.nl_compiler import (
    CompilationStatus,
    CompiledCheckConfig,
    CompileRequest,
    CompileResponse,
    FallbackSuggestion,
    ValidationError,
)
from app.schemas.nl_rule_builder import (
    RuleType,
    SIRCondition,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)
from app.services.nl_compiler.compiler import NLRuleCompiler
from app.services.nl_compiler.mappings import (
    DIMENSION_DEFAULTS,
    OPERATOR_ALIASES,
    RULE_TYPE_MAP,
    RULE_TYPE_REQUIRED_TYPES,
)
from app.services.nl_compiler.validators import validate_compatibility

# ── helpers ──


def make_sir(
    rule_type: str = "not_null",
    subject_col: str = "email",
    subject_dataset: str = "users",
    subject_dataset_id: str = None,
    operator: str = None,
    object_col: str = None,
    object_dataset: str = None,
    constraints: list = None,
    conditions: list = None,
    confidence: float = 0.95,
) -> StructuredIntermediateRepresentation:
    ds_id = subject_dataset_id or str(uuid4())
    obj = None
    if object_col:
        obj = SIREntity(
            raw_text=object_col,
            resolved_column=object_col,
            resolved_dataset=object_dataset or subject_dataset,
            dataset_id=ds_id,
        )
    return StructuredIntermediateRepresentation(
        rule_type=RuleType(rule_type),
        subject=SIREntity(
            raw_text=subject_col,
            resolved_column=subject_col,
            resolved_dataset=subject_dataset,
            dataset_id=ds_id,
        ),
        operator=operator,
        object=obj,
        constraints=constraints or [],
        conditions=conditions or [],
        confidence=confidence,
    )


def make_request(sir=None, options=None) -> CompileRequest:
    return CompileRequest(
        resolved_rule=sir or make_sir(),
        compilation_options=options or {},
    )


compiler = NLRuleCompiler()


# ══════════════════════════════════════
# 1. Schema Tests
# ══════════════════════════════════════


class TestSchemas:
    def test_compilation_status_values(self):
        assert CompilationStatus.SUCCESS == "success"
        assert CompilationStatus.PARTIAL == "partial"
        assert CompilationStatus.UNSUPPORTED == "unsupported"
        assert CompilationStatus.ERROR == "error"

    def test_compile_request_minimal(self):
        req = make_request()
        assert req.resolved_rule.rule_type == RuleType.NOT_NULL
        # F128: compilation_options is now a typed CompilationOptions (not dict)
        from app.schemas.nl_compiler import CompilationOptions

        assert isinstance(req.compilation_options, CompilationOptions)
        assert req.compilation_options.severity == "medium"

    def test_compiled_check_config_defaults(self):
        cfg = CompiledCheckConfig(
            check_type="completeness",
            subtype="null",
            rule_name="test_rule",
        )
        assert cfg.severity == "medium"
        # F128: config is now a typed GenericCheckConfig (not empty dict)
        from app.schemas.nl_compiler import GenericCheckConfig

        assert isinstance(cfg.config, GenericCheckConfig)
        assert cfg.canonical_rule is None

    def test_fallback_suggestion(self):
        fs = FallbackSuggestion(
            suggested_type="not_null",
            reason="Try completeness",
            confidence=0.7,
        )
        assert fs.suggested_type == "not_null"

    def test_validation_error_schema(self):
        ve = ValidationError(field="subject", message="missing", code="err")
        assert ve.field == "subject"


# ══════════════════════════════════════
# 2. Mapping Tests
# ══════════════════════════════════════


class TestMappings:
    def test_all_13_rule_types_mapped(self):
        for rt in RuleType:
            if rt == RuleType.UNKNOWN:
                assert rt.value not in RULE_TYPE_MAP
            else:
                assert rt.value in RULE_TYPE_MAP, f"{rt.value} not in RULE_TYPE_MAP"

    def test_dimension_defaults_all_present(self):
        dims = set(d for d, _ in RULE_TYPE_MAP.values())
        for dim in dims:
            assert dim in DIMENSION_DEFAULTS, f"Missing defaults for {dim}"

    def test_operator_aliases_standard(self):
        assert OPERATOR_ALIASES["greater_than"] == ">"
        assert OPERATOR_ALIASES["equals"] == "="
        assert OPERATOR_ALIASES["not_equals"] == "!="
        assert OPERATOR_ALIASES["between"] == "BETWEEN"

    def test_rule_type_required_types(self):
        assert RULE_TYPE_REQUIRED_TYPES["numeric_threshold"] == "numeric"
        assert RULE_TYPE_REQUIRED_TYPES["date_comparison"] == "date"
        assert RULE_TYPE_REQUIRED_TYPES["length_check"] == "string"


# ══════════════════════════════════════
# 3. Validator Tests
# ══════════════════════════════════════


class TestValidators:
    def test_valid_not_null(self):
        sir = make_sir("not_null", "email")
        errors = validate_compatibility(sir)
        assert errors == []

    def test_unresolved_subject(self):
        sir = make_sir("not_null")
        sir.subject.resolved_column = None
        errors = validate_compatibility(sir)
        assert any(e.code == "unresolved_subject" for e in errors)

    def test_comparison_missing_object(self):
        sir = make_sir("column_comparison", operator=">")
        sir.object = None
        errors = validate_compatibility(sir)
        assert any(e.code == "unresolved_object" for e in errors)

    def test_missing_operator(self):
        sir = make_sir("column_comparison", object_col="b")
        sir.operator = None
        errors = validate_compatibility(sir)
        assert any(e.code == "missing_operator" for e in errors)

    def test_type_incompatibility(self):
        sir = make_sir("numeric_threshold", "name", operator=">=")
        types = {"name": "varchar"}
        errors = validate_compatibility(sir, column_data_types=types)
        assert any(e.code == "type_incompatible" for e in errors)

    def test_type_compatible(self):
        sir = make_sir("numeric_threshold", "price", operator=">=")
        types = {"price": "numeric"}
        errors = validate_compatibility(sir, column_data_types=types)
        assert errors == []

    def test_empty_value_list(self):
        sir = make_sir("value_in_list", constraints=[])
        errors = validate_compatibility(sir)
        assert any(e.code == "empty_value_list" for e in errors)

    def test_invalid_regex(self):
        sir = make_sir("regex_format", constraints=["[invalid"])
        errors = validate_compatibility(sir)
        assert any(e.code == "invalid_regex" for e in errors)

    def test_valid_regex(self):
        sir = make_sir("regex_format", constraints=[r"^\d{3}-\d{4}$"])
        errors = validate_compatibility(sir)
        assert errors == []

    def test_missing_regex_pattern(self):
        sir = make_sir("regex_format", constraints=[])
        errors = validate_compatibility(sir)
        assert any(e.code == "missing_regex_pattern" for e in errors)

    def test_composite_uniqueness_missing_columns(self):
        sir = make_sir("composite_uniqueness")
        sir.object = None
        errors = validate_compatibility(sir)
        assert any(e.code == "missing_composite_columns" for e in errors)

    def test_conditional_missing_conditions(self):
        sir = make_sir("conditional_rule")
        errors = validate_compatibility(sir)
        assert any(e.code == "missing_conditions" for e in errors)


# ══════════════════════════════════════
# 4. Compiler Tests — All Rule Types
# ══════════════════════════════════════


class TestCompilerAllTypes:
    def test_null_check(self):
        sir = make_sir("null_check", "status")
        resp = compiler.compile(make_request(sir))
        assert resp.status == CompilationStatus.SUCCESS
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "completeness"
        assert cfg.subtype == "null"
        assert cfg.config["condition"] == "IS NULL"

    def test_not_null(self):
        sir = make_sir("not_null", "email")
        resp = compiler.compile(make_request(sir))
        assert resp.status == CompilationStatus.SUCCESS
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "completeness"
        assert cfg.config["condition"] == "IS NOT NULL"

    def test_column_comparison(self):
        sir = make_sir(
            "column_comparison", "shipping_date", operator="greater_than", object_col="order_date"
        )
        resp = compiler.compile(make_request(sir))
        assert resp.status == CompilationStatus.SUCCESS
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "consistency"
        assert cfg.config["right_column"] == "order_date"
        assert cfg.config["operator"] == ">"

    def test_numeric_threshold_range(self):
        sir = make_sir("numeric_threshold", "price", operator="between", constraints=[0, 10000])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "validity"
        assert cfg.config["min_value"] == 0
        assert cfg.config["max_value"] == 10000

    def test_numeric_threshold_single(self):
        sir = make_sir("numeric_threshold", "quantity", operator=">=", constraints=[1])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.config["threshold_value"] == 1

    def test_date_comparison(self):
        sir = make_sir(
            "date_comparison", "end_date", operator="greater_than", object_col="start_date"
        )
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "consistency"
        assert cfg.subtype == "temporal"
        assert cfg.config["right_column"] == "start_date"

    def test_value_in_list(self):
        sir = make_sir("value_in_list", "status", constraints=["active", "inactive", "pending"])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "validity"
        assert cfg.config["allowed_values"] == ["active", "inactive", "pending"]

    def test_regex_format(self):
        sir = make_sir("regex_format", "email", constraints=[r"^[\w.]+@[\w.]+\.\w+$"])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "conformity"
        assert cfg.subtype == "regex"
        assert "pattern" in cfg.config

    def test_length_check_range(self):
        sir = make_sir("length_check", "zip_code", constraints=[5, 10])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "conformity"
        assert cfg.config["min_length"] == 5
        assert cfg.config["max_length"] == 10

    def test_uniqueness(self):
        sir = make_sir("uniqueness", "customer_id")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "uniqueness"
        assert cfg.subtype == "exact"

    def test_composite_uniqueness(self):
        sir = make_sir("composite_uniqueness", "first_name", object_col="last_name")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "uniqueness"
        assert cfg.subtype == "composite"
        assert "first_name" in cfg.config["columns"]
        assert "last_name" in cfg.config["columns"]

    def test_reference_lookup(self):
        sir = make_sir("reference_lookup", "dept_id", object_col="id", object_dataset="departments")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "validity"
        assert cfg.config["reference_column"] == "id"
        assert cfg.config["reference_dataset"] == "departments"

    def test_conditional_rule(self):
        cond = SIRCondition(
            field=SIREntity(raw_text="status", resolved_column="status"),
            operator="equals",
            value="active",
        )
        sir = make_sir("conditional_rule", "email", conditions=[cond])
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "completeness"
        assert cfg.subtype == "conditional"
        assert len(cfg.config["conditions"]) == 1
        assert cfg.config["conditions"][0]["field"] == "status"

    def test_arithmetic_comparison(self):
        sir = make_sir("arithmetic_comparison", "total", operator="equals", object_col="subtotal")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.check_type == "consistency"
        assert cfg.subtype == "formula"

    def test_unknown_rejected(self):
        make_sir.__wrapped__ if hasattr(make_sir, "__wrapped__") else make_sir
        s = StructuredIntermediateRepresentation(
            rule_type=RuleType.UNKNOWN,
            subject=SIREntity(raw_text="something", resolved_column="something"),
            confidence=0.3,
        )
        resp = compiler.compile(CompileRequest(resolved_rule=s))
        assert resp.status == CompilationStatus.UNSUPPORTED
        assert resp.rejection_reason is not None
        assert len(resp.fallback_suggestions) > 0


# ══════════════════════════════════════
# 5. Compiler Edge Cases
# ══════════════════════════════════════


class TestCompilerEdgeCases:
    def test_low_confidence_warning(self):
        sir = make_sir("not_null", confidence=0.5)
        resp = compiler.compile(make_request(sir))
        assert resp.status == CompilationStatus.PARTIAL
        assert any("Low parse confidence" in w for w in resp.warnings)

    def test_custom_severity_from_options(self):
        sir = make_sir("not_null")
        resp = compiler.compile(make_request(sir, options={"severity": "critical"}))
        cfg = resp.compiled_configs[0]
        assert cfg.severity == "critical"

    def test_custom_threshold_from_options(self):
        sir = make_sir("not_null")
        resp = compiler.compile(make_request(sir, options={"threshold_pass": 95}))
        cfg = resp.compiled_configs[0]
        assert cfg.config["threshold_pass"] == 95

    def test_canonical_rule_included(self):
        sir = make_sir("not_null", "email", "users")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.canonical_rule is not None
        assert cfg.canonical_rule["dimension"] == "completeness"
        assert "email" in cfg.canonical_rule["entity"]

    def test_rule_name_generated(self):
        sir = make_sir("uniqueness", "customer_id")
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert "uniqueness" in cfg.rule_name
        assert "customer_id" in cfg.rule_name

    def test_dataset_id_propagated(self):
        ds_id = str(uuid4())
        sir = make_sir("not_null", subject_dataset_id=ds_id)
        resp = compiler.compile(make_request(sir))
        cfg = resp.compiled_configs[0]
        assert cfg.dataset_id == ds_id

    def test_validation_errors_returned(self):
        sir = make_sir("column_comparison")
        sir.object = None
        sir.operator = None
        resp = compiler.compile(make_request(sir))
        assert resp.status == CompilationStatus.ERROR
        assert len(resp.validation_errors) >= 2

    def test_parse_warnings_propagated(self):
        sir = make_sir("not_null", confidence=0.6)
        sir.parse_warnings = ["Ambiguous subject reference"]
        resp = compiler.compile(make_request(sir))
        assert "Ambiguous subject reference" in resp.warnings

    def test_fallback_null_suggestion(self):
        s = StructuredIntermediateRepresentation(
            rule_type=RuleType.UNKNOWN,
            subject=SIREntity(raw_text="null values in email", resolved_column="email"),
            confidence=0.3,
        )
        resp = compiler.compile(CompileRequest(resolved_rule=s))
        assert any(fs.suggested_type == "not_null" for fs in resp.fallback_suggestions)

    def test_fallback_uniqueness_suggestion(self):
        s = StructuredIntermediateRepresentation(
            rule_type=RuleType.UNKNOWN,
            subject=SIREntity(raw_text="duplicate customer ids", resolved_column="cid"),
            confidence=0.3,
        )
        resp = compiler.compile(CompileRequest(resolved_rule=s))
        assert any(fs.suggested_type == "uniqueness" for fs in resp.fallback_suggestions)


# ══════════════════════════════════════
# 6. Endpoint Tests
# ══════════════════════════════════════


class TestEndpoint:
    def test_compile_endpoint_import(self):
        from app.api.v1.endpoints.rule_builder import compile_rule

        assert callable(compile_rule)

    def test_compile_endpoint_direct(self):
        from app.api.v1.endpoints.rule_builder import _compiler

        sir = make_sir("not_null", "email")
        req = make_request(sir)
        resp = _compiler.compile(req)
        assert resp.status == CompilationStatus.SUCCESS
        assert len(resp.compiled_configs) == 1
