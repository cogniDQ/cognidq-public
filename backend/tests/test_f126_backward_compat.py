"""
F126 Backward Compatibility Tests (P01)

Verifies that all pre-F126 SIR, SIRCondition, CompiledCheckConfig, and
ParseRuleResponse behaviors are preserved after schema extensions.
"""

import pytest
from app.schemas.nl_compiler import CompiledCheckConfig
from app.schemas.nl_rule_builder import (
    ParseRuleResponse,
    RuleType,
    SIRCondition,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_sir_entity(text: str = "email") -> SIREntity:
    return SIREntity(raw_text=text)


def _minimal_sir() -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=_minimal_sir_entity("email"),
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# AC-P01-001 / AC-P01-002 — SIR and SIRCondition default fields
# ---------------------------------------------------------------------------


def test_sir_default_fields_backward_compat():
    """SIR instantiated without new F126 fields — all defaults are pre-F126 values."""
    sir = _minimal_sir()
    assert sir.is_compound is False
    assert sir.obligation_logic is None
    assert sir.obligations == []


def test_condition_default_fields_backward_compat():
    """SIRCondition instantiated without new F126 fields — defaults preserved."""
    cond = SIRCondition(
        field=_minimal_sir_entity("status"),
        operator="equals",
        value="active",
    )
    assert cond.logic_operator is None
    assert cond.nested_conditions == []


# ---------------------------------------------------------------------------
# AC-P01-003 — CompiledCheckConfig backward compat
# ---------------------------------------------------------------------------


def test_compiled_check_config_backward_compat():
    """CompiledCheckConfig serialised without group_id fields — no breakage."""
    config = CompiledCheckConfig(
        check_type="completeness",
        subtype="null",
        rule_name="email_not_null",
        severity="high",
    )
    assert config.obligation_group_id is None
    assert config.obligation_logic is None
    data = config.model_dump()
    assert "obligation_group_id" in data
    assert data["obligation_group_id"] is None


# ---------------------------------------------------------------------------
# AC-P01-004 — ParseRuleResponse with decomposition_summary=None
# ---------------------------------------------------------------------------


def test_single_obligation_format_unchanged():
    """ParseRuleResponse for single-obligation — shape identical to pre-F126 (new field is null)."""
    response = ParseRuleResponse(
        request_id="test-req-001",
        status="parsed",
        parsed_rule=_minimal_sir(),
    )
    assert response.decomposition_summary is None
    data = response.model_dump()
    # Key fields that pre-F126 consumers rely on must still be present
    assert "request_id" in data
    assert "status" in data
    assert "parsed_rule" in data
    assert "check_configs" in data


# ---------------------------------------------------------------------------
# AC-P01-010 — Single obligation flag
# ---------------------------------------------------------------------------


def test_single_obligation_is_compound_false():
    """A plain SIR has is_compound=False and empty obligations list."""
    sir = _minimal_sir()
    assert sir.is_compound is False
    assert sir.obligations == []
    # Serialise + deserialise round-trip
    restored = StructuredIntermediateRepresentation.model_validate(sir.model_dump())
    assert restored.is_compound is False
    assert restored.obligations == []
