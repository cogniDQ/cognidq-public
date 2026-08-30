"""
F126 Decomposition Tests (P02)

Tests for NLRuleParserService._detect_and_decompose — compound obligation detection
and decomposition into atomic SIRs.
"""

from unittest.mock import patch

import pytest
from app.schemas.nl_rule_builder import (
    RuleType,
    SIRCondition,
    SIREntity,
    StructuredIntermediateRepresentation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service():
    """Return an NLRuleParserService instance without a real API key."""
    with patch("app.services.nl_rule_builder.parser.AsyncOpenAI"):
        from app.services.nl_rule_builder.parser import NLRuleParserService

        return NLRuleParserService()


def _minimal_sir(subject: str = "email") -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=SIREntity(raw_text=subject),
        confidence=0.9,
    )


def _obligation_raw(subject: str, rule_type: str = "not_null") -> dict:
    return {
        "rule_type": rule_type,
        "subject": {"raw_text": subject},
        "operator": None,
        "object": None,
        "scope": {"dataset_hint": None, "domain_hint": None, "source_system_hint": None},
        "conditions": [],
        "constraints": [],
        "confidence": 0.9,
        "requires_disambiguation": False,
        "parse_warnings": [],
        "clarifying_questions": [],
    }


# ---------------------------------------------------------------------------
# test_and_2_obligations — AC-P02-001
# ---------------------------------------------------------------------------


def test_and_2_obligations():
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "AND",
        "obligations": [
            _obligation_raw("email"),
            _obligation_raw("phone"),
        ],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is True
    assert result.obligation_logic == "AND"
    assert len(result.obligations) == 2


# ---------------------------------------------------------------------------
# test_or_different_columns — AC-P02-001
# ---------------------------------------------------------------------------


def test_or_different_columns():
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "OR",
        "obligations": [
            _obligation_raw("col_a"),
            _obligation_raw("col_b"),
            _obligation_raw("col_c"),
        ],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is True
    assert result.obligation_logic == "OR"
    assert len(result.obligations) == 3


# ---------------------------------------------------------------------------
# test_or_same_column_not_compound — AC-P02-002
# ---------------------------------------------------------------------------


def test_or_same_column_not_compound():
    """LLM returns is_compound=False for same-column OR (value_in_list) — parser preserves."""
    svc = _make_service()
    sir = _minimal_sir("status")
    raw_output = {"is_compound": False}  # LLM correctly identified as single obligation
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is False
    assert result.obligations == []


# ---------------------------------------------------------------------------
# test_semicolon_separator
# ---------------------------------------------------------------------------


def test_semicolon_separator():
    """Two obligations from semicolon-separated input."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "AND",
        "obligations": [
            _obligation_raw("email"),
            _obligation_raw("phone"),
        ],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert len(result.obligations) == 2


# ---------------------------------------------------------------------------
# test_if_then_single_obligation
# ---------------------------------------------------------------------------


def test_if_then_single_obligation():
    """IF-THEN is single obligation — is_compound=False, conditions populated."""
    svc = _make_service()
    sir = _minimal_sir("email")
    sir.conditions = [
        SIRCondition(
            field=SIREntity(raw_text="status"),
            operator="equals",
            value="active",
        )
    ]
    raw_output = {"is_compound": False}
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is False
    assert len(result.conditions) == 1


# ---------------------------------------------------------------------------
# test_if_then_else_two_obligations
# ---------------------------------------------------------------------------


def test_if_then_else_two_obligations():
    """IF-THEN-ELSE → is_compound=True, 2 obligations."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "INDEPENDENT",
        "obligations": [
            _obligation_raw("col_a"),  # THEN branch
            _obligation_raw("col_b"),  # ELSE branch
        ],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is True
    assert result.obligation_logic == "INDEPENDENT"
    assert len(result.obligations) == 2


# ---------------------------------------------------------------------------
# test_obligation_count_exactly_10
# ---------------------------------------------------------------------------


def test_obligation_count_exactly_10():
    """Exactly 10 obligations — accepted without warning."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "AND",
        "obligations": [_obligation_raw(f"col_{i}") for i in range(10)],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is True
    assert len(result.obligations) == 10
    assert not any("Too many" in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# test_obligation_count_11_rejected — AC-P02-003
# ---------------------------------------------------------------------------


def test_obligation_count_11_rejected():
    """11 obligations → requires_disambiguation=True + warning, obligations NOT set."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "AND",
        "obligations": [_obligation_raw(f"col_{i}") for i in range(11)],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.requires_disambiguation is True
    assert any("Too many" in w for w in result.parse_warnings)
    assert result.obligations == []


# ---------------------------------------------------------------------------
# test_empty_obligations_fallback — AC-P02-004
# ---------------------------------------------------------------------------


def test_empty_obligations_fallback():
    """is_compound=True but obligations=[] → fallback to single obligation, warning added."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {"is_compound": True, "obligations": []}
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.is_compound is False
    assert result.obligations == []
    assert any("Compound marker" in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# test_unknown_obligation_logic_defaults_to_independent
# ---------------------------------------------------------------------------


def test_unknown_obligation_logic_defaults_to_independent():
    """Unknown obligation_logic value → INDEPENDENT + warning."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "EXCLUSIVE_OR",
        "obligations": [_obligation_raw("a"), _obligation_raw("b")],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    assert result.obligation_logic == "INDEPENDENT"
    assert any("Unknown obligation logic" in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# test_decomposition_summary_always_present — AC-P02-010
# ---------------------------------------------------------------------------


def test_decomposition_summary_count_reflected():
    """obligations list is populated correctly — caller builds decomposition_summary from it."""
    svc = _make_service()
    sir = _minimal_sir()
    raw_output = {
        "is_compound": True,
        "obligation_logic": "AND",
        "obligations": [_obligation_raw("col_x"), _obligation_raw("col_y")],
    }
    result = svc._detect_and_decompose(sir, raw_output)
    # Decomposition summary is built by parse_rule, but we can verify the data is right
    assert len(result.obligations) == 2
    assert result.obligations[0].subject.raw_text == "col_x"
    assert result.obligations[1].subject.raw_text == "col_y"
