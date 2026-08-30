"""
F128 P03 — Resolution and Proposal Schema Hardening Tests

Tests for:
- ResolutionEvidence typed model (replaces Dict[str, Any] on ResolveResponse)
- ResolutionEvidence backward-compat dict-like access (__contains__, __getitem__)
- ProposalPayload typed parsed_rule / resolved_rule (StructuredIntermediateRepresentation)
- ProposalPayload typed compiled_checks (list[CompiledCheckConfig])
- Coercion validators (dict → SIR, dict → CompiledCheckConfig)
- ProposalPayload legacy incomplete-dict backward compat
"""

import pytest
from app.schemas.nl_compiler import CompiledCheckConfig, GenericCheckConfig
from app.schemas.nl_rule_builder import (
    RuleType,
    SIREntity,
    StructuredIntermediateRepresentation,
)
from app.schemas.proposal import ProposalPayload
from app.schemas.resolution import (
    EntityResolution,
    ResolutionEvidence,
    ResolveResponse,
    SignalBreakdown,
)
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


def _make_entity_resolution() -> EntityResolution:
    return EntityResolution(raw_text="customer_id")


def _make_resolve_response(**overrides) -> ResolveResponse:
    return ResolveResponse(
        resolved_rule=_make_sir(),
        subject_resolution=_make_entity_resolution(),
        overall_confidence=0.8,
        **overrides,
    )


# ---------------------------------------------------------------------------
# ResolutionEvidence tests (FR-08)
# ---------------------------------------------------------------------------


def test_resolution_evidence_construction():
    """ResolutionEvidence constructs with typed fields."""
    signal = SignalBreakdown(signal_name="glossary_match", score=0.85, available=True)
    ev = ResolutionEvidence(
        subject_signals=[signal],
        glossary_contribution=0.85,
        metadata_contribution=0.5,
        notes=["Resolved via glossary term 'customer_id'"],
    )
    assert len(ev.subject_signals) == 1
    assert ev.subject_signals[0].score == 0.85
    assert ev.glossary_contribution == 0.85


def test_resolution_evidence_extra_fields_preserved():
    """ResolutionEvidence preserves legacy dict keys as extra fields (extra='allow')."""
    ev = ResolutionEvidence(
        subject_candidates_count=3,
        object_candidates_count=0,
        weights_used={"name": 0.5, "glossary": 0.3},
    )
    # Extra fields accessible via dict-like API
    assert ev["subject_candidates_count"] == 3
    assert ev["weights_used"]["name"] == 0.5


def test_resolution_evidence_contains_legacy_keys():
    """'key in resolution_evidence' works for backward compat (used in existing tests)."""
    ev = ResolutionEvidence(
        subject_candidates_count=5,
        weights_used={"name": 0.5},
    )
    assert "subject_candidates_count" in ev
    assert "weights_used" in ev
    assert "nonexistent_key" not in ev


def test_resolve_response_evidence_is_typed():
    """ResolveResponse.resolution_evidence is a ResolutionEvidence instance."""
    resp = _make_resolve_response(
        resolution_evidence={
            "subject_candidates_count": 2,
            "weights_used": {},
        }
    )
    assert isinstance(resp.resolution_evidence, ResolutionEvidence)
    # Legacy keys still accessible
    assert "subject_candidates_count" in resp.resolution_evidence


def test_resolve_response_evidence_default():
    """ResolveResponse.resolution_evidence defaults to empty ResolutionEvidence."""
    resp = _make_resolve_response()
    assert isinstance(resp.resolution_evidence, ResolutionEvidence)
    assert resp.resolution_evidence.subject_signals == []


# ---------------------------------------------------------------------------
# ProposalPayload typed fields tests (FR-09)
# ---------------------------------------------------------------------------


def test_proposal_payload_typed_parsed_rule():
    """ProposalPayload coerces a complete SIR dict to StructuredIntermediateRepresentation."""
    p = ProposalPayload(
        parsed_rule={
            "rule_type": "not_null",
            "subject": {"raw_text": "customer_id"},
            "confidence": 0.9,
        }
    )
    assert isinstance(p.parsed_rule, StructuredIntermediateRepresentation)
    assert p.parsed_rule.rule_type == RuleType.NOT_NULL


def test_proposal_payload_typed_resolved_rule():
    """ProposalPayload coerces resolved_rule dict to StructuredIntermediateRepresentation."""
    p = ProposalPayload(
        parsed_rule={
            "rule_type": "not_null",
            "subject": {"raw_text": "customer_id"},
            "confidence": 0.9,
        },
        resolved_rule={
            "rule_type": "not_null",
            "subject": {"raw_text": "customer_id", "resolved_column": "customer_id"},
            "confidence": 0.95,
        },
    )
    assert isinstance(p.resolved_rule, StructuredIntermediateRepresentation)
    assert p.resolved_rule.subject.resolved_column == "customer_id"


def test_proposal_payload_typed_compiled_checks():
    """ProposalPayload coerces compiled_checks list[dict] to list[CompiledCheckConfig]."""
    p = ProposalPayload(
        parsed_rule={
            "rule_type": "not_null",
            "subject": {"raw_text": "customer_id"},
            "confidence": 0.9,
        },
        compiled_checks=[
            {
                "check_type": "completeness",
                "subtype": "not_null",
                "rule_name": "completeness_not_null_customer_id",
                "config": {"check_dimension": "completeness", "columns": ["customer_id"]},
            }
        ],
    )
    assert p.compiled_checks is not None
    assert len(p.compiled_checks) == 1
    assert isinstance(p.compiled_checks[0], CompiledCheckConfig)
    assert p.compiled_checks[0].check_type == "completeness"


def test_proposal_payload_incomplete_sir_dict_passthrough():
    """Incomplete SIR dict (missing required fields) is kept as-is, not dropped."""
    p = ProposalPayload(
        parsed_rule={"rule_type": "not_null"},  # Missing subject and confidence
        parse_confidence=0.95,
    )
    # Should not raise — lenient coercion keeps the incomplete dict
    assert p.parsed_rule is not None
    assert p.parse_confidence == 0.95


def test_proposal_payload_sir_instance_accepted():
    """ProposalPayload accepts a SIR model instance directly."""
    sir = _make_sir()
    p = ProposalPayload(parsed_rule=sir)
    assert p.parsed_rule is sir or isinstance(p.parsed_rule, StructuredIntermediateRepresentation)


def test_proposal_payload_none_fields_allowed():
    """ProposalPayload can have None parsed_rule, resolved_rule, compiled_checks."""
    p = ProposalPayload(
        parsed_rule=None,
        resolved_rule=None,
        compiled_checks=None,
        parse_confidence=0.0,
    )
    assert p.parsed_rule is None
    assert p.compiled_checks is None


def test_proposal_payload_defaults():
    """ProposalPayload maintains backward-compat defaults."""
    p = ProposalPayload()
    assert p.glossary_matches == []
    assert p.resolution_evidence == {}
    assert p.parse_confidence == 0.0
    assert p.resolution_confidence == 0.0
