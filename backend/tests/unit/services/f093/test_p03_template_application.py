"""
P03 — Template Application Logic Tests

Tests for: apply_template placeholder substitution, column mapping,
target table, overrides, entity construction, error handling.
All tests use mock DB objects — no real database.
"""

import copy
import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.services.rule_templates.placeholders import (
    extract_placeholders,
    substitute_placeholders,
)
from app.services.rule_templates.seed_templates import SEED_TEMPLATES
from app.services.rule_templates.service import RuleTemplateService


def _make_mock_template(seed_entry: dict) -> MagicMock:
    """Create a mock RuleTemplate ORM object from a seed dict."""
    tpl = MagicMock()
    tpl.id = uuid.uuid4()
    tpl.name = seed_entry["name"]
    tpl.dimension = seed_entry["dimension"]
    tpl.description = seed_entry["description"]
    tpl.category = seed_entry["category"]
    tpl.tags = seed_entry.get("tags", [])
    tpl.canonical_rule_template = copy.deepcopy(seed_entry["canonical_rule_template"])
    tpl.default_severity = seed_entry.get("default_severity", "high")
    tpl.default_threshold_pass = seed_entry.get("default_threshold_pass", 98.0)
    tpl.default_threshold_warn = seed_entry.get("default_threshold_warn")
    tpl.use_count = 0
    tpl.is_active = True
    return tpl


def _build_column_mapping(canonical_rule_template: dict) -> dict:
    """Build a complete column mapping for all placeholders in a template."""
    placeholders = extract_placeholders(canonical_rule_template)
    mapping = {}
    col_counter = 0
    for ph in sorted(placeholders):
        if ph == "__TABLE__":
            continue  # handled by target_table
        elif "COLUMN" in ph:
            mapping[ph] = f"test_col_{col_counter}"
            col_counter += 1
        elif "REF_TABLE" in ph:
            mapping[ph] = "ref_table"
        elif "REF_COLUMN" in ph:
            mapping[ph] = "ref_col"
        elif "CONDITION_VALUE" in ph:
            mapping[ph] = "US"
        elif "ALLOWED_VALUE" in ph:
            mapping[ph] = f"val_{col_counter}"
            col_counter += 1
        elif "REGEX_PATTERN" in ph:
            mapping[ph] = "^[A-Z]+$"
        elif "EXPRESSION" in ph:
            mapping[ph] = "col_a * col_b"
        else:
            mapping[ph] = f"placeholder_{col_counter}"
            col_counter += 1
    return mapping


# -----------------------------------------------------------------------
# Basic apply flow (mock DB)
# -----------------------------------------------------------------------


class TestApplyTemplateBasic:
    def setup_method(self):
        self.service = RuleTemplateService()
        self.seed = SEED_TEMPLATES[0]  # Mandatory Fields — NULL Check
        self.mock_tpl = _make_mock_template(self.seed)

    def _mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = self.mock_tpl
        db.query.return_value.filter.return_value.update.return_value = 1
        return db

    def test_apply_returns_canonical_rule(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "customers",
            {"__COLUMN__": "email"},
        )
        assert "canonical_rule" in result
        assert result["template_name"] == self.seed["name"]

    def test_canonical_rule_has_dimension(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "customers",
            {"__COLUMN__": "email"},
        )
        cr = result["canonical_rule"]
        assert cr["dimension"] == "completeness"

    def test_column_substituted(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "customers",
            {"__COLUMN__": "email"},
        )
        cr = result["canonical_rule"]
        assert "email" in cr["parameters"]["columns"]

    def test_entity_contains_table_and_column(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "customers",
            {"__COLUMN__": "email"},
        )
        cr = result["canonical_rule"]
        assert "customers" in cr["entity"]
        assert "email" in cr["entity"]

    def test_target_table_set(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "orders",
            {"__COLUMN__": "status"},
        )
        cr = result["canonical_rule"]
        assert cr["target_table"] == "orders"


# -----------------------------------------------------------------------
# Override application
# -----------------------------------------------------------------------


class TestApplyOverrides:
    def setup_method(self):
        self.service = RuleTemplateService()
        self.seed = SEED_TEMPLATES[0]
        self.mock_tpl = _make_mock_template(self.seed)

    def _mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = self.mock_tpl
        db.query.return_value.filter.return_value.update.return_value = 1
        return db

    def test_override_threshold_pass(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "t",
            {"__COLUMN__": "c"},
            overrides={"threshold_pass": 95.0},
        )
        assert result["canonical_rule"]["parameters"]["threshold_pass"] == 95.0

    def test_override_threshold_warn(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "t",
            {"__COLUMN__": "c"},
            overrides={"threshold_warn": 90.0},
        )
        assert result["canonical_rule"]["parameters"]["threshold_warn"] == 90.0

    def test_override_severity(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "t",
            {"__COLUMN__": "c"},
            overrides={"severity": "critical"},
        )
        assert result["canonical_rule"]["severity"] == "critical"

    def test_override_invalid_severity_raises(self):
        db = self._mock_db()
        with pytest.raises(ValueError, match="severity"):
            self.service.apply_template(
                db,
                self.mock_tpl.id,
                "t",
                {"__COLUMN__": "c"},
                overrides={"severity": "invalid"},
            )

    def test_override_threshold_out_of_range_raises(self):
        db = self._mock_db()
        with pytest.raises(ValueError, match="threshold_pass"):
            self.service.apply_template(
                db,
                self.mock_tpl.id,
                "t",
                {"__COLUMN__": "c"},
                overrides={"threshold_pass": 150.0},
            )

    def test_no_overrides_uses_defaults(self):
        db = self._mock_db()
        result = self.service.apply_template(
            db,
            self.mock_tpl.id,
            "t",
            {"__COLUMN__": "c"},
        )
        cr = result["canonical_rule"]
        assert (
            cr["parameters"]["threshold_pass"]
            == self.seed["canonical_rule_template"]["parameters"]["threshold_pass"]
        )


# -----------------------------------------------------------------------
# Error cases
# -----------------------------------------------------------------------


class TestApplyErrors:
    def setup_method(self):
        self.service = RuleTemplateService()

    def test_template_not_found_raises(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(LookupError, match="not found"):
            self.service.apply_template(db, uuid.uuid4(), "t", {})

    def test_missing_column_mapping_raises(self):
        seed = SEED_TEMPLATES[0]
        mock_tpl = _make_mock_template(seed)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tpl
        with pytest.raises(ValueError, match="Missing required column mappings"):
            self.service.apply_template(db, mock_tpl.id, "t", {})

    def test_partial_mapping_raises_with_missing_keys(self):
        # Use conditional template which needs __COLUMN__, __COLUMN_2__, __CONDITION_VALUE__
        seed = next(t for t in SEED_TEMPLATES if t["name"] == "Conditional Required Field")
        mock_tpl = _make_mock_template(seed)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tpl
        db.query.return_value.filter.return_value.update.return_value = 1
        with pytest.raises(ValueError, match="Missing"):
            self.service.apply_template(
                db,
                mock_tpl.id,
                "t",
                {"__COLUMN__": "state"},  # missing __COLUMN_2__ and __CONDITION_VALUE__
            )


# -----------------------------------------------------------------------
# Deep copy safety
# -----------------------------------------------------------------------


class TestDeepCopySafety:
    def test_template_unmodified_after_apply(self):
        service = RuleTemplateService()
        seed = SEED_TEMPLATES[0]
        mock_tpl = _make_mock_template(seed)
        original_crt = copy.deepcopy(mock_tpl.canonical_rule_template)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tpl
        db.query.return_value.filter.return_value.update.return_value = 1

        service.apply_template(db, mock_tpl.id, "customers", {"__COLUMN__": "email"})
        assert mock_tpl.canonical_rule_template == original_crt


# -----------------------------------------------------------------------
# Apply every seeded template
# -----------------------------------------------------------------------


class TestApplyAllSeeded:
    """Apply each seeded template with synthetic column mapping → should succeed."""

    @pytest.mark.parametrize("seed", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_apply_succeeds(self, seed):
        service = RuleTemplateService()
        mock_tpl = _make_mock_template(seed)
        mapping = _build_column_mapping(seed["canonical_rule_template"])

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_tpl
        db.query.return_value.filter.return_value.update.return_value = 1

        result = service.apply_template(db, mock_tpl.id, "test_table", mapping)
        cr = result["canonical_rule"]

        # No placeholders should remain
        remaining = extract_placeholders(cr)
        assert len(remaining) == 0, f"Remaining placeholders: {remaining}"

        # Dimension should match
        assert cr["dimension"] == seed["dimension"]

        # target_table should be set
        assert cr["target_table"] == "test_table"
