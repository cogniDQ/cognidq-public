"""P06 — Temporal Uniqueness Mode tests."""

import pytest
from app.services.rules.compiler import RuleCompiler

TABLE = '"schema"."table"'


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, **params):
    params.setdefault("columns", ["customer_id"])
    params.setdefault("uniqueness_mode", "temporal")
    return compiler._compile_uniqueness_rule(TABLE, "customer_id", "", "", params)


class TestTemporalMode:
    def test_basic_temporal_sql(self, compiler):
        result = _compile(compiler, temporal_column="created_at", temporal_window="1d")
        sql = result["compiled_sql"]
        assert "JOIN" in sql
        assert "EXTRACT(EPOCH" in sql
        assert "86400" in sql  # 1d = 86400 seconds
        assert "total_rows" in sql
        assert "duplicate_rows" in sql

    def test_hours_window(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="2h")
        sql = result["compiled_sql"]
        assert "7200" in sql  # 2h = 7200 seconds

    def test_minutes_window(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="30m")
        sql = result["compiled_sql"]
        assert "1800" in sql  # 30m = 1800 seconds

    def test_seconds_window(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="60s")
        sql = result["compiled_sql"]
        assert "60" in sql

    def test_missing_temporal_column_error(self, compiler):
        result = _compile(compiler, temporal_window="1d")
        assert result["error"] is True
        assert "temporal_column" in result["error_message"]

    def test_missing_temporal_window_error(self, compiler):
        result = _compile(compiler, temporal_column="ts")
        assert result["error"] is True
        assert "temporal_window" in result["error_message"]

    def test_invalid_window_format_error(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="abc")
        assert result["error"] is True
        assert "Invalid temporal_window" in result["error_message"]

    def test_null_handling_exclude(self, compiler):
        result = _compile(
            compiler, temporal_column="ts", temporal_window="1d", null_handling="exclude"
        )
        sql = result["compiled_sql"]
        assert "IS NOT NULL" in sql

    def test_filter_expression(self, compiler):
        result = _compile(
            compiler, temporal_column="ts", temporal_window="1d", filter_expression="region = 'US'"
        )
        sql = result["compiled_sql"]
        assert "region = 'US'" in sql

    def test_violation_sql(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="1d")
        vsql = result["violation_sql"]
        assert "JOIN" in vsql
        assert "EXTRACT(EPOCH" in vsql

    def test_spark_code(self, compiler):
        result = _compile(compiler, temporal_column="ts", temporal_window="1d")
        spark = result["compiled_spark"]
        assert "spark.table" in spark
        assert "unix_timestamp" in spark
