"""
F126 Compound Compilation Tests (P03)

Tests for NLRuleCompiler._compile_compound and the routing in compile().
"""

import pytest
from app.schemas.nl_compiler import CompilationStatus, CompileRequest
from app.schemas.nl_rule_builder import (
    RuleType,
    SIREntity,
    StructuredIntermediateRepresentation,
)
from app.services.nl_compiler.compiler import NLRuleCompiler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compiler() -> NLRuleCompiler:
    return NLRuleCompiler()


def _atomic_sir(
    subject: str, rule_type: RuleType = RuleType.NOT_NULL
) -> StructuredIntermediateRepresentation:
    return StructuredIntermediateRepresentation(
        rule_type=rule_type,
        subject=SIREntity(raw_text=subject, resolved_column=subject),
        confidence=0.9,
    )


def _compound_sir(
    obligations: list,
    logic: str = "AND",
) -> StructuredIntermediateRepresentation:
    sir = StructuredIntermediateRepresentation(
        rule_type=RuleType.UNKNOWN,
        subject=SIREntity(raw_text="compound"),
        confidence=0.9,
        is_compound=True,
        obligation_logic=logic,
        obligations=obligations,
    )
    return sir


def _request(sir: StructuredIntermediateRepresentation, **kw) -> CompileRequest:
    return CompileRequest(resolved_rule=sir, compilation_options=kw)


# ===========================================================================
# Section 1 — Compound Compilation (10 tests)
# ===========================================================================


def test_compound_and_2_obligations_success():
    """2-obligation AND compound → 2 configs, status=SUCCESS."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("email"), _atomic_sir("phone")], logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 2


def test_compound_and_3_obligations():
    """3-obligation AND → 3 configs."""
    c = _compiler()
    obligations = [_atomic_sir(f"col_{i}") for i in range(3)]
    compound = _compound_sir(obligations, logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 3


def test_compound_or_logic_configs():
    """OR logic → obligation_logic='OR' on all configs."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("a"), _atomic_sir("b")], logic="OR")
    resp = c.compile(_request(compound))
    assert all(cfg.obligation_logic == "OR" for cfg in resp.compiled_configs)


def test_compound_independent_logic():
    """INDEPENDENT logic preserved on compiled configs."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("x"), _atomic_sir("y")], logic="INDEPENDENT")
    resp = c.compile(_request(compound))
    assert all(cfg.obligation_logic == "INDEPENDENT" for cfg in resp.compiled_configs)


def test_compound_obligation_group_id_shared():
    """All configs share the same obligation_group_id."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("a"), _atomic_sir("b"), _atomic_sir("c")])
    resp = c.compile(_request(compound))
    group_ids = {cfg.obligation_group_id for cfg in resp.compiled_configs}
    assert len(group_ids) == 1
    assert next(iter(group_ids)) is not None


def test_compound_obligation_group_id_is_uuid():
    """obligation_group_id is a valid UUID string."""
    import re

    c = _compiler()
    compound = _compound_sir([_atomic_sir("a"), _atomic_sir("b")])
    resp = c.compile(_request(compound))
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    for cfg in resp.compiled_configs:
        assert uuid_re.match(cfg.obligation_group_id), f"Bad UUID: {cfg.obligation_group_id}"


def test_compound_configs_individual_check_types():
    """Each obligation compiles to its own check type."""
    c = _compiler()
    ob1 = _atomic_sir("email", RuleType.NOT_NULL)
    ob2 = _atomic_sir("status", RuleType.UNIQUENESS)
    compound = _compound_sir([ob1, ob2])
    resp = c.compile(_request(compound))
    types = {cfg.check_type for cfg in resp.compiled_configs}
    assert "completeness" in types
    assert "uniqueness" in types


def test_compound_with_value_in_list_obligation():
    """Value_in_list obligation in compound compiles correctly."""
    c = _compiler()
    ob = _atomic_sir("status", RuleType.VALUE_IN_LIST)
    ob.constraints = ["Active", "Inactive"]
    compound = _compound_sir([ob, _atomic_sir("email")], logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    # Find the allowed_values config
    vl_cfg = next((cfg for cfg in resp.compiled_configs if cfg.subtype == "allowed_values"), None)
    assert vl_cfg is not None
    assert vl_cfg.config.get("allowed_values") == ["Active", "Inactive"]


def test_compound_with_numeric_threshold_obligation():
    """Numeric threshold obligation in compound compiles correctly."""
    c = _compiler()
    ob = _atomic_sir("score", RuleType.NUMERIC_THRESHOLD)
    ob.constraints = [100]
    ob.operator = ">="
    compound = _compound_sir([ob, _atomic_sir("id")], logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    num_cfg = next((cfg for cfg in resp.compiled_configs if cfg.subtype == "range"), None)
    assert num_cfg is not None


def test_compound_10_obligations_boundary():
    """Exactly 10 obligations compile successfully."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir(f"col_{i}") for i in range(10)], logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 10


# ===========================================================================
# Section 2 — Edge Cases (10 tests)
# ===========================================================================


def test_compound_unknown_obligation_skipped():
    """UNKNOWN obligation in compound is skipped; valid ones compiled."""
    c = _compiler()
    ob_unknown = _atomic_sir("bad_col", RuleType.UNKNOWN)
    ob_valid = _atomic_sir("email", RuleType.NOT_NULL)
    compound = _compound_sir([ob_unknown, ob_valid])
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.PARTIAL
    assert len(resp.compiled_configs) == 1
    assert any("unknown rule type" in w for w in resp.warnings)


def test_compound_all_unknown_obligations_error():
    """All UNKNOWN obligations → status=ERROR, 0 configs."""
    c = _compiler()
    compound = _compound_sir(
        [_atomic_sir("a", RuleType.UNKNOWN), _atomic_sir("b", RuleType.UNKNOWN)]
    )
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.ERROR
    assert resp.compiled_configs == []


def test_compound_is_false_uses_single_path():
    """is_compound=False → normal single-obligation compile path."""
    c = _compiler()
    sir = _atomic_sir("email", RuleType.NOT_NULL)
    resp = c.compile(_request(sir))
    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 1
    assert resp.compiled_configs[0].obligation_group_id is None


def test_compound_empty_obligations_list_uses_normal_path():
    """is_compound=True but obligations=[] → single-path but rule_type=UNKNOWN → UNSUPPORTED."""
    c = _compiler()
    sir = StructuredIntermediateRepresentation(
        rule_type=RuleType.UNKNOWN,
        subject=SIREntity(raw_text="orphan"),
        confidence=0.5,
        is_compound=True,
        obligations=[],  # empty — does NOT trigger _compile_compound
    )
    resp = c.compile(_request(sir))
    # Falls through to single-path → UNKNOWN → UNSUPPORTED
    assert resp.status == CompilationStatus.UNSUPPORTED


def test_compound_partial_status_when_one_unknown():
    """1 valid + 1 UNKNOWN → PARTIAL, 1 config returned."""
    c = _compiler()
    compound = _compound_sir(
        [_atomic_sir("col_a"), _atomic_sir("col_b", RuleType.UNKNOWN)],
        logic="OR",
    )
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.PARTIAL
    assert len(resp.compiled_configs) == 1


def test_compound_group_id_different_across_calls():
    """Two separate compile() calls produce different group_ids."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("a"), _atomic_sir("b")])
    resp1 = c.compile(_request(compound))
    resp2 = c.compile(_request(compound))
    gid1 = resp1.compiled_configs[0].obligation_group_id
    gid2 = resp2.compiled_configs[0].obligation_group_id
    assert gid1 != gid2


def test_compound_single_obligation_still_groups():
    """1-obligation compound (degenerate) still gets group_id and logic."""
    c = _compiler()
    compound = _compound_sir([_atomic_sir("email")], logic="AND")
    resp = c.compile(_request(compound))
    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 1
    assert resp.compiled_configs[0].obligation_group_id is not None
    assert resp.compiled_configs[0].obligation_logic == "AND"


def test_compound_parse_warnings_propagated():
    """parse_warnings on obligations appear in CompileResponse.warnings."""
    c = _compiler()
    ob = _atomic_sir("email")
    ob.parse_warnings = ["Some parse warning"]
    compound = _compound_sir([ob, _atomic_sir("phone")])
    resp = c.compile(_request(compound))
    assert any("Some parse warning" in w for w in resp.warnings)


def test_compound_obligation_logic_none_still_sets_group_id():
    """obligation_logic=None — group_id still set on configs."""
    c = _compiler()
    sir = StructuredIntermediateRepresentation(
        rule_type=RuleType.UNKNOWN,
        subject=SIREntity(raw_text="compound"),
        confidence=0.9,
        is_compound=True,
        obligation_logic=None,
        obligations=[_atomic_sir("col_a"), _atomic_sir("col_b")],
    )
    resp = c.compile(_request(sir))
    assert resp.status == CompilationStatus.SUCCESS
    for cfg in resp.compiled_configs:
        assert cfg.obligation_group_id is not None
        assert cfg.obligation_logic is None


def test_compound_low_confidence_warning_propagated():
    """Parent SIR low confidence → warning in response."""
    c = _compiler()
    ob = _atomic_sir("col_a")
    ob.confidence = 0.5  # triggers low-confidence warning in _collect_warnings
    compound = _compound_sir([ob, _atomic_sir("col_b")])
    resp = c.compile(_request(compound))
    assert any("Low parse confidence" in w for w in resp.warnings)


# ===========================================================================
# Section 3 — Integration (1 test)
# ===========================================================================


def test_integration_compound_sir_end_to_end():
    """Full compile() round-trip: compound SIR → configs with group_id and logic."""
    c = _compiler()
    ob_email = _atomic_sir("email", RuleType.NOT_NULL)
    ob_phone = _atomic_sir("phone", RuleType.NOT_NULL)
    ob_status = _atomic_sir("status", RuleType.UNIQUENESS)

    compound = _compound_sir([ob_email, ob_phone, ob_status], logic="AND")
    resp = c.compile(_request(compound))

    assert resp.status == CompilationStatus.SUCCESS
    assert len(resp.compiled_configs) == 3

    # All share same group_id
    group_ids = {cfg.obligation_group_id for cfg in resp.compiled_configs}
    assert len(group_ids) == 1

    # All have logic AND
    assert all(cfg.obligation_logic == "AND" for cfg in resp.compiled_configs)

    # Check types are correct
    check_types = {cfg.check_type for cfg in resp.compiled_configs}
    assert "completeness" in check_types
    assert "uniqueness" in check_types
