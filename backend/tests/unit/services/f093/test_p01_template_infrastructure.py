"""
P01 — Template Infrastructure Tests

Tests for: RuleTemplate model defaults, Pydantic schemas, placeholder utilities,
service skeleton methods, and basic apply_template logic.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.rule_template import (
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    RuleTemplateDetail,
    RuleTemplateListItem,
    RuleTemplateListResponse,
)
from app.services.rule_templates.placeholders import (
    VALID_DIMENSIONS,
    VALID_SEVERITIES,
    extract_placeholders,
    substitute_placeholders,
    validate_mapping_complete,
)

# -----------------------------------------------------------------------
# VALID_DIMENSIONS & VALID_SEVERITIES
# -----------------------------------------------------------------------


class TestConstants:
    def test_valid_dimensions_count(self):
        assert len(VALID_DIMENSIONS) == 8

    def test_valid_dimensions_members(self):
        expected = {
            "completeness",
            "validity",
            "uniqueness",
            "conformity",
            "consistency",
            "timeliness",
            "accuracy",
            "reconciliation",
        }
        assert VALID_DIMENSIONS == expected

    def test_valid_severities_members(self):
        assert VALID_SEVERITIES == {"blocker", "critical", "high", "medium", "low"}


# -----------------------------------------------------------------------
# extract_placeholders
# -----------------------------------------------------------------------


class TestExtractPlaceholders:
    def test_simple_column(self):
        tpl = {"parameters": {"columns": ["__COLUMN__"]}}
        assert extract_placeholders(tpl) == {"__COLUMN__"}

    def test_multiple_placeholders(self):
        tpl = {
            "entity": "__TABLE__.__COLUMN__",
            "parameters": {"columns": ["__COLUMN__", "__COLUMN_2__"]},
        }
        result = extract_placeholders(tpl)
        assert "__TABLE__" in result
        assert "__COLUMN__" in result
        assert "__COLUMN_2__" in result

    def test_nested_lists(self):
        tpl = {"parameters": {"join_keys": ["__COLUMN__", "__COLUMN_2__"]}}
        assert "__COLUMN__" in extract_placeholders(tpl)
        assert "__COLUMN_2__" in extract_placeholders(tpl)

    def test_no_placeholders(self):
        tpl = {"parameters": {"columns": ["email"], "threshold_pass": 98.0}}
        assert extract_placeholders(tpl) == set()

    def test_ref_table_and_column(self):
        tpl = {
            "parameters": {
                "reference_dataset": "__REF_TABLE__",
                "reference_column": "__REF_COLUMN__",
            }
        }
        result = extract_placeholders(tpl)
        assert "__REF_TABLE__" in result
        assert "__REF_COLUMN__" in result

    def test_placeholder_in_string(self):
        tpl = {"condition": "__COLUMN__ IS NOT NULL"}
        assert "__COLUMN__" in extract_placeholders(tpl)

    def test_ignores_non_string_values(self):
        tpl = {"parameters": {"threshold_pass": 98.0, "min_value": 0}}
        assert extract_placeholders(tpl) == set()


# -----------------------------------------------------------------------
# substitute_placeholders
# -----------------------------------------------------------------------


class TestSubstitutePlaceholders:
    def test_simple_substitution(self):
        obj = {"columns": ["__COLUMN__"]}
        result = substitute_placeholders(obj, {"__COLUMN__": "email"})
        assert result == {"columns": ["email"]}

    def test_deep_nested_substitution(self):
        obj = {
            "entity": "__TABLE__.__COLUMN__",
            "parameters": {"columns": ["__COLUMN__"]},
        }
        result = substitute_placeholders(obj, {"__TABLE__": "customers", "__COLUMN__": "email"})
        assert result["entity"] == "customers.email"
        assert result["parameters"]["columns"] == ["email"]

    def test_numeric_values_unchanged(self):
        obj = {"threshold": 98.0, "columns": ["__COLUMN__"]}
        result = substitute_placeholders(obj, {"__COLUMN__": "age"})
        assert result["threshold"] == 98.0

    def test_multiple_tokens_in_one_string(self):
        obj = {"condition": "__COLUMN__ <= __COLUMN_2__"}
        result = substitute_placeholders(
            obj, {"__COLUMN__": "start_date", "__COLUMN_2__": "end_date"}
        )
        assert result["condition"] == "start_date <= end_date"

    def test_no_mutation_of_original(self):
        original = {"columns": ["__COLUMN__"]}
        _ = substitute_placeholders(original, {"__COLUMN__": "email"})
        assert original["columns"] == ["__COLUMN__"]

    def test_boolean_values_unchanged(self):
        obj = {"case_sensitive": True, "columns": ["__COLUMN__"]}
        result = substitute_placeholders(obj, {"__COLUMN__": "name"})
        assert result["case_sensitive"] is True

    def test_none_values_unchanged(self):
        obj = {"extra": None, "columns": ["__COLUMN__"]}
        result = substitute_placeholders(obj, {"__COLUMN__": "id"})
        assert result["extra"] is None


# -----------------------------------------------------------------------
# validate_mapping_complete
# -----------------------------------------------------------------------


class TestValidateMappingComplete:
    def test_all_present(self):
        required = {"__COLUMN__", "__TABLE__"}
        provided = {"__COLUMN__": "email", "__TABLE__": "customers"}
        assert validate_mapping_complete(required, provided) == []

    def test_missing_one(self):
        required = {"__COLUMN__", "__COLUMN_2__"}
        provided = {"__COLUMN__": "email"}
        missing = validate_mapping_complete(required, provided)
        assert "__COLUMN_2__" in missing

    def test_extra_ignored(self):
        required = {"__COLUMN__"}
        provided = {"__COLUMN__": "email", "__EXTRA__": "foo"}
        assert validate_mapping_complete(required, provided) == []

    def test_empty_required(self):
        assert validate_mapping_complete(set(), {}) == []

    def test_all_missing(self):
        required = {"__COLUMN__", "__COLUMN_2__"}
        missing = validate_mapping_complete(required, {})
        assert len(missing) == 2


# -----------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------


class TestSchemas:
    def test_rule_template_list_item_from_dict(self):
        data = {
            "id": uuid.uuid4(),
            "dimension": "completeness",
            "name": "Test Template",
            "description": "desc",
            "category": "cat",
            "tags": ["tag1"],
            "default_severity": "high",
            "default_threshold_pass": 98.0,
            "default_threshold_warn": 95.0,
            "use_count": 0,
        }
        item = RuleTemplateListItem(**data)
        assert item.dimension == "completeness"
        assert item.use_count == 0

    def test_rule_template_detail_includes_template(self):
        data = {
            "id": uuid.uuid4(),
            "dimension": "validity",
            "name": "Test",
            "description": "desc",
            "category": "cat",
            "tags": [],
            "default_severity": "high",
            "default_threshold_pass": 98.0,
            "use_count": 5,
            "canonical_rule_template": {"dimension": "validity", "parameters": {}},
            "is_active": True,
        }
        detail = RuleTemplateDetail(**data)
        assert "dimension" in detail.canonical_rule_template

    def test_rule_template_list_response(self):
        resp = RuleTemplateListResponse(templates=[], total=0)
        assert resp.total == 0
        assert resp.templates == []

    def test_apply_template_request_valid(self):
        req = ApplyTemplateRequest(
            target_table="customers",
            column_mapping={"__COLUMN__": "email"},
        )
        assert req.target_table == "customers"

    def test_apply_template_request_defaults(self):
        req = ApplyTemplateRequest(target_table="t")
        assert req.column_mapping == {}
        assert req.overrides is None

    def test_apply_template_response(self):
        resp = ApplyTemplateResponse(
            canonical_rule={"dimension": "completeness"},
            template_id=uuid.uuid4(),
            template_name="Test",
        )
        assert resp.template_name == "Test"

    def test_list_item_optional_fields(self):
        data = {
            "id": uuid.uuid4(),
            "dimension": "uniqueness",
            "name": "T",
            "description": "d",
            "category": "c",
            "default_severity": "low",
            "default_threshold_pass": 100.0,
        }
        item = RuleTemplateListItem(**data)
        assert item.tags == []
        assert item.default_threshold_warn is None


# -----------------------------------------------------------------------
# RuleTemplate Model field defaults (unit-level, no DB)
# -----------------------------------------------------------------------


class TestRuleTemplateModel:
    def test_model_import(self):
        from app.models.rule_template import RuleTemplate

        assert RuleTemplate.__tablename__ == "rule_templates"

    def test_model_columns(self):
        from app.models.rule_template import RuleTemplate

        cols = {c.name for c in RuleTemplate.__table__.columns}
        expected = {
            "id",
            "dimension",
            "name",
            "description",
            "category",
            "tags",
            "canonical_rule_template",
            "default_severity",
            "default_threshold_pass",
            "default_threshold_warn",
            "use_count",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_name_unique_constraint(self):
        from app.models.rule_template import RuleTemplate

        name_col = RuleTemplate.__table__.c.name
        assert name_col.unique is True

    def test_dimension_indexed(self):
        from app.models.rule_template import RuleTemplate

        dim_col = RuleTemplate.__table__.c.dimension
        assert dim_col.index is True
