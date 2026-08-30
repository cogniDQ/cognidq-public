"""P06 — Integration tests: E2E config → canonical → compiled → parsed."""

import sys
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# Stub pyspark
for mod_name in [
    "pyspark",
    "pyspark.sql",
    "pyspark.sql.functions",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_ssm = types.ModuleType("app.services.execution.spark_session_manager")
_ssm.SparkSessionManager = MagicMock
sys.modules.setdefault("app.services.execution.spark_session_manager", _ssm)

_se = types.ModuleType("app.services.execution.spark_executor")
_se.SparkCheckExecutor = MagicMock
sys.modules.setdefault("app.services.execution.spark_executor", _se)

from app.services.flows.node_handlers.check_node import CheckNodeHandler
from app.services.rules.compiler import RuleCompiler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


@pytest.fixture
def compiler():
    return RuleCompiler()


def _e2e(handler, compiler, config, schema="s", table="t"):
    canonical = handler._build_canonical_rule("timeliness", config, schema, table)
    compiled = compiler.compile_rule(canonical, target_schema=schema, target_table=table)
    return canonical, compiled


# ── E2E Per Type ────────────────────────────────────────────────


class TestEndToEndFreshness:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "freshness",
                "timestampColumn": "updated_at",
                "maxAge": "24h",
            },
        )
        assert "error" not in r
        assert "MAX" in r["compiled_sql"]
        assert "86400" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"columns": ["ts"], "maxAge": "1h", "pass_threshold": 90})
        rows = [{"total_rows": 100, "timely_rows": 100, "untimely_rows": 0, "age_seconds": 1800}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"
        assert result["timeliness_type"] == "freshness"
        assert result["data_age_seconds"] == 1800


class TestEndToEndRecordAge:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "record_age",
                "timestampColumn": "created_at",
                "maxAge": "30d",
            },
        )
        assert "error" not in r
        assert "SUM" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "record_age",
                "maxAge": "7d",
                "pass_threshold": 90,
            },
        )
        rows = [{"total_rows": 100, "timely_rows": 95, "untimely_rows": 5}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"
        assert result["rows_failed"] == 5


class TestEndToEndLatency:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "latency",
                "timestampColumn": "event_ts",
                "comparisonTimestamp": "load_ts",
                "maxAge": "2h",
            },
        )
        assert "error" not in r
        assert "load_ts" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "comparisonTimestamp": "load_ts",
                "maxAge": "1h",
                "pass_threshold": 95,
            },
        )
        rows = [{"total_rows": 200, "timely_rows": 200, "untimely_rows": 0}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"


class TestEndToEndProcessingDelay:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "processing_delay",
                "timestampColumn": "start_ts",
                "comparisonTimestamp": "end_ts",
                "maxAge": "30m",
            },
        )
        assert "error" not in r
        assert "1800" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "processing_delay",
                "comparisonTimestamp": "end_ts",
                "maxAge": "1h",
                "pass_threshold": 80,
            },
        )
        rows = [{"total_rows": 50, "timely_rows": 45, "untimely_rows": 5}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"


class TestEndToEndDeliveryWindow:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "delivery_window",
                "timestampColumn": "load_ts",
                "deliveryWindowStart": "02:00",
                "deliveryWindowEnd": "04:00",
            },
        )
        assert "error" not in r
        assert "BETWEEN" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "deliveryWindowStart": "02:00",
                "deliveryWindowEnd": "04:00",
                "pass_threshold": 90,
            },
        )
        rows = [{"total_rows": 100, "timely_rows": 100, "untimely_rows": 0}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"
        assert result["timeliness_type"] == "delivery_window"


class TestEndToEndHeartbeat:
    def test_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["ts"],
                "timelinessType": "heartbeat",
                "timestampColumn": "event_ts",
                "expectedFrequency": "1h",
            },
        )
        assert "error" not in r
        assert "GREATEST" in r["compiled_sql"]

    def test_full_pipeline(self, handler, compiler):
        c, r = _e2e(
            handler, compiler, {"columns": ["ts"], "expectedFrequency": "1h", "pass_threshold": 90}
        )
        rows = [{"total_rows": 50, "timely_rows": 50, "untimely_rows": 0}]
        result = handler._parse_timeliness_results(rows, c)
        assert result["check_status"] == "PASS"
        assert result["timeliness_type"] == "heartbeat"


# ── Backward Compat ─────────────────────────────────────────────


class TestBackwardCompat:
    def test_date_column(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"dateColumn": "updated_at", "maxAgeDays": 1})
        assert "error" not in r
        assert c["parameters"]["timestamp_column"] == "updated_at"
        assert c["parameters"]["max_age"] == "1d"

    def test_max_age_days(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"dateColumn": "ts", "maxAgeDays": 7})
        assert "error" not in r
        assert "604800" in r["compiled_sql"]


# ── Error Paths ─────────────────────────────────────────────────


class TestErrorPaths:
    def test_unknown_type(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"columns": ["a"], "timelinessType": "bogus"})
        assert "error" in r

    def test_missing_max_age_freshness(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "timelinessType": "freshness", "timestampColumn": "ts"},
        )
        assert "error" in r

    def test_missing_comparison_timestamp_latency(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "latency",
                "timestampColumn": "ts",
                "maxAge": "1h",
            },
        )
        assert "error" in r

    def test_missing_window_start(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "delivery_window",
                "timestampColumn": "ts",
                "deliveryWindowEnd": "04:00",
            },
        )
        assert "error" in r

    def test_missing_expected_frequency(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "timelinessType": "heartbeat", "timestampColumn": "ts"},
        )
        assert "error" in r

    def test_dangerous_filter(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "maxAge": "1h", "filterExpression": "1; DROP TABLE x"},
        )
        assert "error" in r

    def test_invalid_duration(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "freshness",
                "timestampColumn": "ts",
                "maxAge": "invalid",
            },
        )
        assert "error" in r

    def test_missing_max_age_record_age(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "timelinessType": "record_age", "timestampColumn": "ts"},
        )
        assert "error" in r


# ── Spark Output ────────────────────────────────────────────────


class TestSparkOutput:
    @pytest.mark.parametrize(
        "config",
        [
            {"timelinessType": "freshness", "maxAge": "1h"},
            {"timelinessType": "record_age", "maxAge": "7d"},
            {"timelinessType": "latency", "comparisonTimestamp": "load", "maxAge": "1h"},
            {"timelinessType": "processing_delay", "comparisonTimestamp": "end", "maxAge": "30m"},
            {
                "timelinessType": "delivery_window",
                "deliveryWindowStart": "02:00",
                "deliveryWindowEnd": "04:00",
            },
            {"timelinessType": "heartbeat", "expectedFrequency": "1h"},
        ],
    )
    def test_spark_present(self, handler, compiler, config):
        config["columns"] = ["ts"]
        config.setdefault("timestampColumn", "ts")
        c, r = _e2e(handler, compiler, config)
        assert "compiled_spark" in r
        assert "pyspark" in r["compiled_spark"]


# ── WARN Threshold ──────────────────────────────────────────────


class TestWarnThreshold:
    def test_pass(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "maxAge": "1h", "pass_threshold": 90, "thresholdWarn": 80},
        )
        rows = [{"total_rows": 100, "timely_rows": 95, "untimely_rows": 5}]
        r = handler._parse_timeliness_results(rows, c)
        assert r["check_status"] == "PASS"

    def test_warn(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "maxAge": "1h", "pass_threshold": 95, "thresholdWarn": 85},
        )
        rows = [{"total_rows": 100, "timely_rows": 90, "untimely_rows": 10}]
        r = handler._parse_timeliness_results(rows, c)
        assert r["check_status"] == "WARN"

    def test_fail(self, handler, compiler):
        c, _ = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "maxAge": "1h", "pass_threshold": 95, "thresholdWarn": 85},
        )
        rows = [{"total_rows": 100, "timely_rows": 70, "untimely_rows": 30}]
        r = handler._parse_timeliness_results(rows, c)
        assert r["check_status"] == "FAIL"


# ── Filter Expression ───────────────────────────────────────────


class TestFilterExpression:
    def test_filter_in_sql(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {"columns": ["a"], "maxAge": "1h", "filterExpression": "status = 'active'"},
        )
        assert "active" in r["compiled_sql"]


# ── Null Handling ───────────────────────────────────────────────


class TestNullHandling:
    def test_skip(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "record_age",
                "maxAge": "1d",
                "nullHandling": "skip",
            },
        )
        assert "IS NOT NULL" in r["compiled_sql"]

    def test_fail(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "record_age",
                "maxAge": "1d",
                "nullHandling": "fail",
            },
        )
        assert "IS NOT NULL" not in r["compiled_sql"]

    def test_pass(self, handler, compiler):
        c, r = _e2e(
            handler,
            compiler,
            {
                "columns": ["a"],
                "timelinessType": "record_age",
                "maxAge": "1d",
                "nullHandling": "pass",
            },
        )
        assert "IS NULL" in r["compiled_sql"]


# ── Duration Formats in E2E ─────────────────────────────────────


class TestDurationFormats:
    def test_minutes(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"columns": ["a"], "maxAge": "30m"})
        assert "1800" in r["compiled_sql"]

    def test_hours(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"columns": ["a"], "maxAge": "2h"})
        assert "7200" in r["compiled_sql"]

    def test_days(self, handler, compiler):
        c, r = _e2e(handler, compiler, {"columns": ["a"], "maxAge": "7d"})
        assert "604800" in r["compiled_sql"]


# ── Result Structure ────────────────────────────────────────────


class TestResultStructure:
    def test_all_required_fields(self, handler):
        rows = [{"total_rows": 10, "timely_rows": 8, "untimely_rows": 2}]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 90}}
        r = handler._parse_timeliness_results(rows, rule)
        for key in [
            "rows_scanned",
            "rows_passed",
            "rows_failed",
            "pass_rate",
            "timeliness_rate",
            "check_status",
            "timeliness_type",
            "zero_rows",
            "violations",
        ]:
            assert key in r

    def test_pass_rate_is_decimal(self, handler):
        rows = [{"total_rows": 3, "timely_rows": 2, "untimely_rows": 1}]
        rule = {"parameters": {"timeliness_type": "record_age", "threshold_pass": 50}}
        r = handler._parse_timeliness_results(rows, rule)
        assert isinstance(r["pass_rate"], Decimal)
