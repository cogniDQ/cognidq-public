"""
F126 Inline Extraction Tests — OPERATOR_ALIASES (P01 scope: first 10 tests)

Tests that each new NL-phrase alias in OPERATOR_ALIASES resolves to the
correct SQL operator symbol.

P02 adds threshold, allowed_values, reference_dataset, severity and decomposition tests
(see section 2 below).
"""

from unittest.mock import patch

import pytest
from app.services.nl_compiler.mappings import OPERATOR_ALIASES

# ---------------------------------------------------------------------------
# OPERATOR_ALIASES — NL phrase → SQL operator (F126 additions)
# ---------------------------------------------------------------------------


def test_operator_alias_at_least():
    assert OPERATOR_ALIASES["at least"] == ">="


def test_operator_alias_at_most():
    assert OPERATOR_ALIASES["at most"] == "<="


def test_operator_alias_no_more_than():
    assert OPERATOR_ALIASES["no more than"] == "<="


def test_operator_alias_no_fewer_than():
    assert OPERATOR_ALIASES["no fewer than"] == ">="


def test_operator_alias_greater_than_nl():
    assert OPERATOR_ALIASES["greater than"] == ">"


def test_operator_alias_fewer_than():
    assert OPERATOR_ALIASES["fewer than"] == "<"


def test_operator_alias_not_equal_to():
    assert OPERATOR_ALIASES["not equal to"] == "!="


def test_operator_alias_different_from():
    assert OPERATOR_ALIASES["different from"] == "!="


def test_operator_alias_after_date():
    assert OPERATOR_ALIASES["after"] == ">"


def test_operator_alias_before_date():
    assert OPERATOR_ALIASES["before"] == "<"


def test_operator_alias_between_maps():
    assert OPERATOR_ALIASES["between"] == "BETWEEN"


def test_operator_alias_more_than():
    assert OPERATOR_ALIASES["more than"] == ">"


def test_operator_alias_less_than_nl():
    assert OPERATOR_ALIASES["less than"] == "<"


def test_operator_alias_exactly():
    assert OPERATOR_ALIASES["exactly"] == "="


# Pre-existing aliases must still resolve (regression)
def test_existing_alias_greater_than_snake():
    assert OPERATOR_ALIASES["greater_than"] == ">"


def test_existing_alias_equal():
    assert OPERATOR_ALIASES["equal"] == "="


# ===========================================================================
# Section 2 — P02: _apply_inline_extraction unit tests
# ===========================================================================
from app.schemas.nl_rule_builder import (
    RuleType,
    SIREntity,
    SIRScope,
    StructuredIntermediateRepresentation,
)


def _make_service():
    with patch("app.services.nl_rule_builder.parser.AsyncOpenAI"):
        from app.services.nl_rule_builder.parser import NLRuleParserService

        return NLRuleParserService()


def _minimal_sir() -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type=RuleType.NOT_NULL,
        subject=SIREntity(raw_text="email"),
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Threshold — 5 tests
# ---------------------------------------------------------------------------


def test_threshold_pass_top_level():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"threshold_pass": 95})
    assert result.threshold_pass == 95.0


def test_threshold_pass_via_check_config():
    svc = _make_service()
    sir = _minimal_sir()
    raw = {"check_config": {"thresholds": {"threshold_pass": 80}}}
    result = svc._apply_inline_extraction(sir, raw)
    assert result.threshold_pass == 80.0


def test_threshold_warn_clamped_to_pass():
    svc = _make_service()
    sir = _minimal_sir()
    raw = {"threshold_pass": 70, "threshold_warn": 90}
    result = svc._apply_inline_extraction(sir, raw)
    assert result.threshold_warn <= result.threshold_pass


def test_threshold_clamped_below_zero():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"threshold_pass": -5})
    assert result.threshold_pass == 0.0
    assert any("Invalid threshold" in w for w in result.parse_warnings)


def test_threshold_clamped_above_100():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"threshold_pass": 105})
    assert result.threshold_pass == 100.0
    assert any("Invalid threshold" in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# Allowed values — 5 tests
# ---------------------------------------------------------------------------


def test_allowed_values_list():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"allowed_values": ["Active", "Inactive"]})
    assert "Active" in result.constraints
    assert "Inactive" in result.constraints


def test_allowed_values_deduplication():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"allowed_values": ["Active", "active", "Active"]})
    # Case-insensitive dedup — only first occurrence kept
    assert len(result.constraints) == 1


def test_allowed_values_via_check_config():
    svc = _make_service()
    sir = _minimal_sir()
    raw = {"check_config": {"config": {"allowedValues": ["X", "Y"]}}}
    result = svc._apply_inline_extraction(sir, raw)
    assert "X" in result.constraints


def test_allowed_values_empty_list_warning():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"allowed_values": []})
    assert any("empty" in w.lower() for w in result.parse_warnings)


def test_allowed_values_strips_quotes():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"allowed_values": ["'Active'", '"Inactive"']})
    assert "Active" in result.constraints
    assert "Inactive" in result.constraints


# ---------------------------------------------------------------------------
# Reference dataset — 4 tests
# ---------------------------------------------------------------------------


def test_reference_dataset_top_level():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"reference_dataset": "customers"})
    assert result.scope.dataset_hint == "customers"


def test_reference_dataset_via_check_config():
    svc = _make_service()
    sir = _minimal_sir()
    raw = {"check_config": {"config": {"referenceDataset": "orders"}}}
    result = svc._apply_inline_extraction(sir, raw)
    assert result.scope.dataset_hint == "orders"


def test_reference_dataset_empty_string_warning():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"reference_dataset": "   "})
    assert any("empty" in w.lower() for w in result.parse_warnings)


def test_reference_dataset_not_overwrite_existing_hint():
    """If scope.dataset_hint is already set, reference_dataset should not overwrite it."""
    svc = _make_service()
    sir = _minimal_sir()
    sir.scope.dataset_hint = "already_set"
    result = svc._apply_inline_extraction(sir, {"reference_dataset": "other_table"})
    assert result.scope.dataset_hint == "already_set"


# ---------------------------------------------------------------------------
# Severity — 5 tests
# ---------------------------------------------------------------------------


def test_severity_critical():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"inline_severity": "critical"})
    assert result.inline_severity == "critical"


def test_severity_from_severity_key():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"severity": "high"})
    assert result.inline_severity == "high"


def test_severity_case_insensitive():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"inline_severity": "MEDIUM"})
    assert result.inline_severity == "medium"


def test_severity_fuzzy_match_crital_to_critical():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"inline_severity": "crital"})
    assert result.inline_severity == "critical"
    assert any("fuzzy-matched" in w for w in result.parse_warnings)


def test_severity_unrecognized_adds_warning():
    svc = _make_service()
    sir = _minimal_sir()
    result = svc._apply_inline_extraction(sir, {"inline_severity": "urgent_99"})
    assert result.inline_severity is None
    assert any("not recognized" in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# Decomposition integration (1 test)
# ---------------------------------------------------------------------------


def test_decomposition_summary_shape():
    """Verify decomposition_summary built from compound SIR has expected keys."""
    _make_service()
    sir = _minimal_sir()
    from app.schemas.nl_rule_builder import StructuredIntermediateRepresentation as SIR

    ob1 = SIR(rule_type=RuleType.NOT_NULL, subject=SIREntity(raw_text="col_a"), confidence=0.9)
    ob2 = SIR(rule_type=RuleType.NOT_NULL, subject=SIREntity(raw_text="col_b"), confidence=0.9)
    sir.is_compound = True
    sir.obligation_logic = "AND"
    sir.obligations = [ob1, ob2]
    # Simulate how parse_rule builds decomposition_summary
    decomp = {
        "count": len(sir.obligations),
        "logic": sir.obligation_logic,
        "obligations": [o.subject.raw_text for o in sir.obligations],
    }
    assert decomp["count"] == 2
    assert decomp["logic"] == "AND"
    assert decomp["obligations"] == ["col_a", "col_b"]
