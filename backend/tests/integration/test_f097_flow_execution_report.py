"""
Integration tests for F097 — Flow Execution Detail Report.

Tests the flow execution API endpoints used by the FlowExecutionReport dashboard:
  - GET /workspaces/{workspace_id}/flow-executions            (list all)
  - GET /workspaces/{workspace_id}/flow-executions/{id}       (single detail)
  - GET /workspaces/{workspace_id}/flow-executions/{id}/nodes (node results)
  - GET /workspaces/{workspace_id}/flow-executions/{id}/report (report view)

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
# List All Executions
# ─────────────────────────────────────────────────────────────────────


class TestListAllExecutions:
    """GET /workspaces/{workspace_id}/flow-executions"""

    def test_returns_200(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers)
        assert r.status_code == 200

    def test_response_structure(self, client, auth_headers, workspace_id):
        data = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers).json()
        assert "executions" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["executions"], list)

    def test_pagination_params(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions",
            headers=auth_headers,
            params={"page": 1, "page_size": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] <= 5

    def test_status_filter(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions",
            headers=auth_headers,
            params={"status": "completed"},
        )
        assert r.status_code == 200

    def test_page_size_max_100(self, client, auth_headers, workspace_id):
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions",
            headers=auth_headers,
            params={"page_size": 101},
        )
        assert r.status_code == 422

    def test_requires_auth(self, client, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/flow-executions")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# Get Single Execution
# ─────────────────────────────────────────────────────────────────────


class TestGetExecution:
    """GET /workspaces/{workspace_id}/flow-executions/{execution_id}"""

    def test_not_found(self, client, auth_headers, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/{fake_id}", headers=auth_headers)
        assert r.status_code == 404

    def test_invalid_uuid(self, client, auth_headers, workspace_id):
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/not-a-uuid", headers=auth_headers)
        assert r.status_code == 422

    def test_requires_auth(self, client, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/{fake_id}")
        assert r.status_code == 401

    def test_response_fields_when_found(self, client, auth_headers, workspace_id):
        """If executions exist, verify the response schema of the first one."""
        listing = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers).json()
        execs = listing.get("executions", [])
        if not execs:
            pytest.skip("No executions in database to verify detail schema")
        exec_id = execs[0]["id"]
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/{exec_id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        for field in [
            "id",
            "flow_id",
            "status",
            "nodes_executed",
            "nodes_passed",
            "nodes_failed",
            "nodes_skipped",
        ]:
            assert field in data, f"Missing field: {field}"


# ─────────────────────────────────────────────────────────────────────
# Get Node Results
# ─────────────────────────────────────────────────────────────────────


class TestGetNodeResults:
    """GET /workspaces/{workspace_id}/flow-executions/{execution_id}/nodes"""

    def test_not_found(self, client, auth_headers, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions/{fake_id}/nodes", headers=auth_headers
        )
        assert r.status_code in (404, 200)  # may return empty list or 404

    def test_requires_auth(self, client, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/{fake_id}/nodes")
        assert r.status_code == 401

    def test_response_is_list_when_found(self, client, auth_headers, workspace_id):
        """If executions exist, verify node results response is a list."""
        listing = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers).json()
        execs = listing.get("executions", [])
        if not execs:
            pytest.skip("No executions in database to verify node results")
        exec_id = execs[0]["id"]
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions/{exec_id}/nodes", headers=auth_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_node_result_fields(self, client, auth_headers, workspace_id):
        """Verify node result response schema if data is available."""
        listing = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers).json()
        execs = listing.get("executions", [])
        if not execs:
            pytest.skip("No executions available")
        exec_id = execs[0]["id"]
        nodes = client.get(
            f"{BASE}/{workspace_id}/flow-executions/{exec_id}/nodes", headers=auth_headers
        ).json()
        if not nodes:
            pytest.skip("No node results for this execution")
        node = nodes[0]
        for field in ["id", "execution_id", "node_id", "status", "execution_order"]:
            assert field in node, f"Missing field: {field}"


# ─────────────────────────────────────────────────────────────────────
# Get Execution Report
# ─────────────────────────────────────────────────────────────────────


class TestGetExecutionReport:
    """GET /workspaces/{workspace_id}/flow-executions/{execution_id}/report"""

    def test_not_found(self, client, auth_headers, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions/{fake_id}/report", headers=auth_headers
        )
        assert r.status_code == 404

    def test_requires_auth(self, client, workspace_id):
        fake_id = str(uuid.uuid4())
        r = client.get(f"{BASE}/{workspace_id}/flow-executions/{fake_id}/report")
        assert r.status_code == 401

    def test_response_when_found(self, client, auth_headers, workspace_id):
        """If executions exist, verify the report endpoint returns 200."""
        listing = client.get(f"{BASE}/{workspace_id}/flow-executions", headers=auth_headers).json()
        execs = listing.get("executions", [])
        if not execs:
            pytest.skip("No executions in database to verify report")
        exec_id = execs[0]["id"]
        r = client.get(
            f"{BASE}/{workspace_id}/flow-executions/{exec_id}/report", headers=auth_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
