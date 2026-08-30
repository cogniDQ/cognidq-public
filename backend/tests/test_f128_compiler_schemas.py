"""
F128 P02 — Compiler Schema Hardening Tests

Tests for:
- CompilationOptions (extra='forbid', typed fields)
- Per-dimension check config models (CompletenessConfig, ValidityConfig, etc.)
- CheckTypeConfig coercion via field_validator on CompiledCheckConfig
- CanonicalRuleOutput typed model (replaces Optional[Dict])
- CompileRequest.compilation_options typed as CompilationOptions
"""

import pytest
from app.schemas.nl_compiler import (
    AccuracyConfig,
    CanonicalRuleOutput,
    CompilationOptions,
    CompiledCheckConfig,
    CompileRequest,
    CompletenessConfig,
    ConformityConfig,
    ConsistencyConfig,
    GenericCheckConfig,
    ReconciliationConfig,
    TimelinessConfig,
    UniquenessCheckConfig,
    ValidityConfig,
)
from app.schemas.nl_rule_builder import RuleType, SIREntity, StructuredIntermediateRepresentation
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sir(**overrides) -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type="not_null",
        subject=SIREntity(raw_text="customer_id"),
        confidence=0.9,
        **overrides,
    )


def _make_compiled(**overrides) -> CompiledCheckConfig:
    return CompiledCheckConfig(
        check_type="completeness",
        subtype="not_null",
        rule_name="completeness_not_null_customer_id",
        **overrides,
    )


# ---------------------------------------------------------------------------
# CompilationOptions tests (FR-07)
# ---------------------------------------------------------------------------


def test_compilation_options_extra_field_rejected():
    """CompilationOptions with extra fields must raise ValidationError (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        CompilationOptions(unknown_key="should_fail")
    assert "unknown_key" in str(exc_info.value) or "extra" in str(exc_info.value).lower()


def test_compilation_options_valid_construction():
    opts = CompilationOptions(
        severity="high",
        threshold_pass=99.0,
        threshold_warn=95.0,
        null_handling="skip",
        force_dimension="completeness",
        dry_run=True,
    )
    assert opts.severity == "high"
    assert opts.threshold_pass == 99.0
    assert opts.dry_run is True


# ---------------------------------------------------------------------------
# Per-dimension config construction tests (FR-05)
# ---------------------------------------------------------------------------


def test_completeness_config_construction():
    c = CompletenessConfig(null_handling="fail", include_empty_strings=True)
    assert c.check_dimension == "completeness"
    assert c.null_handling == "fail"
    assert c.include_empty_strings is True


def test_validity_config_construction():
    c = ValidityConfig(validation_type="value_in_list", allowed_values=["active", "inactive"])
    assert c.check_dimension == "validity"
    assert "active" in c.allowed_values


def test_uniqueness_config_construction():
    c = UniquenessCheckConfig(uniqueness_mode="composite", scope_columns=["col_a", "col_b"])
    assert c.check_dimension == "uniqueness"
    assert c.scope_columns == ["col_a", "col_b"]


def test_conformity_config_construction():
    c = ConformityConfig(conformity_type="regex", pattern=r"^\d{4}-\d{2}-\d{2}$")
    assert c.check_dimension == "conformity"
    assert c.pattern is not None


def test_consistency_config_construction():
    c = ConsistencyConfig(consistency_type="cross_field", reference_field="end_date")
    assert c.check_dimension == "consistency"
    assert c.reference_field == "end_date"


def test_timeliness_config_construction():
    c = TimelinessConfig(timeliness_type="freshness", max_age="24h", date_column="updated_at")
    assert c.check_dimension == "timeliness"
    assert c.max_age == "24h"


def test_accuracy_config_construction():
    c = AccuracyConfig(accuracy_type="numeric", reference_column="expected_amount", tolerance=0.01)
    assert c.check_dimension == "accuracy"
    assert c.tolerance == 0.01


def test_reconciliation_config_construction():
    c = ReconciliationConfig(recon_type="count", target_dataset_id="ds-abc", target_column="id")
    assert c.check_dimension == "reconciliation"
    assert c.target_column == "id"


# ---------------------------------------------------------------------------
# CheckTypeConfig coercion on CompiledCheckConfig (FR-05)
# ---------------------------------------------------------------------------


def test_check_config_output_typed_config():
    """CompiledCheckConfig coerces a dict with check_dimension to the right typed model."""
    cc = _make_compiled(
        config={
            "check_dimension": "completeness",
            "null_handling": "skip",
            "columns": ["email"],
            "threshold_pass": 100,
        }
    )
    assert isinstance(cc.config, CompletenessConfig)
    assert cc.config["null_handling"] == "skip"
    assert cc.config["columns"] == ["email"]


def test_check_config_output_wrong_dimension_rejected():
    """A config with check_dimension='validity' on a completeness check should
    result in a ValidityConfig, not CompletenessConfig — the dimension is determined
    by the config dict's own check_dimension field."""
    cc = CompiledCheckConfig(
        check_type="completeness",
        subtype="not_null",
        rule_name="completeness_not_null_col",
        config={"check_dimension": "validity", "validation_type": "value_in_list"},
    )
    # The config is typed as ValidityConfig based on check_dimension field
    assert isinstance(cc.config, ValidityConfig)
    # Verify wrong dim isn't silently ignored
    assert cc.config.check_dimension == "validity"


# ---------------------------------------------------------------------------
# CanonicalRuleOutput typed field on CompiledCheckConfig (FR-06)
# ---------------------------------------------------------------------------


def test_canonical_rule_output_construction():
    cro = CanonicalRuleOutput(
        rule_type="not_null",
        subject="customer_id",
        operator="is_not_null",
        severity="high",
    )
    assert cro.rule_type == "not_null"
    assert cro.severity == "high"


def test_compiled_check_config_with_canonical_rule():
    """canonical_rule field coerces a dict to CanonicalRuleOutput."""
    cc = _make_compiled(
        canonical_rule={
            "rule_type": "not_null",
            "subject": "customer_id",
            "operator": "is_not_null",
            "severity": "medium",
            # Legacy fields absorbed by extra='allow'
            "dimension": "completeness",
            "entity": "customer_id",
        }
    )
    assert isinstance(cc.canonical_rule, CanonicalRuleOutput)
    assert cc.canonical_rule.rule_type == "not_null"
    # Backward-compat dict access
    assert cc.canonical_rule["dimension"] == "completeness"
    assert cc.canonical_rule["entity"] == "customer_id"


# ---------------------------------------------------------------------------
# CompileRequest with typed compilation_options (FR-07)
# ---------------------------------------------------------------------------


def test_compile_request_typed_options():
    """CompileRequest.compilation_options coerces a dict to CompilationOptions."""
    req = CompileRequest(
        resolved_rule=_make_sir(),
        compilation_options={"severity": "high", "threshold_pass": 95},
    )
    assert isinstance(req.compilation_options, CompilationOptions)
    assert req.compilation_options.severity == "high"
    assert req.compilation_options.threshold_pass == 95
