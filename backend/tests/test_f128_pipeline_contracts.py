"""
F128 P04 — Pipeline Integration Tests

End-to-end contract tests validating that the full NL Rule Builder pipeline
works correctly with the F128 typed schemas across all four stages:
Parse → Resolve → Compile → Propose
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.schemas.nl_compiler import (
    BaseCheckConfig,
    CanonicalRuleOutput,
    CompilationOptions,
    CompilationStatus,
    CompiledCheckConfig,
    CompileRequest,
    CompileResponse,
    CompletenessConfig,
)
from app.schemas.nl_rule_builder import (
    DecompositionSummary,
    RuleType,
    SIRCondition,
    SIREntity,
    StructuredIntermediateRepresentation,
)
from app.schemas.proposal import ProposalPayload
from app.schemas.resolution import (
    EntityResolution,
    ResolutionEvidence,
    ResolveRequest,
    ResolveResponse,
)
from app.services.nl_compiler.compiler import NLRuleCompiler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sir(**overrides) -> StructuredIntermediateRepresentation:
    defaults = dict(
        rule_type="not_null",
        subject=SIREntity(raw_text="customer_id"),
        confidence=0.9,
    )
    defaults.update(overrides)
    return StructuredIntermediateRepresentation(**defaults)


def _make_resolved_sir(**overrides) -> StructuredIntermediateRepresentation:
    """Make a SIR with resolved subject (needed for compiler)."""
    defaults = dict(
        rule_type="not_null",
        subject=SIREntity(
            raw_text="customer_id",
            resolved_column="customer_id",
            resolved_dataset="customers",
            dataset_id="ds-001",
        ),
        confidence=0.9,
    )
    defaults.update(overrides)
    return StructuredIntermediateRepresentation(**defaults)


def _compile(sir: StructuredIntermediateRepresentation, **opts) -> CompileResponse:
    compiler = NLRuleCompiler()
    request = CompileRequest(resolved_rule=sir, compilation_options=opts)
    return compiler.compile(request)


# ---------------------------------------------------------------------------
# Stage 1: Parse / SIR validation tests (P01 contracts in integration context)
# ---------------------------------------------------------------------------


def test_sir_validation_normalizes_rule_type_from_llm_dict():
    """SIR auto-normalizes uppercase rule_type from LLM output."""
    sir = StructuredIntermediateRepresentation(
        **{
            "rule_type": "NOT_NULL",  # LLM often outputs uppercase
            "subject": {"raw_text": "email"},
            "confidence": 0.88,
        }
    )
    assert sir.rule_type == RuleType.NOT_NULL
    assert sir.rule_type.value == "not_null"


def test_sir_validation_clamps_confidence():
    """SIR clamps out-of-range confidence values rather than rejecting."""
    sir_high = StructuredIntermediateRepresentation(
        **{
            "rule_type": "not_null",
            "subject": {"raw_text": "email"},
            "confidence": 1.5,
        }
    )
    assert sir_high.confidence == 1.0

    sir_low = StructuredIntermediateRepresentation(
        **{
            "rule_type": "not_null",
            "subject": {"raw_text": "email"},
            "confidence": -0.1,
        }
    )
    assert sir_low.confidence == 0.0


def test_sir_rejects_nested_condition_value():
    """SIRCondition.value rejects dicts (LLM hallucination guard)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SIRCondition(
            field=SIREntity(raw_text="status"),
            operator="=",
            value={"nested": "object"},  # Invalid
        )


def test_decompose_returns_typed_decomposition_summary():
    """DecompositionSummary is a proper Pydantic model (not dict)."""
    ds = DecompositionSummary(
        count=1,
        logic=None,
        obligations=["customer_id must not be null"],
    )
    assert isinstance(ds, DecompositionSummary)
    assert ds.count == 1
    # model_dump returns a dict with typed values
    d = ds.model_dump()
    assert isinstance(d, dict)
    assert d["count"] == 1


def test_decompose_compound_sir_count_and_logic():
    """DecompositionSummary correctly captures compound rule decomposition."""
    ds = DecompositionSummary(
        count=2,
        logic="AND",
        obligations=["email must not be null", "phone must not be null"],
    )
    assert ds.count == 2
    assert ds.logic == "AND"
    assert len(ds.obligations) == 2


# ---------------------------------------------------------------------------
# Stage 2: Resolve — ResolutionEvidence integration
# ---------------------------------------------------------------------------


def test_resolve_returns_typed_resolution_evidence():
    """ResolveResponse.resolution_evidence is a typed ResolutionEvidence instance."""
    resp = ResolveResponse(
        resolved_rule=_make_sir(),
        subject_resolution=EntityResolution(raw_text="customer_id"),
        resolution_evidence={
            "subject_candidates_count": 3,
            "weights_used": {"name": 0.5},
        },
    )
    assert isinstance(resp.resolution_evidence, ResolutionEvidence)


def test_resolve_evidence_has_subject_signals():
    """ResolutionEvidence can carry typed SignalBreakdown list."""
    from app.schemas.resolution import SignalBreakdown

    ev = ResolutionEvidence(
        subject_signals=[SignalBreakdown(signal_name="name_match", score=0.9, available=True)],
        glossary_contribution=0.7,
    )
    assert len(ev.subject_signals) == 1
    assert ev.subject_signals[0].signal_name == "name_match"
    assert ev.glossary_contribution == 0.7


# ---------------------------------------------------------------------------
# Stage 3: Compile — CheckTypeConfig integration
# ---------------------------------------------------------------------------


def test_compile_returns_typed_check_config():
    """NLRuleCompiler returns CompiledCheckConfig with typed config model."""
    sir = _make_resolved_sir()
    response = _compile(sir)
    assert response.status in (CompilationStatus.SUCCESS, CompilationStatus.PARTIAL)
    assert len(response.compiled_configs) == 1
    cfg = response.compiled_configs[0]
    assert isinstance(cfg.config, BaseCheckConfig)


def test_compile_completeness_config_fields():
    """Completeness rule produces CompletenessConfig with expected fields."""
    sir = _make_resolved_sir()
    response = _compile(sir)
    cfg = response.compiled_configs[0]
    assert cfg.check_type == "completeness"
    # Config supports dict-like access for backward compat
    assert cfg.config["columns"] == ["customer_id"]
    assert cfg.config["check_dimension"] == "completeness"


def test_compile_compound_rule_typed_configs():
    """Compound rule compiles to multiple CompiledCheckConfig instances."""
    from app.schemas.nl_rule_builder import RuleType

    obligation1 = StructuredIntermediateRepresentation(
        rule_type="not_null",
        subject=SIREntity(
            raw_text="email",
            resolved_column="email",
            resolved_dataset="users",
        ),
        confidence=0.9,
    )
    obligation2 = StructuredIntermediateRepresentation(
        rule_type="not_null",
        subject=SIREntity(
            raw_text="phone",
            resolved_column="phone",
            resolved_dataset="users",
        ),
        confidence=0.85,
    )
    compound_sir = StructuredIntermediateRepresentation(
        rule_type="not_null",
        subject=SIREntity(raw_text="contact"),
        confidence=0.8,
        is_compound=True,
        obligation_logic="AND",
        obligations=[obligation1, obligation2],
    )
    response = _compile(compound_sir)
    assert len(response.compiled_configs) == 2
    for cfg in response.compiled_configs:
        assert isinstance(cfg.config, BaseCheckConfig)


# ---------------------------------------------------------------------------
# Stage 4: Proposal — typed ProposalPayload integration
# ---------------------------------------------------------------------------


def test_proposal_payload_contains_typed_sir():
    """ProposalPayload coerces full SIR dict to typed SIR on construction."""
    sir = _make_sir()
    p = ProposalPayload(
        parsed_rule=sir.model_dump(),
        parse_confidence=0.9,
    )
    assert isinstance(p.parsed_rule, StructuredIntermediateRepresentation)
    assert p.parsed_rule.rule_type == RuleType.NOT_NULL


def test_proposal_payload_contains_typed_compiled_checks():
    """ProposalPayload coerces compiled_checks list[dict] to list[CompiledCheckConfig]."""
    compiler = NLRuleCompiler()
    sir = _make_resolved_sir()
    response = compiler.compile(CompileRequest(resolved_rule=sir))
    # Simulate how the proposal engine serializes compiled configs
    compiled_dicts = [c.model_dump() for c in response.compiled_configs]

    p = ProposalPayload(
        parsed_rule=sir.model_dump(),
        compiled_checks=compiled_dicts,
    )
    assert p.compiled_checks is not None
    assert len(p.compiled_checks) > 0
    assert isinstance(p.compiled_checks[0], CompiledCheckConfig)


def test_proposal_json_round_trip_preserves_sir():
    """ProposalPayload.model_dump(mode='json') produces JSON-serializable output
    that can be round-tripped back to ProposalPayload."""
    sir = _make_sir()
    p_original = ProposalPayload(
        parsed_rule=sir,
        parse_confidence=0.9,
        resolution_confidence=0.85,
    )
    # Serialize to JSON-safe dict
    payload_dict = p_original.model_dump(mode="json")
    json_str = json.dumps(payload_dict)  # Must not raise

    # Deserialize back
    payload_loaded = json.loads(json_str)
    p_restored = ProposalPayload(**payload_loaded)
    assert isinstance(p_restored.parsed_rule, StructuredIntermediateRepresentation)
    assert p_restored.parse_confidence == 0.9


def test_full_pipeline_parse_to_compile_no_type_errors():
    """Full parse → compile chain with typed schemas produces no TypeError or AttributeError."""
    # Stage 1: Construct SIR (simulating parser output)
    sir = _make_resolved_sir()

    # Stage 3: Compile
    response = _compile(sir)
    assert response.status != CompilationStatus.ERROR
    cfg = response.compiled_configs[0]

    # Verify no type errors on typed field access
    assert isinstance(cfg.config, BaseCheckConfig)
    assert isinstance(cfg.canonical_rule, CanonicalRuleOutput)
    assert cfg.canonical_rule.rule_type == "not_null"
    assert cfg.canonical_rule.severity == "medium"


def test_backward_compatibility_existing_fixtures():
    """Verify that dict-based construction still works for existing test fixture patterns."""
    # This pattern is used in many existing test_nl_compiler tests
    cfg = CompiledCheckConfig(
        check_type="completeness",
        subtype="not_null",
        rule_name="completeness_not_null_email",
        config={
            "check_dimension": "completeness",
            "columns": ["email"],
            "threshold_pass": 100,
            "threshold_warn": 95,
            "null_handling": "skip",
            "check_mode": "null",
            "condition": "IS NOT NULL",
        },
        canonical_rule={
            "dimension": "completeness",
            "entity": "schema.email",
            "condition": "email IS NOT NULL",
            "expectation": "100%",
            "severity": "medium",
        },
    )
    # Dict-like access still works
    assert cfg.config["columns"] == ["email"]
    assert cfg.config["check_mode"] == "null"
    assert cfg.canonical_rule["dimension"] == "completeness"

    # Typed access also works
    assert isinstance(cfg.config, CompletenessConfig)
    assert isinstance(cfg.canonical_rule, CanonicalRuleOutput)
