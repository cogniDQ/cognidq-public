"""
F057 P03 — Pagination & Filtering Tests
==========================================

Tests that query parameters (page, page_size, filters) are passed through
correctly and that response pagination metadata is accurate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.access_token import AccessToken
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(scopes):
    tok = MagicMock(spec=AccessToken)
    tok.id = uuid.uuid4()
    tok.user_id = uuid.uuid4()
    tok.scopes = scopes
    tok.name = "ci-token"
    tok.prefix = "dqai_test"
    tok.is_valid.return_value = True
    return tok


def _build_client(scopes):
    from app.api.v1.endpoints.api_entities import router
    from app.models.database import get_db
    from app.services.auth.api_token_auth import get_api_token

    app = FastAPI()
    app.include_router(router)

    token = _make_token(scopes)
    app.dependency_overrides[get_api_token] = lambda: token
    app.dependency_overrides[get_db] = lambda: MagicMock()

    return TestClient(app)


# ---------------------------------------------------------------------------
# Datasets — pagination & filter params
# ---------------------------------------------------------------------------


class TestDatasetPagination:
    @patch("app.api.v1.endpoints.api_entities._dataset_svc")
    def test_page_and_page_size_passed(self, mock_svc):
        tc = _build_client(["read:datasets"])
        mock_svc.list_datasets.return_value = SimpleNamespace(items=[], total_count=0)
        tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets", params={"page": 3, "page_size": 10})
        call_args = mock_svc.list_datasets.call_args
        filters = call_args.kwargs.get("filters") or call_args[1].get("filters")
        assert filters.offset == 20  # (3-1) * 10
        assert filters.limit == 10

    @patch("app.api.v1.endpoints.api_entities._dataset_svc")
    def test_search_param_passed(self, mock_svc):
        tc = _build_client(["read:datasets"])
        mock_svc.list_datasets.return_value = SimpleNamespace(items=[], total_count=0)
        tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets", params={"search": "sales"})
        call_args = mock_svc.list_datasets.call_args
        filters = call_args.kwargs.get("filters") or call_args[1].get("filters")
        assert filters.search == "sales"

    @patch("app.api.v1.endpoints.api_entities._dataset_svc")
    def test_status_filter_passed(self, mock_svc):
        tc = _build_client(["read:datasets"])
        mock_svc.list_datasets.return_value = SimpleNamespace(items=[], total_count=0)
        tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets", params={"status": "active"})
        call_args = mock_svc.list_datasets.call_args
        filters = call_args.kwargs.get("filters") or call_args[1].get("filters")
        assert filters.status == "active"

    def test_page_min_validation(self):
        tc = _build_client(["read:datasets"])
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets", params={"page": 0})
        assert resp.status_code == 422

    def test_page_size_max_validation(self):
        tc = _build_client(["read:datasets"])
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/datasets", params={"page_size": 101})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Issues — pagination & filter params
# ---------------------------------------------------------------------------


class TestIssuePagination:
    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_page_params_forwarded(self, mock_repo):
        tc = _build_client(["read:issues"])
        mock_repo.list_by_workspace.return_value = ([], 0)
        tc.get(f"/api/workspaces/{uuid.uuid4()}/issues", params={"page": 2, "page_size": 10})
        call_args = mock_repo.list_by_workspace.call_args
        assert call_args.kwargs.get("page") == 2
        assert call_args.kwargs.get("page_size") == 10

    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_severity_filter(self, mock_repo):
        tc = _build_client(["read:issues"])
        mock_repo.list_by_workspace.return_value = ([], 0)
        tc.get(f"/api/workspaces/{uuid.uuid4()}/issues", params={"severity": "critical"})
        call_args = mock_repo.list_by_workspace.call_args
        assert call_args.kwargs.get("severity") == "critical"

    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_has_next_true(self, mock_repo):
        tc = _build_client(["read:issues"])
        mock_repo.list_by_workspace.return_value = ([], 60)
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/issues", params={"page": 1, "page_size": 50})
        assert resp.json()["has_next"] is True

    @patch("app.api.v1.endpoints.api_entities._issue_repo")
    def test_has_next_false(self, mock_repo):
        tc = _build_client(["read:issues"])
        mock_repo.list_by_workspace.return_value = ([], 10)
        resp = tc.get(f"/api/workspaces/{uuid.uuid4()}/issues", params={"page": 1, "page_size": 50})
        assert resp.json()["has_next"] is False


# ---------------------------------------------------------------------------
# Incidents — pagination & filter params
# ---------------------------------------------------------------------------


class TestIncidentPagination:
    @patch("app.api.v1.endpoints.api_entities._incident_svc")
    def test_page_params_forwarded(self, mock_svc):
        tc = _build_client(["read:incidents"])
        mock_svc.list_incidents.return_value = SimpleNamespace(
            items=[],
            total=0,
            page=2,
            page_size=10,
            has_next=False,
        )
        tc.get(f"/api/workspaces/{uuid.uuid4()}/incidents", params={"page": 2, "page_size": 10})
        call_args = mock_svc.list_incidents.call_args
        assert call_args.kwargs.get("page") == 2
        assert call_args.kwargs.get("page_size") == 10

    @patch("app.api.v1.endpoints.api_entities._incident_svc")
    def test_severity_filter(self, mock_svc):
        tc = _build_client(["read:incidents"])
        mock_svc.list_incidents.return_value = SimpleNamespace(
            items=[],
            total=0,
            page=1,
            page_size=50,
            has_next=False,
        )
        tc.get(f"/api/workspaces/{uuid.uuid4()}/incidents", params={"severity": "critical"})
        call_args = mock_svc.list_incidents.call_args
        assert call_args.kwargs.get("severity") == "critical"
