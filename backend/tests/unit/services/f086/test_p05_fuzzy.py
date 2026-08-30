"""P05 — Fuzzy Duplicate Detection Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler

TABLE = '"schema"."table"'


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **params):
    params.setdefault("columns", ["company_name"])
    params.setdefault("uniqueness_mode", "fuzzy")
    return compiler._compile_uniqueness_rule(TABLE, "company_name", "", "", params)


class TestFuzzyMode:
    def test_levenshtein_sql(self, compiler):
        result = _compile(compiler, fuzzy_algorithm="levenshtein", fuzzy_threshold=0.85)
        sql = result["compiled_sql"]
        assert "levenshtein" in sql.lower()
        assert "CROSS JOIN" in sql
        assert "similarity" in sql
        assert "0.85" in sql

    def test_soundex_sql(self, compiler):
        result = _compile(compiler, fuzzy_algorithm="soundex")
        sql = result["compiled_sql"]
        assert "soundex" in sql.lower()

    def test_default_algorithm_levenshtein(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "levenshtein" in sql.lower()

    def test_default_threshold(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "0.85" in sql

    def test_custom_threshold(self, compiler):
        result = _compile(compiler, fuzzy_threshold=0.9)
        sql = result["compiled_sql"]
        assert "0.9" in sql

    def test_filter_expression(self, compiler):
        result = _compile(compiler, filter_expression="active = true")
        sql = result["compiled_sql"]
        assert "active = true" in sql

    def test_violation_sql_returns_pairs(self, compiler):
        result = _compile(compiler, fuzzy_algorithm="levenshtein", fuzzy_threshold=0.85)
        vsql = result["violation_sql"]
        assert "similarity" in vsql
        assert "CROSS JOIN" in vsql

    def test_spark_code(self, compiler):
        result = _compile(compiler)
        spark = result["compiled_spark"]
        assert "spark.table" in spark

    def test_total_rows_in_sql(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "total_rows" in sql

    def test_null_filtered_in_pairs(self, compiler):
        result = _compile(compiler)
        sql = result["compiled_sql"]
        assert "IS NOT NULL" in sql
