"""P05 — Group Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **extra):
    params = {"columns": ["email"], "check_mode": "group", "group_by_columns": ["country"]}
    params.update(extra)
    return compiler._compile_completeness_rule(
        '"customers"', "email", "IS NOT NULL", "100%", params
    )


class TestGroupMode:
    def test_single_group_column(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert '"country"' in sql
        assert "GROUP BY" in sql
        assert "ORDER BY completeness_rate ASC" in sql
        assert result.get("error") is not True

    def test_two_group_columns(self, compiler):
        result = _compile(compiler, group_by_columns=["country", "region"])
        sql = result["compiled_sql"]
        assert '"country"' in sql
        assert '"region"' in sql
        assert 'GROUP BY "country", "region"' in sql

    def test_group_columns_in_select(self, compiler):
        result = _compile(compiler, group_by_columns=["country", "region"])
        sql = result["compiled_sql"]
        # Group columns should appear in SELECT before aggregate columns
        select_pos = sql.index("SELECT")
        from_pos = sql.index("FROM")
        select_section = sql[select_pos:from_pos]
        assert '"country"' in select_section
        assert '"region"' in select_section

    def test_order_by_asc(self, compiler):
        result = _compile(compiler)
        assert "ORDER BY completeness_rate ASC" in result["compiled_sql"]

    def test_violation_sql_not_grouped(self, compiler):
        result = _compile(compiler)
        vsql = result["violation_sql"]
        assert "GROUP BY" not in vsql
        assert '"email" IS NULL' in vsql

    def test_empty_group_columns_error(self, compiler):
        result = _compile(compiler, group_by_columns=[])
        assert result["error"] is True
        assert "group_by_columns" in result["error_message"]

    def test_with_filter(self, compiler):
        result = _compile(compiler, filter_expression="year > 2020")
        sql = result["compiled_sql"]
        assert "year > 2020" in sql
        # Filter should appear before GROUP BY
        where_pos = sql.index("year > 2020")
        group_pos = sql.index("GROUP BY")
        assert where_pos < group_pos

    def test_spark_code_present(self, compiler):
        result = _compile(compiler)
        assert "pyspark" in result["compiled_spark"]
        assert "groupBy" in result["compiled_spark"]
