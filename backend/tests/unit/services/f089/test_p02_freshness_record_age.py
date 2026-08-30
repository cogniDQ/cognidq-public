"""P02 — Freshness + Record Age detailed tests."""

import pytest
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def compiler():
    return RuleCompiler()


def _compile(compiler, params, column="ts_col"):
    return compiler.compile_rule(
        {
            "dimension": "timeliness",
            "entity": f"test_table.{column}",
            "condition": "",
            "expectation": "100%",
            "parameters": params,
        },
        target_table="test_table",
    )


# ── Freshness ───────────────────────────────────────────────────


class TestFreshness:
    def test_basic_sql_keywords(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "freshness", "timestamp_column": "updated_at", "max_age": "24h"},
        )
        sql = r["compiled_sql"]
        assert "MAX" in sql
        assert "EXTRACT(EPOCH" in sql
        assert "NOW()" in sql
        assert "86400" in sql

    def test_filter_expression(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "freshness",
                "timestamp_column": "ts",
                "max_age": "1h",
                "filter_expression": "region = 'EU'",
            },
        )
        assert "region = 'EU'" in r["compiled_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "freshness", "timestamp_column": "ts", "max_age": "1h"}
        )
        assert "pyspark" in r["compiled_spark"]
        assert "F.max" in r["compiled_spark"]

    def test_no_violation_sql(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "freshness", "timestamp_column": "ts", "max_age": "1h"}
        )
        assert r["violation_sql"] == ""

    def test_missing_timestamp_column(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "freshness", "timestamp_column": "", "max_age": "1h"}
        )
        assert "error" in r

    def test_missing_max_age(self, compiler):
        r = _compile(compiler, {"timeliness_type": "freshness", "timestamp_column": "ts"})
        assert "error" in r

    def test_invalid_duration(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "freshness", "timestamp_column": "ts", "max_age": "invalid"},
        )
        assert "error" in r

    def test_uses_column_as_fallback(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "freshness", "max_age": "1h"}, column="updated_at"
        )
        assert "updated_at" in r["compiled_sql"]

    def test_timely_untimely_columns(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "freshness", "timestamp_column": "ts", "max_age": "1h"}
        )
        assert "timely_rows" in r["compiled_sql"]
        assert "untimely_rows" in r["compiled_sql"]


# ── Record Age ──────────────────────────────────────────────────


class TestRecordAge:
    def test_basic_sql_keywords(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "record_age", "timestamp_column": "created_at", "max_age": "30d"},
        )
        sql = r["compiled_sql"]
        assert "SUM" in sql
        assert "CASE WHEN" in sql
        assert "2592000" in sql  # 30 * 86400

    def test_null_skip(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "record_age",
                "timestamp_column": "ts",
                "max_age": "1d",
                "null_handling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_null_fail(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "record_age",
                "timestamp_column": "ts",
                "max_age": "1d",
                "null_handling": "fail",
            },
        )
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "record_age",
                "timestamp_column": "ts",
                "max_age": "1d",
                "null_handling": "pass",
            },
        )
        assert "IS NULL" in r["compiled_sql"]  # COALESCE-like null handling

    def test_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "record_age",
                "timestamp_column": "ts",
                "max_age": "1d",
                "filter_expression": "active = true",
            },
        )
        assert "active = true" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "record_age", "timestamp_column": "ts", "max_age": "1d"}
        )
        assert "record_age_seconds" in r["violation_sql"]
        assert "86400" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "record_age", "timestamp_column": "ts", "max_age": "1d"}
        )
        assert "pyspark" in r["compiled_spark"]
        assert "_age_s" in r["compiled_spark"]

    def test_missing_timestamp(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "record_age", "timestamp_column": "", "max_age": "1d"}
        )
        assert "error" in r

    def test_missing_max_age(self, compiler):
        r = _compile(compiler, {"timeliness_type": "record_age", "timestamp_column": "ts"})
        assert "error" in r
