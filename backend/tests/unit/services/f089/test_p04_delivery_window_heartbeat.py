"""P04 — Delivery Window + Heartbeat detailed tests."""

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


# ── Delivery Window ─────────────────────────────────────────────


class TestDeliveryWindow:
    def test_basic_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "load_ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "04:00",
            },
        )
        sql = r["compiled_sql"]
        assert "BETWEEN" in sql
        assert "120" in sql  # 02:00 = 120 min
        assert "240" in sql  # 04:00 = 240 min
        assert "EXTRACT(HOUR" in sql

    def test_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "00:00",
                "delivery_window_end": "06:00",
                "filter_expression": "feed = 'daily'",
            },
        )
        assert "feed = 'daily'" in r["compiled_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "04:00",
            },
        )
        assert "pyspark" in r["compiled_spark"]
        assert "minutes" in r["compiled_spark"]

    def test_no_violation_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "04:00",
            },
        )
        assert r["violation_sql"] == ""

    def test_missing_window_start(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_end": "04:00",
            },
        )
        assert "error" in r

    def test_missing_window_end(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "02:00",
            },
        )
        assert "error" in r

    def test_invalid_window_start(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "invalid",
                "delivery_window_end": "04:00",
            },
        )
        assert "error" in r

    def test_invalid_window_end(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "bad",
            },
        )
        assert "error" in r

    def test_midnight_window(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "00:00",
                "delivery_window_end": "06:00",
            },
        )
        sql = r["compiled_sql"]
        assert "BETWEEN 0 AND 360" in sql

    def test_timely_untimely_columns(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "04:00",
            },
        )
        assert "timely_rows" in r["compiled_sql"]
        assert "untimely_rows" in r["compiled_sql"]


# ── Heartbeat ───────────────────────────────────────────────────


class TestHeartbeat:
    def test_basic_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "heartbeat",
                "timestamp_column": "event_ts",
                "expected_frequency": "1h",
            },
        )
        sql = r["compiled_sql"]
        assert "MAX(" in sql
        assert "COUNT(*) > 0" in sql
        assert "3600" in sql

    def test_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "heartbeat",
                "timestamp_column": "ts",
                "expected_frequency": "30m",
                "filter_expression": "source = 'stream'",
            },
        )
        assert "source = 'stream'" in r["compiled_sql"]

    def test_spark_code(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "1h"},
        )
        assert "pyspark" in r["compiled_spark"]
        assert "cnt" in r["compiled_spark"]

    def test_no_violation_sql(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "1h"},
        )
        assert r["violation_sql"] == ""

    def test_missing_expected_frequency(self, compiler):
        r = _compile(compiler, {"timeliness_type": "heartbeat", "timestamp_column": "ts"})
        assert "error" in r

    def test_invalid_frequency(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "bad"},
        )
        assert "error" in r

    def test_minutes_frequency(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "15m"},
        )
        assert "900" in r["compiled_sql"]

    def test_days_frequency(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "1d"},
        )
        assert "86400" in r["compiled_sql"]

    def test_timely_untimely_columns(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "heartbeat", "timestamp_column": "ts", "expected_frequency": "1h"},
        )
        assert "timely_rows" in r["compiled_sql"]
        assert "untimely_rows" in r["compiled_sql"]
