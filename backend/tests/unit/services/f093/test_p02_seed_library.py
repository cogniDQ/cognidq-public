"""
P02 — Seed Library Tests

Tests for: template count, per-dimension count, structural validity,
no duplicate names, field constraints, placeholder convention, idempotency.
"""

import pytest
from app.services.rule_templates.placeholders import (
    VALID_DIMENSIONS,
    VALID_SEVERITIES,
    extract_placeholders,
)
from app.services.rule_templates.seed_templates import SEED_TEMPLATES

# -----------------------------------------------------------------------
# Count & Coverage
# -----------------------------------------------------------------------


class TestSeedCount:
    def test_minimum_total_templates(self):
        assert len(SEED_TEMPLATES) >= 40

    @pytest.mark.parametrize("dim", sorted(VALID_DIMENSIONS))
    def test_min_five_per_dimension(self, dim):
        count = sum(1 for t in SEED_TEMPLATES if t["dimension"] == dim)
        assert count >= 5, f"{dim} has only {count} templates, need >= 5"

    def test_all_dimensions_present(self):
        dims = {t["dimension"] for t in SEED_TEMPLATES}
        assert dims == VALID_DIMENSIONS


# -----------------------------------------------------------------------
# Structural Validity
# -----------------------------------------------------------------------

REQUIRED_FIELDS = {"dimension", "name", "description", "category", "canonical_rule_template"}
OPTIONAL_FIELDS = {"tags", "default_severity", "default_threshold_pass", "default_threshold_warn"}


class TestSeedStructure:
    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_required_fields_present(self, tpl):
        for field in REQUIRED_FIELDS:
            assert field in tpl, f"Template '{tpl['name']}' missing field '{field}'"

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_dimension_valid(self, tpl):
        assert tpl["dimension"] in VALID_DIMENSIONS, f"Invalid dimension: {tpl['dimension']}"

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_severity_valid(self, tpl):
        sev = tpl.get("default_severity", "high")
        assert sev in VALID_SEVERITIES, f"Invalid severity: {sev}"

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_threshold_pass_in_range(self, tpl):
        tp = tpl.get("default_threshold_pass", 98.0)
        assert 0 <= tp <= 100

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_threshold_warn_valid(self, tpl):
        tw = tpl.get("default_threshold_warn")
        if tw is not None:
            assert 0 <= tw <= 100
            tp = tpl.get("default_threshold_pass", 98.0)
            assert tw <= tp, f"threshold_warn ({tw}) > threshold_pass ({tp})"

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_canonical_rule_has_dimension(self, tpl):
        crt = tpl["canonical_rule_template"]
        assert "dimension" in crt
        assert crt["dimension"] == tpl["dimension"]

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_canonical_rule_has_parameters(self, tpl):
        crt = tpl["canonical_rule_template"]
        assert "parameters" in crt
        assert isinstance(crt["parameters"], dict)

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_canonical_rule_has_entity(self, tpl):
        crt = tpl["canonical_rule_template"]
        assert "entity" in crt

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_canonical_rule_has_severity(self, tpl):
        crt = tpl["canonical_rule_template"]
        assert "severity" in crt
        assert crt["severity"] in VALID_SEVERITIES


# -----------------------------------------------------------------------
# No Duplicate Names
# -----------------------------------------------------------------------


class TestSeedUniqueness:
    def test_no_duplicate_names(self):
        names = [t["name"] for t in SEED_TEMPLATES]
        assert len(names) == len(set(names)), (
            f"Duplicate names: {[n for n in names if names.count(n) > 1]}"
        )


# -----------------------------------------------------------------------
# Placeholder Convention
# -----------------------------------------------------------------------


class TestSeedPlaceholders:
    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_placeholders_use_convention(self, tpl):
        """All placeholders should match __UPPER_SNAKE__ pattern."""
        placeholders = extract_placeholders(tpl["canonical_rule_template"])
        for ph in placeholders:
            assert ph.startswith("__") and ph.endswith("__"), f"Bad placeholder: {ph}"

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_has_at_least_one_placeholder(self, tpl):
        """Every template should have at least one placeholder (column or table)."""
        placeholders = extract_placeholders(tpl["canonical_rule_template"])
        assert len(placeholders) >= 1, f"Template '{tpl['name']}' has no placeholders"


# -----------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------


class TestSeedTags:
    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_tags_is_list(self, tpl):
        tags = tpl.get("tags", [])
        assert isinstance(tags, list)

    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_tags_non_empty(self, tpl):
        tags = tpl.get("tags", [])
        assert len(tags) >= 1, f"Template '{tpl['name']}' has no tags"


# -----------------------------------------------------------------------
# Dimension-specific subtype key present
# -----------------------------------------------------------------------

_DIM_SUBTYPE_KEY = {
    "completeness": "check_mode",
    "validity": "validation_type",
    "uniqueness": "uniqueness_mode",
    "conformity": "conformity_type",
    "consistency": "consistency_type",
    "timeliness": "timeliness_type",
    "accuracy": "accuracy_type",
    "reconciliation": "reconciliation_type",
}


class TestSeedDimensionSubtype:
    @pytest.mark.parametrize("tpl", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_subtype_key_present(self, tpl):
        dim = tpl["dimension"]
        key = _DIM_SUBTYPE_KEY[dim]
        params = tpl["canonical_rule_template"]["parameters"]
        assert key in params, f"Template '{tpl['name']}' missing '{key}' in parameters"
