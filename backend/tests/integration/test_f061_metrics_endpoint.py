"""
F061 — Prometheus & Grafana Observability Stack
================================================
Integration tests for the /metrics scrape endpoint.

Tests:
    MET-01  GET /metrics returns 200
    MET-02  Content-Type is prometheus text format
    MET-03  Response body contains required HELP lines
    MET-04  Python GC metrics are present (default collector)
    MET-05  data_source_create_count metric is declared
    MET-06  dataset_create_count metric is declared
    MET-07  permission_audit_list_requests_total metric is declared
    MET-08  permission_audit_query_duration_ms metric is declared
    MET-09  /metrics is NOT listed in OpenAPI schema
    MET-10  Incrementing a known counter is reflected in /metrics output

Run inside Docker:
    docker exec dq-backend-1 python -m pytest \\
        tests/integration/test_f061_metrics_endpoint.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, Counter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metrics_text(client: TestClient) -> str:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    return resp.text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    def test_met_01_returns_200(self, client: TestClient):
        """MET-01 GET /metrics → 200."""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_met_02_content_type(self, client: TestClient):
        """MET-02 Content-Type begins with text/plain (Prometheus exposition format)."""
        resp = client.get("/metrics")
        assert resp.headers["content-type"].startswith("text/plain")

    def test_met_03_help_lines_present(self, client: TestClient):
        """MET-03 Response contains at least one # HELP line."""
        body = _metrics_text(client)
        assert "# HELP" in body

    def test_met_04_python_gc_metrics(self, client: TestClient):
        """MET-04 Default Python GC collector metrics are present."""
        body = _metrics_text(client)
        assert "python_gc_objects_collected_total" in body

    def test_met_05_data_source_create_count(self, client: TestClient):
        """MET-05 data_source_create_count metric is declared."""
        body = _metrics_text(client)
        assert "data_source_create_count" in body

    def test_met_06_dataset_create_count(self, client: TestClient):
        """MET-06 dataset_create_count metric is declared."""
        body = _metrics_text(client)
        assert "dataset_create_count" in body

    def test_met_07_permission_audit_list_requests_total(self, client: TestClient):
        """MET-07 permission_audit_list_requests_total metric is declared."""
        body = _metrics_text(client)
        assert "permission_audit_list_requests_total" in body

    def test_met_08_permission_audit_query_duration_ms(self, client: TestClient):
        """MET-08 permission_audit_query_duration_ms histogram is declared."""
        body = _metrics_text(client)
        assert "permission_audit_query_duration_ms" in body

    def test_met_09_not_in_openapi_schema(self, client: TestClient):
        """MET-09 /metrics does not appear in the OpenAPI schema paths."""
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        paths = resp.json().get("paths", {})
        assert "/metrics" not in paths

    def test_met_10_counter_increment_reflected(self, client: TestClient):
        """MET-10 A counter increment is visible in the next /metrics scrape."""
        # Use a test-specific counter so as not to pollute real metrics
        _test_counter = Counter(
            "f061_test_sentinel_total",
            "Sentinel counter for F061 test MET-10",
        )
        _test_counter.inc(3)

        body = _metrics_text(client)
        assert "f061_test_sentinel_total" in body
        # The _total sample for this counter must show 3.0
        for line in body.splitlines():
            if line.startswith("f061_test_sentinel_total") and not line.startswith("#"):
                value = float(line.split()[-1])
                assert value == 3.0
                break
        else:
            pytest.fail("f061_test_sentinel_total not found in /metrics output")
