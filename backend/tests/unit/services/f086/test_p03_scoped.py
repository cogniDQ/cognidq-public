"""P03 — Scoped Uniqueness Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler

TABLE = '"schema"."table"'


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **params):
    params.setdefault("columns", ["email"])
    params.setdefault("uniqueness_mode", "scoped")
    return compiler._compile_uniqueness_rule(TABLE, "email", "", "", params)


class TestScopedMode:
    def test_basic_scoped_sql(self, compiler):
        result = _compile(compiler, scope_columns=["department"])
        sql = result["compiled_sql"]
        assert '"department"' in sql
        assert '"email"' in sql
        assert "GROUP BY" in sql
        assert "HAVING COUNT(*) > 1" in sql

    def test_scoped_includes_scope_in_group_by(self, compiler):
        result = _compile(compiler, scope_columns=["dept", "region"])
        sql = result["compiled_sql"]
        assert '"dept"' in sql
        assert '"region"' in sql

    def test_empty_scope_columns_error(self, compiler):
        result = _compile(compiler, scope_columns=[])
        assert result["error"] is True
        assert "scope_columns" in result["error_message"]

    def test_missing_scope_columns_error(self, compiler):
        result = compiler._compile_uniqueness_rule(
            TABLE, "email", "", "", {"uniqueness_mode": "scoped", "columns": ["email"]}
        )
        assert result["error"] is True

    def test_null_handling_exclude(self, compiler):
        result = _compile(compiler, scope_columns=["dept"], null_handling="exclude")
        sql = result["compiled_sql"]
        assert '"email" IS NOT NULL' in sql

    def test_null_handling_include(self, compiler):
        result = _compile(compiler, scope_columns=["dept"], null_handling="include")
        sql = result["compiled_sql"]
        assert "COALESCE" in sql

    def test_case_insensitive(self, compiler):
        result = _compile(compiler, scope_columns=["dept"], case_sensitive=False)
        sql = result["compiled_sql"]
        assert "LOWER" in sql

    def test_filter_expression(self, compiler):
        result = _compile(compiler, scope_columns=["dept"], filter_expression="active = true")
        sql = result["compiled_sql"]
        assert "active = true" in sql

    def test_violation_sql(self, compiler):
        result = _compile(compiler, scope_columns=["dept"])
        assert "HAVING COUNT(*) > 1" in result["violation_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler, scope_columns=["dept"])
        spark = result["compiled_spark"]
        assert "spark.table" in spark
        assert "Window" in spark
