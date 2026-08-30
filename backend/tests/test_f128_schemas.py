"""
F128 P01 — SIR Schema Hardening Tests

Tests for:
- ConditionValue typed union (rejects dicts and nested lists)
- SIRCondition.nested_conditions depth validator (max 3)
- SIRConstraint discriminated union variants
- StructuredIntermediateRepresentation rule_type normalization + confidence clamping
- ParseRuleResponse.decomposition_summary typed as DecompositionSummary
"""

import pytest
from app.schemas.nl_rule_builder import (
    ClarifyingQuestion,
    DecompositionSummary,
    GenericConstraint,
    LengthConstraint,
    ParseRuleResponse,
    RangeConstraint,
    RegexConstraint,
    RuleType,
    SIRCondition,
    SIREntity,
    StructuredIntermediateRepresentation,
    ValueInListConstraint,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(text: str = "customer_id") -> SIREntity:
    return SIREntity(raw_text=text)


def _make_base_sir(**overrides) -> dict:
    """Return a minimal valid SIR payload dict."""
    return {
        "rule_type": "not_null",
        "subject": {"raw_text": "customer_id"},
        "confidence": 0.9,
        **overrides,
    }


def _make_condition(value=None, nested: list | None = None) -> SIRCondition:
    """Build a SIRCondition with a given value and optional nested_conditions."""
    return SIRCondition(
        field=_make_entity(),
        operator="=",
        value=value if value is not None else "active",
        nested_conditions=nested or [],
    )


# ---------------------------------------------------------------------------
# ConditionValue tests (FR-01)
# ---------------------------------------------------------------------------


def test_condition_value_accepts_string():
    cond = _make_condition(value="active")
    assert cond.value == "active"


def test_condition_value_accepts_int():
    cond = _make_condition(value=42)
    assert cond.value == 42


def test_condition_value_accepts_float():
    cond = _make_condition(value=3.14)
    assert cond.value == 3.14


def test_condition_value_accepts_flat_list():
    cond = _make_condition(value=["a", "b", "c"])
    assert cond.value == ["a", "b", "c"]


def test_condition_value_rejects_dict():
    with pytest.raises(ValidationError) as exc_info:
        _make_condition(value={"nested": "dict"})
    assert "dict" in str(exc_info.value).lower() or "SIRCondition" in str(exc_info.value)


# ---------------------------------------------------------------------------
# nested_conditions depth validator tests (FR-02)
# ---------------------------------------------------------------------------


def test_nested_conditions_depth_3_passes():
    level3 = _make_condition()
    level2 = _make_condition(nested=[level3])
    level1 = _make_condition(nested=[level2])
    # Depth from root level1's perspective: 3 levels, should pass
    root = _make_condition(nested=[level1])
    assert root is not None


def test_nested_conditions_depth_4_fails():
    level4 = _make_condition()
    level3 = _make_condition(nested=[level4])
    level2 = _make_condition(nested=[level3])
    level1 = _make_condition(nested=[level2])
    with pytest.raises(ValidationError) as exc_info:
        _make_condition(nested=[level1])
    assert "depth" in str(exc_info.value).lower() or "3" in str(exc_info.value)


# ---------------------------------------------------------------------------
# SIRConstraint discriminated union tests (FR-03)
# ---------------------------------------------------------------------------


def test_value_in_list_constraint_construction():
    c = ValueInListConstraint(allowed_values=["active", "inactive", "pending"])
    assert c.constraint_type == "value_in_list"
    assert "active" in c.allowed_values


def test_range_constraint_construction():
    c = RangeConstraint(min=0.0, max=100.0)
    assert c.constraint_type == "range"
    assert c.min == 0.0
    assert c.max == 100.0


def test_regex_constraint_construction():
    c = RegexConstraint(pattern=r"^\d{4}-\d{2}-\d{2}$")
    assert c.constraint_type == "regex"
    assert c.pattern.startswith("^")


def test_length_constraint_construction():
    c = LengthConstraint(min_length=1, max_length=255)
    assert c.constraint_type == "length"
    assert c.min_length == 1


def test_generic_constraint_catch_all():
    c = GenericConstraint(data={"custom_key": "custom_val", "extra": 42})
    assert c.constraint_type == "generic"


# ---------------------------------------------------------------------------
# SIR model validator tests (FR-10)
# ---------------------------------------------------------------------------


def test_sir_rule_type_normalization():
    """LLM-produced uppercase rule_type should normalize to canonical enum value."""
    sir = StructuredIntermediateRepresentation(**_make_base_sir(rule_type="NOT_NULL"))
    assert sir.rule_type == RuleType.NOT_NULL
    assert sir.rule_type.value == "not_null"


def test_sir_rule_type_normalization_mixed_case():
    sir = StructuredIntermediateRepresentation(**_make_base_sir(rule_type="Not_Null"))
    assert sir.rule_type == RuleType.NOT_NULL


def test_sir_confidence_clamping_above_one():
    """Confidence > 1.0 should be clamped to 1.0."""
    sir = StructuredIntermediateRepresentation(**_make_base_sir(confidence=2.5))
    assert sir.confidence == 1.0


def test_sir_confidence_clamping_below_zero():
    """Confidence < 0.0 should be clamped to 0.0."""
    sir = StructuredIntermediateRepresentation(**_make_base_sir(confidence=-0.5))
    assert sir.confidence == 0.0


# ---------------------------------------------------------------------------
# DecompositionSummary typed field on ParseRuleResponse (FR-04)
# ---------------------------------------------------------------------------


def test_parse_response_decomposition_summary_typed():
    """ParseRuleResponse.decomposition_summary must be a DecompositionSummary instance."""
    response = ParseRuleResponse(
        request_id="req-001",
        parse_result_id="pr-001",
        parsed_rule=None,
        status="parsed",
        decomposition_summary={
            "count": 2,
            "logic": "AND",
            "obligations": ["customer_id must not be null", "email must not be null"],
        },
    )
    assert isinstance(response.decomposition_summary, DecompositionSummary)
    assert response.decomposition_summary.count == 2
    assert response.decomposition_summary.logic == "AND"
    assert len(response.decomposition_summary.obligations) == 2


def test_decomposition_summary_direct_construction():
    ds = DecompositionSummary(count=1, logic=None, obligations=["col must not be null"])
    assert ds.count == 1
    assert ds.logic is None
