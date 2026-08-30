"""P03 — Latency + Processing Delay detailed tests."""

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


# ── Latency ─────────────────────────────────────────────────────


class TestLatency:
    def test_basic_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "event_ts",
                "comparison_timestamp": "load_ts",
                "max_age": "2h",
            },
        )
        sql = r["compiled_sql"]
        assert '"load_ts"' in sql
        assert '"event_ts"' in sql
        assert "7200" in sql

    def test_null_skip(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "null_handling": "skip",
            },
        )
        assert '"a" IS NOT NULL' in r["compiled_sql"]
        assert '"b" IS NOT NULL' in r["compiled_sql"]

    def test_null_fail(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "null_handling": "fail",
            },
        )
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "null_handling": "pass",
            },
        )
        assert "IS NULL" in r["compiled_sql"]

    def test_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "filter_expression": "type = 'order'",
            },
        )
        assert "type = 'order'" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
            },
        )
        assert "delay_seconds" in r["violation_sql"]
        assert "3600" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "_delay_s" in r["compiled_spark"]

    def test_missing_comparison_timestamp(self, compiler):
        r = _compile(
            compiler, {"timeliness_type": "latency", "timestamp_column": "a", "max_age": "1h"}
        )
        assert "error" in r

    def test_missing_max_age(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "latency", "timestamp_column": "a", "comparison_timestamp": "b"},
        )
        assert "error" in r


# ── Processing Delay ────────────────────────────────────────────


class TestProcessingDelay:
    def test_basic_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "start_ts",
                "comparison_timestamp": "end_ts",
                "max_age": "30m",
            },
        )
        sql = r["compiled_sql"]
        assert '"end_ts"' in sql
        assert '"start_ts"' in sql
        assert "1800" in sql

    def test_null_skip(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "null_handling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_null_pass(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "null_handling": "pass",
            },
        )
        assert "IS NULL" in r["compiled_sql"]

    def test_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
                "filter_expression": "status = 'done'",
            },
        )
        assert "status = 'done'" in r["compiled_sql"]

    def test_violation_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
            },
        )
        assert "delay_seconds" in r["violation_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "a",
                "comparison_timestamp": "b",
                "max_age": "1h",
            },
        )
        assert "pyspark" in r["compiled_spark"]

    def test_missing_comparison_timestamp(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "processing_delay", "timestamp_column": "a", "max_age": "1h"},
        )
        assert "error" in r
