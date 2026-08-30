"""
Integration tests for F095 — KQI Dynamic Reports Engine.

Tests all 12 KQI API endpoints against the running application.
Uses real JWTs and the actual database (with SAVEPOINT rollback).
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
    """Use a well-known workspace/org ID present in the test database.
    Falls back to a random UUID (endpoints should return 200 with empty data)."""
    return os.environ.get("TEST_ORG_ID", str(uuid.uuid4()))


# ─────────────────────────────────────────────────────────────────────
# Coverage Report Endpoints
# ─────────────────────────────────────────────────────────────────────


class TestCoverageInventory:
    """GET /workspaces/{id}/kqi/coverage/inventory"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/inventory", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/inventory", headers=auth_headers
        ).json()
        required = {
            "total_datasets",
            "datasets_analyzed",
            "datasets_analyzed_24h",
            "datasets_without_flows",
            "total_flows",
            "active_flows",
            "paused_flows",
            "failed_flows",
            "avg_datasets_per_flow",
            "avg_checks_per_flow",
            "has_data",
        }
        assert required.issubset(set(data.keys()))

    def test_no_cache(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/inventory",
            headers=auth_headers,
            params={"use_cache": False},
        )
        assert resp.status_code == 200


class TestCheckInventory:
    """GET /workspaces/{id}/kqi/coverage/checks"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/checks", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/checks", headers=auth_headers
        ).json()
        assert "total_checks" in data
        assert "by_dimension" in data
        assert "standard_checks" in data
        assert "custom_checks" in data
        assert "has_data" in data


class TestGovernanceMaturity:
    """GET /workspaces/{id}/kqi/coverage/maturity"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/maturity", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/maturity", headers=auth_headers
        ).json()
        for field in (
            "datasets_with_owner_pct",
            "datasets_with_criticality_pct",
            "datasets_with_domain_pct",
            "has_data",
        ):
            assert field in data


class TestCoverageTrend:
    """GET /workspaces/{id}/kqi/coverage/trend"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/trend", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_period_validation(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/coverage/trend",
            headers=auth_headers,
            params={"period": "invalid"},
        )
        assert resp.status_code == 422

    def test_valid_periods(self, client, auth_headers, workspace_id):
        for p in ("7d", "30d", "90d"):
            resp = client.get(
                f"/api/v1/workspaces/{workspace_id}/kqi/coverage/trend",
                headers=auth_headers,
                params={"period": p},
            )
            assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# Operational Intelligence Endpoints
# ─────────────────────────────────────────────────────────────────────


class TestOperationalSummary:
    """GET /workspaces/{id}/kqi/operational/summary"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/operational/summary", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/operational/summary", headers=auth_headers
        ).json()
        for field in (
            "runs_per_day",
            "success_rate",
            "failure_rate",
            "mttr_hours",
            "quality_stability_index",
            "has_data",
        ):
            assert field in data


class TestOperationalTimeline:
    """GET /workspaces/{id}/kqi/operational/timeline"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/operational/timeline", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/operational/timeline", headers=auth_headers
        ).json()
        assert "data_points" in data
        assert "has_data" in data


# ─────────────────────────────────────────────────────────────────────
# Dataset Quality Endpoint
# ─────────────────────────────────────────────────────────────────────


class TestDatasetProfile:
    """GET /workspaces/{id}/kqi/datasets/{dataset_id}/profile"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/datasets/test_dataset/profile",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/datasets/test_dataset/profile",
            headers=auth_headers,
        ).json()
        for field in (
            "overall_score",
            "dimension_scores",
            "worst_check_name",
            "column_coverage",
            "has_data",
        ):
            assert field in data


# ─────────────────────────────────────────────────────────────────────
# Check Intelligence Endpoints
# ─────────────────────────────────────────────────────────────────────


class TestCheckIntelligence:
    """GET /workspaces/{id}/kqi/checks/intelligence"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/checks/intelligence", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/checks/intelligence", headers=auth_headers
        ).json()
        for field in (
            "noisy_checks_count",
            "always_passing_count",
            "always_failing_count",
            "duplicate_checks_count",
            "effectiveness_score",
            "health_distribution",
            "has_data",
        ):
            assert field in data


class TestProblematicChecks:
    """GET /workspaces/{id}/kqi/checks/problematic"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/checks/problematic", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_pagination(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/checks/problematic",
            headers=auth_headers,
            params={"page": 1, "page_size": 5},
        )
        data = resp.json()
        assert "checks" in data
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_page_size_validation(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/checks/problematic",
            headers=auth_headers,
            params={"page_size": 200},
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# Business Value Endpoints
# ─────────────────────────────────────────────────────────────────────


class TestBusinessValueSummary:
    """GET /workspaces/{id}/kqi/value/summary"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/value/summary", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/value/summary", headers=auth_headers
        ).json()
        for field in (
            "issues_caught",
            "issues_caught_trend",
            "estimated_incidents_avoided",
            "estimated_cost_saved_usd",
            "has_data",
        ):
            assert field in data


class TestTopFlows:
    """GET /workspaces/{id}/kqi/value/top-flows"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/value/top-flows", headers=auth_headers
        )
        assert resp.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/value/top-flows", headers=auth_headers
        ).json()
        assert "flows" in data

    def test_limit_param(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/kqi/value/top-flows",
            headers=auth_headers,
            params={"limit": 3},
        )
        data = resp.json()
        assert len(data["flows"]) <= 3


# ─────────────────────────────────────────────────────────────────────
# Auth Tests
# ─────────────────────────────────────────────────────────────────────


class TestAuth:
    """All KQI endpoints require authentication."""

    def test_coverage_inventory_401(self, client, workspace_id):
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/coverage/inventory")
        assert resp.status_code in (401, 403)

    def test_operational_summary_401(self, client, workspace_id):
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/operational/summary")
        assert resp.status_code in (401, 403)

    def test_check_intelligence_401(self, client, workspace_id):
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/checks/intelligence")
        assert resp.status_code in (401, 403)

    def test_value_summary_401(self, client, workspace_id):
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/kqi/value/summary")
        assert resp.status_code in (401, 403)
