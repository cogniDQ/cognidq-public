"""P04 — Multi-Field Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **extra):
    params = {"columns": ["phone", "mobile", "email"], "check_mode": "multi_field"}
    params.update(extra)
    return compiler._compile_completeness_rule(
        '"customers"', "phone", "IS NOT NULL", "100%", params
    )


class TestMultiFieldAll:
    def test_two_columns(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"',
            "a",
            "IS NOT NULL",
            "100%",
            {"columns": ["a", "b"], "check_mode": "multi_field", "multi_field_mode": "all"},
        )
        sql = result["compiled_sql"]
        assert '"a" IS NOT NULL AND "b" IS NOT NULL' in sql
        assert result.get("error") is not True

    def test_three_columns(self, compiler):
        result = _compile(compiler, multi_field_mode="all")
        sql = result["compiled_sql"]
        assert '"phone" IS NOT NULL' in sql
        assert '"mobile" IS NOT NULL' in sql
        assert '"email" IS NOT NULL' in sql
        assert "AND" in sql

    def test_violation_sql_uses_or(self, compiler):
        result = _compile(compiler, multi_field_mode="all")
        vsql = result["violation_sql"]
        assert '"phone" IS NULL OR "mobile" IS NULL OR "email" IS NULL' in vsql


class TestMultiFieldAny:
    def test_two_columns(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"',
            "a",
            "IS NOT NULL",
            "100%",
            {"columns": ["a", "b"], "check_mode": "multi_field", "multi_field_mode": "any"},
        )
        sql = result["compiled_sql"]
        assert "COALESCE" in sql
        assert result.get("error") is not True

    def test_three_columns_coalesce(self, compiler):
        result = _compile(compiler, multi_field_mode="any")
        sql = result["compiled_sql"]
        assert "COALESCE" in sql
        assert '"phone"' in sql
        assert '"mobile"' in sql
        assert '"email"' in sql

    def test_violation_sql_uses_and(self, compiler):
        result = _compile(compiler, multi_field_mode="any")
        vsql = result["violation_sql"]
        assert '"phone" IS NULL AND "mobile" IS NULL AND "email" IS NULL' in vsql


class TestMultiFieldEdgeCases:
    def test_less_than_2_columns_error(self, compiler):
        result = compiler._compile_completeness_rule(
            '"t"', "a", "IS NOT NULL", "100%", {"columns": ["a"], "check_mode": "multi_field"}
        )
        assert result["error"] is True
        assert "at least 2" in result["error_message"]

    def test_default_mode_is_all(self, compiler):
        """No multi_field_mode → defaults to all."""
        result = _compile(compiler)
        sql = result["compiled_sql"]
        # "all" mode uses AND IS NOT NULL
        assert '"phone" IS NOT NULL AND "mobile" IS NOT NULL' in sql

    def test_with_filter(self, compiler):
        result = _compile(compiler, multi_field_mode="all", filter_expression="active = true")
        assert "active = true" in result["compiled_sql"]

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, multi_field_mode="any")
        assert "pyspark" in result["compiled_spark"]
        assert "coalesce" in result["compiled_spark"].lower()
