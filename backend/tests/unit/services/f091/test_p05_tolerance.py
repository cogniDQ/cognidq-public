"""P05 — Tolerance Handler Tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params):
    return compiler.compile_rule(
        {
            "dimension": "reconciliation",
            "entity": "src",
            "condition": "",
            "expectation": "100%",
            "parameters": params,
        },
        target_table="src",
    )


BASE = {"source_dataset": "bank_src", "target_dataset": "bank_tgt", "threshold_pass": 100}


class TestToleranceRequired:
    def test_requires_join_keys(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        result = _compile(compiler, params)
        assert "error" in result
        assert "join_keys" in result["error"]

    def test_requires_tolerance_value_for_absolute(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
        }
        result = _compile(compiler, params)
        assert "error" in result
        assert "tolerance_value" in result["error"]

    def test_requires_tolerance_value_for_percentage(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "percentage",
        }
        result = _compile(compiler, params)
        assert "error" in result
        assert "tolerance_value" in result["error"]

    def test_invalid_tolerance_type(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "relative",
            "tolerance_value": 5,
        }
        result = _compile(compiler, params)
        assert "error" in result
        assert "Invalid" in result["error"]


class TestToleranceAbsolute:
    def test_abs_in_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["txn_id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "ABS" in sql

    def test_tolerance_value_in_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["txn_id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.5,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "0.5" in sql

    def test_within_tolerance_count(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 1,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "within_tolerance" in sql

    def test_outside_tolerance_count(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 1,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "outside_tolerance" in sql

    def test_inner_join(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "INNER JOIN" in sql


class TestTolerancePercentage:
    def test_nullif_in_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "percentage",
            "tolerance_value": 5.0,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "NULLIF" in sql

    def test_percentage_value_in_sql(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "percentage",
            "tolerance_value": 2.5,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "2.5" in sql


class TestToleranceNone:
    def test_exact_match(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "none",
            "tolerance_value": 0,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        # exact match uses = operator
        assert "within_tolerance" in sql


class TestToleranceFilters:
    def test_source_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
            "source_filter": "currency = 'USD'",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "currency = 'USD'" in sql

    def test_target_filter(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
            "target_filter": "settled = true",
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert "settled = true" in sql


class TestToleranceJoinKeys:
    def test_single_key(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["txn_id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"txn_id"' in sql

    def test_multiple_keys(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["region", "date"],
            "tolerance_type": "absolute",
            "tolerance_value": 1,
        }
        sql = _compile(compiler, params)["compiled_sql"]
        assert '"region"' in sql
        assert '"date"' in sql


class TestToleranceViolation:
    def test_violation_sql_present(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        vsql = _compile(compiler, params)["violation_sql"]
        assert vsql
        assert "WHERE" in vsql


class TestToleranceSpark:
    def test_spark_code(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        spark = _compile(compiler, params)["compiled_spark"]
        assert "within_tolerance" in spark
        assert "inner" in spark

    def test_spark_abs(self, compiler):
        params = {
            **BASE,
            "reconciliation_type": "tolerance",
            "join_keys": ["id"],
            "tolerance_type": "absolute",
            "tolerance_value": 0.01,
        }
        spark = _compile(compiler, params)["compiled_spark"]
        assert "abs" in spark.lower()
