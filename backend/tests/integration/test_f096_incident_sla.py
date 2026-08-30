"""
Integration tests for F096 — Incident SLA Analytics Dashboard.

Tests all 4 incident SLA API endpoints against the running application.
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


# ─────────────────────────────────────────────────────────────────────
# Incident SLA Metrics
# ─────────────────────────────────────────────────────────────────────


class TestIncidentSLAMetrics:
    """GET /workspaces/{id}/kqi/incident-sla/metrics"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics", headers=auth_headers
        )
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics", headers=auth_headers
        ).json()
        assert "compliance_rate" in data
        assert "breaches_count" in data
        assert "avg_breach_duration_hours" in data
        assert "mttr_hours" in data
        assert "total_incidents" in data
        assert "has_data" in data

    def test_period_7d(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics",
            headers=auth_headers,
            params={"period": "7d"},
        )
        assert r.status_code == 200

    def test_period_90d(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics",
            headers=auth_headers,
            params={"period": "90d"},
        )
        assert r.status_code == 200

    def test_invalid_period_rejected(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics",
            headers=auth_headers,
            params={"period": "1y"},
        )
        assert r.status_code == 422

    def test_no_auth_returns_401(self, client, workspace_id):
        r = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/metrics")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Incident SLA Breaches
# ─────────────────────────────────────────────────────────────────────


class TestIncidentSLABreaches:
    """GET /workspaces/{id}/kqi/incident-sla/breaches"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/breaches", headers=auth_headers
        )
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/breaches", headers=auth_headers
        ).json()
        assert "distribution" in data
        assert isinstance(data["distribution"], list)
        assert "has_data" in data

    def test_period_param(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/breaches",
            headers=auth_headers,
            params={"period": "7d"},
        )
        assert r.status_code == 200

    def test_no_auth_returns_401(self, client, workspace_id):
        r = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/breaches")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Incident SLA Compliance Trend
# ─────────────────────────────────────────────────────────────────────


class TestIncidentSLAComplianceTrend:
    """GET /workspaces/{id}/kqi/incident-sla/compliance-trend"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/compliance-trend",
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/compliance-trend",
            headers=auth_headers,
        ).json()
        assert "trend" in data
        assert isinstance(data["trend"], list)
        assert "has_data" in data
        if data["trend"]:
            point = data["trend"][0]
            assert "date" in point
            assert "compliance" in point
            assert "breaches" in point

    def test_weeks_param(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/compliance-trend",
            headers=auth_headers,
            params={"weeks": 4},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["trend"]) == 4

    def test_weeks_validation(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/compliance-trend",
            headers=auth_headers,
            params={"weeks": 1},
        )
        assert r.status_code == 422

    def test_no_auth_returns_401(self, client, workspace_id):
        r = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/compliance-trend")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Incident List with SLA
# ─────────────────────────────────────────────────────────────────────


class TestIncidentsWithSLA:
    """GET /workspaces/{id}/kqi/incident-sla/incidents"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents", headers=auth_headers
        )
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents", headers=auth_headers
        ).json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_data" in data
        assert isinstance(data["items"], list)

    def test_item_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents", headers=auth_headers
        ).json()
        if data["items"]:
            item = data["items"][0]
            assert "id" in item
            assert "title" in item
            assert "severity" in item
            assert "status" in item
            assert "sla_target_hours" in item
            assert "elapsed_hours" in item
            assert "breached" in item

    def test_pagination(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents",
            headers=auth_headers,
            params={"page": 1, "page_size": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) <= 5

    def test_page_size_limit(self, client, auth_headers, workspace_id):
        r = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents",
            headers=auth_headers,
            params={"page_size": 200},
        )
        assert r.status_code == 422

    def test_no_auth_returns_401(self, client, workspace_id):
        r = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/incident-sla/incidents")
        assert r.status_code == 401
