"""
Integration tests for F098 — Anomaly Detection Dashboard.

Tests all 4 anomaly detection API endpoints against the running application.
Uses real JWTs and the actual database.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


def _get_settings():
    from app.core.config import settings

    return settings


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def auth_headers(admin_token: str):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def workspace_id() -> str:
    return os.environ.get("TEST_ORG_ID", str(uuid.uuid4()))


BASE = "/api/v1/workspaces"


# ─────────────────────────────────────────────────────────────────────
# Anomaly Summary
# ─────────────────────────────────────────────────────────────────────


class TestAnomalySummary:
    """GET /workspaces/{id}/kqi/anomalies/summary"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/summary", headers=auth_headers)
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/summary", headers=auth_headers
        ).json()
        assert "total_anomalies" in data
        assert "critical_anomalies" in data
        assert "high_anomalies" in data
        assert "medium_anomalies" in data
        assert "low_anomalies" in data
        assert "has_data" in data

    def test_period_7d(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/summary",
            headers=auth_headers,
            params={"period": "7d"},
        )
        assert r.status_code == 200

    def test_period_90d(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/summary",
            headers=auth_headers,
            params={"period": "90d"},
        )
        assert r.status_code == 200

    def test_invalid_period(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/summary",
            headers=auth_headers,
            params={"period": "999d"},
        )
        assert r.status_code == 422

    def test_requires_auth(self, client, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/summary")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Detected Anomalies
# ─────────────────────────────────────────────────────────────────────


class TestDetectedAnomalies:
    """GET /workspaces/{id}/kqi/anomalies/detected"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/detected", headers=auth_headers)
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/detected", headers=auth_headers
        ).json()
        assert "anomalies" in data
        assert "has_data" in data
        assert isinstance(data["anomalies"], list)

    def test_anomaly_fields_when_present(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/detected",
            headers=auth_headers,
            params={"period": "90d"},
        ).json()
        if data["anomalies"]:
            a = data["anomalies"][0]
            for field in [
                "dataset",
                "anomaly",
                "severity",
                "current_value",
                "expected_value",
                "status",
            ]:
                assert field in a, f"Missing field: {field}"

    def test_period_filter(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/detected",
            headers=auth_headers,
            params={"period": "7d"},
        )
        assert r.status_code == 200

    def test_requires_auth(self, client, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/detected")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Volume Trend
# ─────────────────────────────────────────────────────────────────────


class TestAnomalyVolumeTrend:
    """GET /workspaces/{id}/kqi/anomalies/volume-trend"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/volume-trend", headers=auth_headers)
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/volume-trend", headers=auth_headers
        ).json()
        assert "trends" in data
        assert "has_data" in data
        assert isinstance(data["trends"], list)

    def test_trend_point_fields(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/volume-trend",
            headers=auth_headers,
            params={"period": "90d"},
        ).json()
        if data["trends"]:
            point = data["trends"][0]
            for field in ["date", "total_executions", "failed_executions", "successful_executions"]:
                assert field in point, f"Missing field: {field}"

    def test_period_filter(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/volume-trend",
            headers=auth_headers,
            params={"period": "7d"},
        )
        assert r.status_code == 200

    def test_requires_auth(self, client, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/volume-trend")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Suggestions
# ─────────────────────────────────────────────────────────────────────


class TestAnomalySuggestions:
    """GET /workspaces/{id}/kqi/anomalies/suggestions"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/suggestions", headers=auth_headers)
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/suggestions", headers=auth_headers
        ).json()
        assert "suggestions" in data
        assert "has_data" in data
        assert isinstance(data["suggestions"], list)

    def test_suggestion_fields_when_present(self, client, auth_headers, workspace_id):
        data = client.get(
            f"{BASE}/{workspace_id}/kqi/anomalies/suggestions",
            headers=auth_headers,
            params={"period": "90d"},
        ).json()
        if data["suggestions"]:
            s = data["suggestions"][0]
            for field in ["signal", "priority", "action", "estimated_impact"]:
                assert field in s, f"Missing field: {field}"

    def test_requires_auth(self, client, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/kqi/anomalies/suggestions")
        assert r.status_code == 401
