"""P01 — Timeliness compiler infrastructure tests."""

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


# ── Constants ───────────────────────────────────────────────────


class TestConstants:
    def test_valid_timeliness_types_count(self):
        assert len(RuleCompiler.VALID_TIMELINESS_TYPES) == 6

    @pytest.mark.parametrize(
        "t",
        ["freshness", "record_age", "latency", "processing_delay", "delivery_window", "heartbeat"],
    )
    def test_valid_type(self, t):
        assert t in RuleCompiler.VALID_TIMELINESS_TYPES

    def test_valid_metric_types_count(self):
        assert len(RuleCompiler.VALID_METRIC_TYPES) == 4

    @pytest.mark.parametrize("m", ["max", "avg", "p95", "p99"])
    def test_valid_metric(self, m):
        assert m in RuleCompiler.VALID_METRIC_TYPES

    def test_dataset_level_types(self):
        assert RuleCompiler.DATASET_LEVEL_TYPES == {"freshness", "delivery_window", "heartbeat"}

    def test_row_level_types(self):
        assert RuleCompiler.ROW_LEVEL_TYPES == {"record_age", "latency", "processing_delay"}


# ── Duration Parser ─────────────────────────────────────────────


class TestDurationParser:
    def test_minutes(self):
        assert RuleCompiler._parse_duration_to_seconds("30m") == 1800

    def test_hours(self):
        assert RuleCompiler._parse_duration_to_seconds("24h") == 86400

    def test_days(self):
        assert RuleCompiler._parse_duration_to_seconds("7d") == 604800

    def test_numeric_int(self):
        assert RuleCompiler._parse_duration_to_seconds(3600) == 3600

    def test_numeric_string(self):
        assert RuleCompiler._parse_duration_to_seconds("3600") == 3600

    def test_float_duration(self):
        assert RuleCompiler._parse_duration_to_seconds("1.5h") == 5400

    def test_invalid(self):
        assert RuleCompiler._parse_duration_to_seconds("invalid") is None

    def test_none(self):
        assert RuleCompiler._parse_duration_to_seconds(None) is None


# ── Window Time Parser ──────────────────────────────────────────


class TestWindowTimeParser:
    def test_early_morning(self):
        assert RuleCompiler._parse_window_time("02:00") == 120

    def test_afternoon(self):
        assert RuleCompiler._parse_window_time("14:30") == 870

    def test_midnight(self):
        assert RuleCompiler._parse_window_time("00:00") == 0

    def test_end_of_day(self):
        assert RuleCompiler._parse_window_time("23:59") == 1439

    def test_invalid(self):
        assert RuleCompiler._parse_window_time("invalid") is None

    def test_none(self):
        assert RuleCompiler._parse_window_time(None) is None


# ── Type Inference ──────────────────────────────────────────────


class TestTypeInference:
    def test_default_freshness(self):
        assert RuleCompiler._infer_timeliness_type({}) == "freshness"

    def test_comparison_timestamp_latency(self):
        assert RuleCompiler._infer_timeliness_type({"comparison_timestamp": "load_ts"}) == "latency"

    def test_delivery_window(self):
        assert (
            RuleCompiler._infer_timeliness_type({"delivery_window_start": "02:00"})
            == "delivery_window"
        )

    def test_expected_frequency_heartbeat(self):
        assert RuleCompiler._infer_timeliness_type({"expected_frequency": "1h"}) == "heartbeat"

    def test_priority_comparison_over_window(self):
        assert (
            RuleCompiler._infer_timeliness_type(
                {"comparison_timestamp": "x", "delivery_window_start": "02:00"}
            )
            == "latency"
        )

    def test_priority_window_over_frequency(self):
        assert (
            RuleCompiler._infer_timeliness_type(
                {"delivery_window_start": "02:00", "expected_frequency": "1h"}
            )
            == "delivery_window"
        )


# ── Dispatcher Routing ──────────────────────────────────────────


class TestDispatcher:
    @pytest.mark.parametrize(
        "tt",
        ["freshness", "record_age", "latency", "processing_delay", "delivery_window", "heartbeat"],
    )
    def test_routes_to_valid_type(self, compiler, tt):
        params = {"timeliness_type": tt, "timestamp_column": "ts", "max_age": "1h"}
        if tt in ("latency", "processing_delay"):
            params["comparison_timestamp"] = "load_ts"
        if tt == "delivery_window":
            params["delivery_window_start"] = "02:00"
            params["delivery_window_end"] = "04:00"
        if tt == "heartbeat":
            params["expected_frequency"] = "1h"
        r = _compile(compiler, params)
        assert "error" not in r

    def test_unknown_type_error(self, compiler):
        r = _compile(compiler, {"timeliness_type": "bogus", "timestamp_column": "ts"})
        assert "error" in r
        assert "Unknown timeliness type" in r["error"]


# ── Null Handling SQL ───────────────────────────────────────────


class TestNullHandling:
    def test_skip(self):
        cond, mode = RuleCompiler._timeliness_null_handling_sql(["ts_col"], "skip")
        assert "IS NOT NULL" in cond
        assert mode == "skip"

    def test_fail(self):
        cond, mode = RuleCompiler._timeliness_null_handling_sql(["ts_col"], "fail")
        assert cond == ""
        assert mode == "fail"

    def test_pass(self):
        cond, mode = RuleCompiler._timeliness_null_handling_sql(["ts_col"], "pass")
        assert cond == ""
        assert mode == "pass"

    def test_multi_column(self):
        cond, _ = RuleCompiler._timeliness_null_handling_sql(["a", "b"], "skip")
        assert '"a" IS NOT NULL' in cond
        assert '"b" IS NOT NULL' in cond


# ── Error Result Structure ──────────────────────────────────────


class TestErrorResult:
    def test_error_structure(self):
        r = RuleCompiler._timeliness_error_result("test error")
        assert r["error"] == "test error"
        assert "-- ERROR" in r["compiled_sql"]
        assert "# ERROR" in r["compiled_spark"]


# ── Filter Validation ───────────────────────────────────────────


class TestFilterValidation:
    def test_valid_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "freshness",
                "timestamp_column": "ts",
                "max_age": "1h",
                "filter_expression": "status = 'active'",
            },
        )
        assert "error" not in r
        assert "active" in r["compiled_sql"]

    def test_dangerous_filter(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "freshness",
                "timestamp_column": "ts",
                "max_age": "1h",
                "filter_expression": "1; DROP TABLE x",
            },
        )
        assert "error" in r


# ── Quick SQL Validation Per Type ───────────────────────────────


class TestQuickSQLPerType:
    def test_freshness_sql(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "freshness", "timestamp_column": "updated_at", "max_age": "24h"},
        )
        assert "MAX" in r["compiled_sql"]
        assert "updated_at" in r["compiled_sql"]
        assert "86400" in r["compiled_sql"]

    def test_record_age_sql(self, compiler):
        r = _compile(
            compiler,
            {"timeliness_type": "record_age", "timestamp_column": "created_at", "max_age": "7d"},
        )
        assert "SUM" in r["compiled_sql"]
        assert "created_at" in r["compiled_sql"]
        assert "604800" in r["compiled_sql"]

    def test_latency_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "latency",
                "timestamp_column": "event_ts",
                "comparison_timestamp": "load_ts",
                "max_age": "2h",
            },
        )
        assert "load_ts" in r["compiled_sql"]
        assert "event_ts" in r["compiled_sql"]
        assert "7200" in r["compiled_sql"]

    def test_processing_delay_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "processing_delay",
                "timestamp_column": "start_ts",
                "comparison_timestamp": "end_ts",
                "max_age": "30m",
            },
        )
        assert "end_ts" in r["compiled_sql"]
        assert "start_ts" in r["compiled_sql"]
        assert "1800" in r["compiled_sql"]

    def test_delivery_window_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "delivery_window",
                "timestamp_column": "load_ts",
                "delivery_window_start": "02:00",
                "delivery_window_end": "04:00",
            },
        )
        assert "BETWEEN" in r["compiled_sql"]
        assert "120" in r["compiled_sql"]
        assert "240" in r["compiled_sql"]

    def test_heartbeat_sql(self, compiler):
        r = _compile(
            compiler,
            {
                "timeliness_type": "heartbeat",
                "timestamp_column": "event_ts",
                "expected_frequency": "1h",
            },
        )
        assert "MAX(" in r["compiled_sql"]
        assert "3600" in r["compiled_sql"]
