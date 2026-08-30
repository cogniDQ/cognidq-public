"""P04 — Derived Value Tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _derived_params(**overrides):
    base = {
        "accuracy_type": "derived_value",
        "formula": '"quantity" * "unit_price"',
        "threshold_pass": 95,
    }
    base.update(overrides)
    return base


def _compile(compiler, column="total", **overrides):
    params = _derived_params(**overrides)
    return compiler.compile_rule(
        {
            "dimension": "accuracy",
            "entity": f"invoices.{column}",
            "condition": "",
            "expectation": "95%",
            "parameters": params,
        },
        target_table="invoices",
    )


class TestDerivedValueBasic:
    def test_basic_sql_structure(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "accurate_rows" in sql
        assert "inaccurate_rows" in sql
        assert "quantity" in sql
        assert "unit_price" in sql

    def test_exact_match_default(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert '("total") = (("quantity" * "unit_price"))' in sql

    def test_self_referential_verified_equals_total(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "COUNT(*) AS verified_rows" in sql
        assert "0 AS unverifiable_rows" in sql

    def test_violation_sql(self, compiler):
        result = _compile(compiler)
        assert "SELECT *" in result["violation_sql"]
        assert '("total") != (("quantity" * "unit_price"))' in result["violation_sql"]

    def test_spark_code(self, compiler):
        result = _compile(compiler)
        assert "pyspark" in result["compiled_spark"]
        assert "accurate_rows" in result["compiled_spark"]


class TestDerivedValueTolerance:
    def test_absolute_tolerance(self, compiler):
        result = _compile(compiler, tolerance_type="absolute", tolerance_value=0.01)
        sql = result["compiled_sql"]
        assert "ABS" in sql
        assert "<= 0.01" in sql

    def test_percentage_tolerance(self, compiler):
        result = _compile(compiler, tolerance_type="percentage", tolerance_value=1.0)
        sql = result["compiled_sql"]
        assert "NULLIF" in sql
        assert "<= 1.0" in sql

    def test_invalid_tolerance_type(self, compiler):
        result = _compile(compiler, tolerance_type="distance")
        assert "error" in result
        assert "Invalid tolerance_type" in result["error"]


class TestDerivedValueFilter:
    def test_filter_in_sql(self, compiler):
        result = _compile(compiler, filter_expression="status = 'completed'")
        assert "status = 'completed'" in result["compiled_sql"]

    def test_dangerous_formula_rejected(self, compiler):
        result = _compile(compiler, formula="1; DROP TABLE users")
        assert "error" in result
        assert "Dangerous formula" in result["error"]


class TestDerivedValueNullHandling:
    def test_null_skip(self, compiler):
        result = _compile(compiler, null_handling="skip")
        assert '"total" IS NOT NULL' in result["compiled_sql"]

    def test_null_pass(self, compiler):
        result = _compile(compiler, null_handling="pass")
        sql = result["compiled_sql"]
        assert '"total" IS NULL OR' in sql

    def test_null_fail_default(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "IS NULL OR" not in sql


class TestDerivedValueErrors:
    def test_missing_formula_error(self, compiler):
        result = _compile(compiler, formula=None)
        assert "error" in result
        assert "formula is required" in result["error"]
