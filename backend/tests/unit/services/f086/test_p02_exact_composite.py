"""P02 — Exact & Composite Uniqueness Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler

TABLE = '"schema"."table"'


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **params):
    """Shortcut to compile a uniqueness rule with given params."""
    params.setdefault("columns", ["col"])
    return compiler._compile_uniqueness_rule(TABLE, "col", "", "", params)


# ---------------------------------------------------------------------------
# Exact mode — SQL generation
# ---------------------------------------------------------------------------
class TestExactMode:
    def test_basic_sql_structure(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["email"])
        sql = result["compiled_sql"]
        assert "GROUP BY" in sql
        assert "HAVING COUNT(*) > 1" in sql
        assert "total_rows" in sql
        assert "duplicate_groups" in sql
        assert "duplicate_rows" in sql
        assert "max_group_size" in sql
        assert "uniqueness_rate" in sql

    def test_null_handling_exclude(self, compiler):
        result = _compile(
            compiler, uniqueness_mode="exact", columns=["email"], null_handling="exclude"
        )
        sql = result["compiled_sql"]
        assert '"email" IS NOT NULL' in sql

    def test_null_handling_include(self, compiler):
        result = _compile(
            compiler, uniqueness_mode="exact", columns=["email"], null_handling="include"
        )
        sql = result["compiled_sql"]
        assert "COALESCE" in sql
        assert "__NULL__" in sql

    def test_case_insensitive(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["Name"], case_sensitive=False)
        sql = result["compiled_sql"]
        assert "LOWER" in sql

    def test_case_sensitive_default(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["Name"])
        sql = result["compiled_sql"]
        assert '"Name"' in sql
        assert "LOWER" not in sql

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler,
            uniqueness_mode="exact",
            columns=["email"],
            filter_expression="status = 'active'",
        )
        sql = result["compiled_sql"]
        assert "status = 'active'" in sql

    def test_violation_sql(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["email"])
        assert "violation_sql" in result
        assert "HAVING COUNT(*) > 1" in result["violation_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["email"])
        spark = result["compiled_spark"]
        assert "spark.table" in spark
        assert "Window" in spark

    def test_all_dialect_keys_present(self, compiler):
        result = _compile(compiler, uniqueness_mode="exact", columns=["email"])
        for key in [
            "compiled_sql",
            "compiled_postgres",
            "compiled_mysql",
            "compiled_snowflake",
            "compiled_spark",
            "violation_sql",
        ]:
            assert key in result

    def test_backward_compat_single_column_no_mode(self, compiler):
        """Old config: no uniqueness_mode, single column → should infer exact."""
        result = compiler._compile_uniqueness_rule(TABLE, "email", "", "", {"columns": ["email"]})
        assert "error" not in result
        assert "GROUP BY" in result["compiled_sql"]


# ---------------------------------------------------------------------------
# Composite mode — SQL generation
# ---------------------------------------------------------------------------
class TestCompositeMode:
    def test_multi_column_group_by(self, compiler):
        result = _compile(compiler, uniqueness_mode="composite", columns=["order_id", "line_item"])
        sql = result["compiled_sql"]
        assert '"order_id"' in sql
        assert '"line_item"' in sql
        assert "GROUP BY" in sql
        assert "HAVING COUNT(*) > 1" in sql

    def test_single_column_falls_back_to_exact(self, compiler):
        result = _compile(compiler, uniqueness_mode="composite", columns=["email"])
        sql = result["compiled_sql"]
        # Should work like exact mode (single column)
        assert "GROUP BY" in sql
        assert "error" not in result

    def test_null_handling_exclude_multi(self, compiler):
        result = _compile(
            compiler, uniqueness_mode="composite", columns=["a", "b"], null_handling="exclude"
        )
        sql = result["compiled_sql"]
        assert '"a" IS NOT NULL' in sql
        assert '"b" IS NOT NULL' in sql

    def test_null_handling_include_multi(self, compiler):
        result = _compile(
            compiler, uniqueness_mode="composite", columns=["a", "b"], null_handling="include"
        )
        sql = result["compiled_sql"]
        assert "COALESCE" in sql

    def test_case_insensitive_composite(self, compiler):
        result = _compile(
            compiler,
            uniqueness_mode="composite",
            columns=["first_name", "last_name"],
            case_sensitive=False,
        )
        sql = result["compiled_sql"]
        assert "LOWER" in sql

    def test_violation_sql_composite(self, compiler):
        result = _compile(compiler, uniqueness_mode="composite", columns=["a", "b"])
        assert "HAVING COUNT(*) > 1" in result["violation_sql"]
