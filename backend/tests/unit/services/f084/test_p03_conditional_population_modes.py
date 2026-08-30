"""P03 — Conditional & Population Modes tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, mode, **extra):
    params = {"columns": ["email"], "check_mode": mode}
    params.update(extra)
    return compiler._compile_completeness_rule('"orders"', "email", "IS NOT NULL", "100%", params)


# ---------------------------------------------------------------------------
# Conditional mode
# ---------------------------------------------------------------------------
class TestCompletenessConditional:
    def test_single_condition_value(self, compiler):
        result = _compile(compiler, "conditional", condition_column="country", condition_value="US")
        sql = result["compiled_sql"]
        assert '"country" IS NOT NULL' in sql
        assert '"country" IN' in sql
        assert "'US'" in sql
        assert result.get("error") is not True

    def test_list_condition_values(self, compiler):
        result = _compile(
            compiler, "conditional", condition_column="country", condition_value=["US", "UK"]
        )
        sql = result["compiled_sql"]
        assert "'US'" in sql
        assert "'UK'" in sql

    def test_excludes_null_condition_column(self, compiler):
        result = _compile(compiler, "conditional", condition_column="country", condition_value="US")
        sql = result["compiled_sql"]
        assert '"country" IS NOT NULL' in sql

    def test_with_filter(self, compiler):
        result = _compile(
            compiler,
            "conditional",
            condition_column="country",
            condition_value="US",
            filter_expression="year > 2020",
        )
        assert "year > 2020" in result["compiled_sql"]
        assert "year > 2020" in result["violation_sql"]

    def test_missing_condition_column_error(self, compiler):
        result = _compile(compiler, "conditional", condition_value="US")
        assert result["error"] is True
        assert "condition_column" in result["error_message"]

    def test_missing_condition_value_error(self, compiler):
        result = _compile(compiler, "conditional", condition_column="country")
        assert result["error"] is True
        assert "condition_value" in result["error_message"]

    def test_violation_sql(self, compiler):
        result = _compile(compiler, "conditional", condition_column="country", condition_value="US")
        vsql = result["violation_sql"]
        assert '"country" IS NOT NULL' in vsql
        assert '"email" IS NULL' in vsql

    def test_spark_code_present(self, compiler):
        result = _compile(compiler, "conditional", condition_column="country", condition_value="US")
        assert "pyspark" in result["compiled_spark"]
        assert "isin" in result["compiled_spark"]


# ---------------------------------------------------------------------------
# Population mode
# ---------------------------------------------------------------------------
class TestCompletenessPopulation:
    def test_delegates_to_null(self, compiler):
        """Population mode produces identical SQL to null mode."""
        null_result = _compile(compiler, "null")
        pop_result = _compile(compiler, "population")
        assert null_result["compiled_sql"] == pop_result["compiled_sql"]
        assert null_result["violation_sql"] == pop_result["violation_sql"]
