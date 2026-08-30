"""
F070 P02 — Unit tests: Compiler Spark adjustment + rule syntax validation

Tests compile_rule_for_spark(), _adjust_for_spark_sql(), validate_rule_syntax(),
entity parsing (dotted vs plain), and schema handling.

P02-01 .. P02-16  (16 tests)
"""

from __future__ import annotations

import pytest
from app.services.rules.compiler import RuleCompiler

compiler = RuleCompiler()


def _rule(dimension: str, entity: str = "orders.amount", **params):
    return {
        "dimension": dimension,
        "entity": entity,
        "condition": params.pop("condition", ""),
        "expectation": params.pop("expectation", "should pass"),
        "severity": params.pop("severity", "high"),
        "parameters": params,
    }


# ===================================================================
# SPARK COMPILATION
# ===================================================================
class TestSparkCompilation:
    """P02-01 .. P02-05"""

    def test_compile_rule_for_spark_returns_string(self):
        """P02-01"""
        result = compiler.compile_rule_for_spark(_rule("completeness"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_spark_sql_strips_double_quotes(self):
        """P02-02: "schema"."table" → schema.table"""
        adjusted = compiler._adjust_for_spark_sql('SELECT * FROM "public"."orders"')
        assert '"public"' not in adjusted
        assert '"orders"' not in adjusted
        assert "public" in adjusted
        assert "orders" in adjusted

    def test_spark_sql_strips_column_quotes(self):
        """P02-03"""
        adjusted = compiler._adjust_for_spark_sql('SELECT COUNT("amount") FROM orders')
        assert '"amount"' not in adjusted
        assert "amount" in adjusted

    def test_spark_sql_preserves_string_literals(self):
        """P02-04: single-quoted strings must stay intact."""
        adjusted = compiler._adjust_for_spark_sql("SELECT * FROM orders WHERE status = 'active'")
        assert "'active'" in adjusted

    def test_spark_from_clause_unquoted(self):
        """P02-05: FROM "table" → FROM table"""
        adjusted = compiler._adjust_for_spark_sql('FROM "my_table"')
        assert '"my_table"' not in adjusted
        assert "my_table" in adjusted


# ===================================================================
# RULE SYNTAX VALIDATION
# ===================================================================
class TestRuleSyntaxValidation:
    """P02-06 .. P02-11"""

    def test_valid_rule_passes(self):
        """P02-06"""
        result = compiler.validate_rule_syntax(_rule("completeness"))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_dimension_fails(self):
        """P02-07"""
        rule = _rule("completeness")
        del rule["dimension"]
        result = compiler.validate_rule_syntax(rule)
        assert result["valid"] is False
        any_dim_error = any("dimension" in e.lower() for e in result["errors"])
        assert any_dim_error

    def test_missing_entity_fails(self):
        """P02-08"""
        rule = _rule("completeness")
        del rule["entity"]
        result = compiler.validate_rule_syntax(rule)
        assert result["valid"] is False

    def test_invalid_dimension_fails(self):
        """P02-09"""
        rule = _rule("completeness")
        rule["dimension"] = "garbage_dimension"
        result = compiler.validate_rule_syntax(rule)
        assert result["valid"] is False
        # Error message should mention valid dimensions
        assert any("dimension" in e.lower() for e in result["errors"])

    def test_empty_entity_fails(self):
        """P02-10"""
        rule = _rule("completeness", entity="")
        result = compiler.validate_rule_syntax(rule)
        assert result["valid"] is False

    def test_empty_expectation_warns(self):
        """P02-11"""
        rule = _rule("completeness", expectation="")
        result = compiler.validate_rule_syntax(rule)
        # Should still be valid, just a warning
        assert any("expectation" in w.lower() for w in result["warnings"])


# ===================================================================
# ENTITY PARSING
# ===================================================================
class TestEntityParsing:
    """P02-12 .. P02-14"""

    def test_dotted_entity_splits_table_column(self):
        """P02-12: 'orders.amount' → table=orders, column=amount"""
        result = compiler.compile_rule(_rule("completeness", entity="orders.amount"))
        sql = result["compiled_sql"]
        # Column should appear in SQL
        assert "amount" in sql

    def test_plain_entity_uses_target_columns(self):
        """P02-13: 'orders' without dot → column from target_columns[0]"""
        result = compiler.compile_rule(
            _rule("completeness", entity="orders"),
            target_columns=["my_col"],
        )
        sql = result["compiled_sql"]
        assert "my_col" in sql

    def test_plain_entity_no_columns_uses_star(self):
        """P02-14: 'orders' without dot or target_columns → column='*'"""
        result = compiler.compile_rule(_rule("completeness", entity="orders"))
        sql = result["compiled_sql"]
        # With column='*', COUNT("*") or COUNT(*) should appear
        assert "COUNT" in sql


# ===================================================================
# SCHEMA HANDLING
# ===================================================================
class TestSchemaHandling:
    """P02-15 .. P02-16"""

    def test_schema_prefixed_in_output(self):
        """P02-15"""
        result = compiler.compile_rule(
            _rule("completeness", entity="orders.amount"),
            target_schema="public",
        )
        sql = result["compiled_sql"]
        assert '"public"' in sql

    def test_no_schema_no_prefix(self):
        """P02-16"""
        result = compiler.compile_rule(
            _rule("completeness", entity="orders.amount"),
            target_schema=None,
        )
        sql = result["compiled_sql"]
        assert '"public"' not in sql
