"""P05 — Handler mapping + result parsing tests for timeliness."""

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
    "app.services.execution.spark_executor",
    "app.services.execution.spark_session_manager",
    "app.services.execution",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules["app.services.execution.spark_executor"].SparkCheckExecutor = MagicMock
sys.modules["app.services.execution.spark_session_manager"].SparkSessionManager = MagicMock
sys.modules["app.services.execution"].SparkSessionManager = MagicMock

from app.services.flows.node_handlers.check_node import CheckNodeHandler


@pytest.fixture
def handler():
    return CheckNodeHandler.__new__(CheckNodeHandler)


def _build(handler, config, schema="s", table="t"):
    return handler._build_canonical_rule("timeliness", config, schema, table)


# ── Type Inference ──────────────────────────────────────────────


class TestTypeInference:
    def test_default_freshness(self, handler):
        c = _build(handler, {"columns": ["ts"], "maxAge": "1h"})
        assert c["parameters"]["timeliness_type"] == "freshness"

    def test_explicit_type(self, handler):
        c = _build(handler, {"columns": ["ts"], "timelinessType": "record_age", "maxAge": "7d"})
        assert c["parameters"]["timeliness_type"] == "record_age"

    def test_infer_latency(self, handler):
        c = _build(handler, {"columns": ["ts"], "comparisonTimestamp": "load_ts", "maxAge": "1h"})
        assert c["parameters"]["timeliness_type"] == "latency"

    def test_infer_delivery_window(self, handler):
        c = _build(
            handler,
            {"columns": ["ts"], "deliveryWindowStart": "02:00", "deliveryWindowEnd": "04:00"},
        )
        assert c["parameters"]["timeliness_type"] == "delivery_window"

    def test_infer_heartbeat(self, handler):
        c = _build(handler, {"columns": ["ts"], "expectedFrequency": "1h"})
        assert c["parameters"]["timeliness_type"] == "heartbeat"

    def test_infer_from_max_age(self, handler):
        c = _build(handler, {"columns": ["ts"], "maxAge": "24h"})
        assert c["parameters"]["timeliness_type"] == "freshness"

    def test_infer_from_date_column(self, handler):
        c = _build(handler, {"columns": ["ts"], "dateColumn": "updated_at", "maxAgeDays": 7})
        assert c["parameters"]["timeliness_type"] == "freshness"

    def test_infer_from_max_age_days(self, handler):
        c = _build(handler, {"dateColumn": "ts", "maxAgeDays": 30})
        assert c["parameters"]["timeliness_type"] == "freshness"


# ── Key Forwarding ──────────────────────────────────────────────


class TestKeyForwarding:
    def test_timestamp_column(self, handler):
        c = _build(handler, {"columns": ["a"], "timestampColumn": "updated_at", "maxAge": "1h"})
        assert c["parameters"]["timestamp_column"] == "updated_at"

    def test_comparison_timestamp(self, handler):
        c = _build(handler, {"columns": ["a"], "comparisonTimestamp": "load_ts", "maxAge": "1h"})
        assert c["parameters"]["comparison_timestamp"] == "load_ts"

    def test_max_age(self, handler):
        c = _build(handler, {"columns": ["a"], "maxAge": "24h"})
        assert c["parameters"]["max_age"] == "24h"

    def test_metric_type(self, handler):
        c = _build(
            handler,
            {"columns": ["a"], "metricType": "p95", "comparisonTimestamp": "b", "maxAge": "1h"},
        )
        assert c["parameters"]["metric_type"] == "p95"

    def test_delivery_window_start(self, handler):
        c = _build(
            handler,
            {"columns": ["a"], "deliveryWindowStart": "02:00", "deliveryWindowEnd": "04:00"},
        )
        assert c["parameters"]["delivery_window_start"] == "02:00"

    def test_delivery_window_end(self, handler):
        c = _build(
            handler,
            {"columns": ["a"], "deliveryWindowStart": "02:00", "deliveryWindowEnd": "04:00"},
        )
        assert c["parameters"]["delivery_window_end"] == "04:00"

    def test_expected_frequency(self, handler):
        c = _build(handler, {"columns": ["a"], "expectedFrequency": "30m"})
        assert c["parameters"]["expected_frequency"] == "30m"

    def test_null_handling(self, handler):
        c = _build(handler, {"columns": ["a"], "nullHandling": "skip", "maxAge": "1h"})
        assert c["parameters"]["null_handling"] == "skip"

    def test_threshold_warn(self, handler):
        c = _build(handler, {"columns": ["a"], "thresholdWarn": 85, "maxAge": "1h"})
        assert c["parameters"]["threshold_warn"] == 85

    def test_filter_expression(self, handler):
        c = _build(handler, {"columns": ["a"], "filterExpression": "active = true", "maxAge": "1h"})
        assert c["parameters"]["filter_expression"] == "active = true"


# ── Backward Compat ─────────────────────────────────────────────


class TestBackwardCompat:
    def test_date_column_maps_to_timestamp_column(self, handler):
        c = _build(handler, {"dateColumn": "updated_at", "maxAgeDays": 1})
        assert c["parameters"]["timestamp_column"] == "updated_at"

    def test_max_age_days_maps_to_max_age(self, handler):
        c = _build(handler, {"dateColumn": "ts", "maxAgeDays": 7})
        assert c["parameters"]["max_age"] == "7d"

    def test_dimension_is_timeliness(self, handler):
        c = _build(handler, {"dateColumn": "ts", "maxAgeDays": 1})
        assert c["dimension"] == "timeliness"

    def test_entity_format(self, handler):
        c = _build(handler, {"columns": ["ts"], "maxAge": "1h"}, schema="public", table="orders")
        assert "orders" in c["entity"]
        assert "ts" in c["entity"]


# ── Result Parsing ──────────────────────────────────────────────


class TestResultParsing:
    def test_pass(self, handler):
        rows = [{"total_rows": 100, "timely_rows": 100, "untimely_rows": 0}]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["check_status"] == "PASS"

    def test_fail(self, handler):
        rows = [{"total_rows": 100, "timely_rows": 80, "untimely_rows": 20}]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["check_status"] == "FAIL"

    def test_warn(self, handler):
        rows = [{"total_rows": 100, "timely_rows": 92, "untimely_rows": 8}]
        rule = {
            "parameters": {
                "timeliness_type": "record_age",
                "threshold_pass": 95,
                "threshold_warn": 90,
            }
        }
        r = handler._parse_timeliness_results(rows, rule)
        assert r["check_status"] == "WARN"

    def test_timeliness_type_in_result(self, handler):
        rows = [{"total_rows": 10, "timely_rows": 10, "untimely_rows": 0}]
        rule = {"parameters": {"timeliness_type": "latency", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["timeliness_type"] == "latency"

    def test_timeliness_rate(self, handler):
        rows = [{"total_rows": 200, "timely_rows": 190, "untimely_rows": 10}]
        rule = {"parameters": {"timeliness_type": "record_age", "threshold_pass": 90}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["timeliness_rate"] == Decimal(190) / Decimal(200) * Decimal(100)

    def test_zero_rows(self, handler):
        rows = [{"total_rows": 0, "timely_rows": 0, "untimely_rows": 0}]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["zero_rows"] is True

    def test_pass_rate_is_decimal(self, handler):
        rows = [{"total_rows": 3, "timely_rows": 2, "untimely_rows": 1}]
        rule = {"parameters": {"timeliness_type": "record_age", "threshold_pass": 50}}
        r = handler._parse_timeliness_results(rows, rule)
        assert isinstance(r["pass_rate"], Decimal)

    def test_extra_metadata_age(self, handler):
        rows = [{"total_rows": 10, "timely_rows": 10, "untimely_rows": 0, "age_seconds": 3600}]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["data_age_seconds"] == 3600

    def test_extra_metadata_most_recent(self, handler):
        rows = [
            {"total_rows": 10, "timely_rows": 10, "untimely_rows": 0, "most_recent": "2026-04-01"}
        ]
        rule = {"parameters": {"timeliness_type": "freshness", "threshold_pass": 100}}
        r = handler._parse_timeliness_results(rows, rule)
        assert r["most_recent"] == "2026-04-01"
