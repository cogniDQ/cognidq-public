"""
F057 P02 — Read Entity Endpoint Tests
========================================

Tests for the token-authenticated read-only entity endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.access_token import AccessToken
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(scopes=None):
    tok = MagicMock(spec=AccessToken)
    tok.id = uuid.uuid4()
    tok.user_id = uuid.uuid4()
    tok.scopes = scopes or []
    tok.name = "ci-token"
    tok.prefix = "dqai_test"
    tok.is_valid.return_value = True
    return tok


def _build_client(scopes):
    """Build TestClient with a mocked API token carrying *scopes*."""
    from app.api.v1.endpoints.api_entities import router
    from app.models.database import get_db
    from app.services.auth.api_token_auth import get_api_token

    app = FastAPI()
    app.include_router(router)

    token = _make_token(scopes=scopes)
    app.dependency_overrides[get_api_token] = lambda: token
    app.dependency_overrides[get_db] = lambda: MagicMock()

    return TestClient(app), token


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_datasets_route_exists(self):
        from app.api.v1.endpoints.api_entities import router

        paths = [r.path for r in router.routes]
        assert "/api/workspaces/{workspace_id}/datasets" in paths

    def test_rules_route_exists(self):
        from app.api.v1.endpoints.api_entities import router

        paths = [r.path for r in router.routes]
        assert "/api/workspaces/{workspace_id}/rules" in paths

    def test_executions_route_exists(self):
        from app.api.v1.endpoints.api_entities import router

        paths = [r.path for r in router.routes]
        assert "/api/workspaces/{workspace_id}/rules/{rule_id}/executions" in paths

    def test_issues_route_exists(self):
        from app.api.v1.endpoints.api_entities import router

        paths = [r.path for r in router.routes]
        assert "/api/workspaces/{workspace_id}/issues" in paths

    def test_incidents_route_exists(self):
        from app.api.v1.endpoints.api_entities import router

        paths = [r.path for r in router.routes]
        assert "/api/workspaces/{workspace_id}/incidents" in paths


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------


class TestScopeEnforcement:
    """Token must carry correct scope for each endpoint."""

    def test_datasets_requires_scope(self):
        tc, _ = _build_client(scopes=[])  # no scopes
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets")
        assert resp.status_code == 403
        assert "read:datasets" in resp.json()["detail"]

    def test_issues_requires_scope(self):
        tc, _ = _build_client(scopes=[])
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/issues")
        assert resp.status_code == 403
        assert "read:issues" in resp.json()["detail"]

    def test_incidents_requires_scope(self):
        tc, _ = _build_client(scopes=[])
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/incidents")
        assert resp.status_code == 403
        assert "read:incidents" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Dataset list
# ---------------------------------------------------------------------------


class TestListDatasets:
    @patch("app.api.v1.endpoints.api_entities._dataset_svc")
    def test_returns_200(self, mock_svc):
        tc, _ = _build_client(scopes=["read:datasets"])
        mock_svc.list_datasets.return_value = SimpleNamespace(
            items=[],
            total_count=0,
        )
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    @patch("app.api.v1.endpoints.api_entities._dataset_svc")
    def test_returns_items(self, mock_svc):
        tc, _ = _build_client(scopes=["read:datasets"])
        item = SimpleNamespace(
            id=uuid.uuid4(),
            name="sales",
            status="active",
            dataset_type="table",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        mock_svc.list_datasets.return_value = SimpleNamespace(
            items=[item],
            total_count=1,
        )
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets")
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "sales"


# ---------------------------------------------------------------------------
# Rule list
# ---------------------------------------------------------------------------


class TestListRules:
    @patch("app.api.v1.endpoints.api_entities.RuleService")
    def test_passes_params(self, mock_cls):
        tc, _ = _build_client(scopes=["read:rules"])
        mock_svc = mock_cls.return_value
        mock_svc.list_rules = AsyncMock(return_value=[])
        workspace_id = uuid.uuid4()
        tc.get(
            f"/api/workspaces/{workspace_id}/rules", params={"category": "completeness", "skip": 10}
        )
        args = mock_svc.list_rules.call_args
        assert args.kwargs.get("category") == "completeness"
        assert args.kwargs.get("skip") == 10


# ---------------------------------------------------------------------------
# Issue list
# ---------------------------------------------------------------------------


class TestListIssues:
    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_returns_200(self, mock_repo):
        tc, _ = _build_client(scopes=["read:issues"])
        mock_repo.list_by_workspace.return_value = ([], 0)
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/issues")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_returns_items(self, mock_repo):
        tc, _ = _build_client(scopes=["read:issues"])
        item = SimpleNamespace(
            id=uuid.uuid4(),
            severity="critical",
            status="open",
            title="Missing values",
            opened_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        mock_repo.list_by_workspace.return_value = ([item], 1)
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/issues")
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "Missing values"


# ---------------------------------------------------------------------------
# Incident list
# ---------------------------------------------------------------------------


class TestListIncidents:
    @patch("app.api.v1.endpoints.api_entities._incident_svc")
    def test_returns_200(self, mock_svc):
        tc, _ = _build_client(scopes=["read:incidents"])
        mock_svc.list_incidents.return_value = SimpleNamespace(
            items=[],
            total=0,
            page=1,
            page_size=50,
            has_next=False,
        )
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/incidents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @patch("app.api.v1.endpoints.api_entities._incident_svc")
    def test_returns_items(self, mock_svc):
        tc, _ = _build_client(scopes=["read:incidents"])
        item = SimpleNamespace(
            id=uuid.uuid4(),
            title="Outage",
            severity="critical",
            status="open",
            priority="P1",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        mock_svc.list_incidents.return_value = SimpleNamespace(
            items=[item],
            total=1,
            page=1,
            page_size=50,
            has_next=False,
        )
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/incidents")
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "Outage"


# ---------------------------------------------------------------------------
# Router wiring in main router
# ---------------------------------------------------------------------------


class TestMainRouterWiring:
    def test_api_entities_registered(self):
        from app.api.v1.router import api_router

        paths = [r.path for r in api_router.routes]
        assert any("/api/" in p for p in paths)
