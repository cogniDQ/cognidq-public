"""
P05 — Compiler Validation Integration Tests

Tests that every seeded template, when applied with synthetic column
names, produces a canonical rule that passes RuleCompiler.compile_rule()
without error.  Also includes spot-check tests for key dimensions.
"""

import copy
import uuid
from unittest.mock import MagicMock

import pytest
from app.services.rule_templates.placeholders import extract_placeholders
from app.services.rule_templates.seed_templates import SEED_TEMPLATES
from app.services.rule_templates.service import RuleTemplateService
from app.services.rules.compiler import RuleCompiler


def _build_column_mapping(canonical_rule_template: dict) -> dict:
    placeholders = extract_placeholders(canonical_rule_template)
    mapping = {}
    col_counter = 0
    for ph in sorted(placeholders):
        if ph == "__TABLE__":
            continue
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
            mapping[ph] = "test_col_0 * test_col_1"
        else:
            mapping[ph] = f"placeholder_{col_counter}"
            col_counter += 1
    return mapping


def _apply_seed(seed: dict) -> dict:
    """Apply a seed template using the service with mock DB."""
    service = RuleTemplateService()
    mock_tpl = MagicMock()
    mock_tpl.id = uuid.uuid4()
    mock_tpl.name = seed["name"]
    mock_tpl.canonical_rule_template = copy.deepcopy(seed["canonical_rule_template"])
    mock_tpl.is_active = True

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = mock_tpl
    db.query.return_value.filter.return_value.update.return_value = 1

    mapping = _build_column_mapping(seed["canonical_rule_template"])
    result = service.apply_template(db, mock_tpl.id, "test_table", mapping)
    return result["canonical_rule"]


# -----------------------------------------------------------------------
# All templates through compiler
# -----------------------------------------------------------------------


class TestAllTemplatesCompile:
    """Apply each seeded template → compile_rule() → should not raise."""

    @pytest.mark.parametrize("seed", SEED_TEMPLATES, ids=lambda t: t["name"])
    def test_template_compiles(self, seed):
        canonical_rule = _apply_seed(seed)
        compiler = RuleCompiler()
        result = compiler.compile_rule(
            canonical_rule,
            target_table="test_table",
        )
        # Should return a dict with compiled_sql or error info
        assert isinstance(result, dict)
        # If there's an error field, it should be False (success)
        if "error" in result:
            assert result["error"] is False, (
                f"Template '{seed['name']}' failed compilation: {result.get('error_message', 'unknown')}"
            )


# -----------------------------------------------------------------------
# Spot-checks per dimension
# -----------------------------------------------------------------------


class TestDimensionSpotChecks:
    def _compile_first(self, dimension: str) -> dict:
        seed = next(t for t in SEED_TEMPLATES if t["dimension"] == dimension)
        canonical_rule = _apply_seed(seed)
        compiler = RuleCompiler()
        return compiler.compile_rule(canonical_rule, target_table="test_table")

    def test_completeness_compiles(self):
        result = self._compile_first("completeness")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_validity_compiles(self):
        result = self._compile_first("validity")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_uniqueness_compiles(self):
        result = self._compile_first("uniqueness")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_conformity_compiles(self):
        result = self._compile_first("conformity")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_consistency_compiles(self):
        result = self._compile_first("consistency")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_timeliness_compiles(self):
        result = self._compile_first("timeliness")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_accuracy_compiles(self):
        result = self._compile_first("accuracy")
        assert isinstance(result, dict)
        assert result.get("error") is not True

    def test_reconciliation_compiles(self):
        result = self._compile_first("reconciliation")
        assert isinstance(result, dict)
        assert result.get("error") is not True


# -----------------------------------------------------------------------
# Compiled output contains expected SQL patterns
# -----------------------------------------------------------------------


class TestCompiledOutputPatterns:
    def _compile_template_by_name(self, name: str) -> dict:
        seed = next(t for t in SEED_TEMPLATES if t["name"] == name)
        canonical_rule = _apply_seed(seed)
        compiler = RuleCompiler()
        return compiler.compile_rule(canonical_rule, target_table="test_table")

    def test_null_check_sql_has_null(self):
        result = self._compile_template_by_name("Mandatory Fields — NULL Check")
        sql = result.get("compiled_sql", "") or result.get("compiled_postgres", "")
        assert "NULL" in sql.upper() or "null" in sql

    def test_primary_key_sql_has_group_by(self):
        result = self._compile_template_by_name("Primary Key Uniqueness")
        sql = result.get("compiled_sql", "") or result.get("compiled_postgres", "")
        assert "GROUP" in sql.upper() or "HAVING" in sql.upper() or "COUNT" in sql.upper()

    def test_email_standard_has_pattern(self):
        result = self._compile_template_by_name("Email Format (RFC 5322)")
        sql = result.get("compiled_sql", "") or result.get("compiled_postgres", "")
        # Should contain some pattern matching (LIKE, SIMILAR TO, ~, or REGEXP)
        combined = sql.upper()
        assert any(kw in combined for kw in ["LIKE", "SIMILAR", "~", "REGEXP", "@"]), (
            f"Expected pattern matching in SQL: {sql[:200]}"
        )
