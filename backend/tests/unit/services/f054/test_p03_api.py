"""
F054 P03 — Rule Change History API Endpoint Tests
====================================================

Tests for GET /workspaces/{workspace_id}/rules/{rule_id}/history
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.services.rules.change_history_models import (
    RuleChangeEntry,
    RuleChangePage,
    RuleChangeQueryParams,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tenant_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        platform_role="admin",
    )


def _make_page(rule_id, items=None, total=0, page=1, page_size=25):
    return RuleChangePage(
        items=items or [],
        total=total,
        page=page,
        page_size=page_size,
        has_next=total > page * page_size,
        rule_id=rule_id,
    )


def _make_entry(rule_id=None, action="rule_updated"):
    return RuleChangeEntry(
        log_id=1,
        occurred_at=datetime.now(UTC),
        action_type=action,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        actor_type="user",
        actor_display_name="test@example.com",
        previous_data={"name": "old"},
        new_data={"name": "new"},
        request_id=None,
    )


# ---------------------------------------------------------------------------
# Import endpoint under test (late, so patches can be applied)
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Build a TestClient with auth and DB mocked out."""
    from app.api.v1.endpoints.rules import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)

    user = _make_user(tenant_id=uuid.uuid4())

    # Build a minimal actor context that satisfies the endpoint's use of actor.tenant_id
    actor = SimpleNamespace(
        actor_id=uuid.uuid4(),
        actor_role="workspace_administrator",
        tenant_id=user.tenant_id,
    )

    # Override dependencies
    from app.models.database import get_db
    from app.services.auth.jwt import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: MagicMock()

    # Override all require_workspace_permission guards (each is a _guard closure)
    for route in app.routes:
        if hasattr(route, "dependant") and hasattr(route.dependant, "dependencies"):
            for dep in route.dependant.dependencies:
                if dep.call is not None and getattr(dep.call, "__name__", "") == "_guard":
                    app.dependency_overrides[dep.call] = lambda _actor=actor: _actor

    return TestClient(app), user


# ---------------------------------------------------------------------------
# Tests — endpoint wiring
# ---------------------------------------------------------------------------


class TestEndpointWiring:
    """Verify the route is registered correctly."""

    def test_route_exists(self):
        from app.api.v1.endpoints.rules import router

        paths = [r.path for r in router.routes]
        assert "/workspaces/{workspace_id}/rules/{rule_id}/history" in paths

    def test_route_method_is_get(self):
        from app.api.v1.endpoints.rules import router

        for route in router.routes:
            if getattr(route, "path", "") == "/workspaces/{workspace_id}/rules/{rule_id}/history":
                assert "GET" in route.methods
                break
        else:
            pytest.fail("history route not found")


# ---------------------------------------------------------------------------
# Tests — endpoint behaviour
# ---------------------------------------------------------------------------


class TestGetRuleChangeHistory:
    """Test the endpoint logic via TestClient."""

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_returns_200_with_empty_page(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        resp = tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["rule_id"] == str(rule_id)

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_returns_items(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        entry = _make_entry(rule_id=rule_id)
        mock_svc.get_page.return_value = _make_page(rule_id, items=[entry], total=1)

        resp = tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["action_type"] == "rule_updated"

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_passes_action_type_filter(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        tc.get(
            f"/workspaces/{workspace_id}/rules/{rule_id}/history",
            params={"action_type": "rule_created"},
        )

        call_args = mock_svc.get_page.call_args
        filters: RuleChangeQueryParams = call_args.kwargs.get("filters") or call_args[1].get(
            "filters"
        )
        assert filters.action_type == "rule_created"

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_passes_page_params(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id, page=2, page_size=10)

        tc.get(
            f"/workspaces/{workspace_id}/rules/{rule_id}/history",
            params={"page": 2, "page_size": 10},
        )

        call_args = mock_svc.get_page.call_args
        filters: RuleChangeQueryParams = call_args.kwargs.get("filters") or call_args[1].get(
            "filters"
        )
        assert filters.page == 2
        assert filters.page_size == 10

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_tenant_id_from_user(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        call_args = mock_svc.get_page.call_args
        passed_tenant = call_args.kwargs.get("tenant_id") or call_args[1].get("tenant_id")
        assert passed_tenant == user.tenant_id

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_tenant_id_fallback_to_org(self, mock_svc):
        """When user.tenant_id is None, workspace_id is used."""
        from app.api.v1.endpoints.rules import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(router)

        user = _make_user(tenant_id=None)
        # actor with no tenant_id — endpoint should fall back to workspace_id
        actor = SimpleNamespace(
            actor_id=uuid.uuid4(),
            actor_role="workspace_administrator",
            tenant_id=None,
        )
        from app.models.database import get_db
        from app.services.auth.jwt import get_current_user

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: MagicMock()
        for route in app.routes:
            if hasattr(route, "dependant") and hasattr(route.dependant, "dependencies"):
                for dep in route.dependant.dependencies:
                    if dep.call is not None and getattr(dep.call, "__name__", "") == "_guard":
                        app.dependency_overrides[dep.call] = lambda _a=actor: _a

        tc = TestClient(app)
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        call_args = mock_svc.get_page.call_args
        passed_tenant = call_args.kwargs.get("tenant_id") or call_args[1].get("tenant_id")
        assert passed_tenant == workspace_id

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_workspace_id_is_org_id(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        call_args = mock_svc.get_page.call_args
        passed_ws = call_args.kwargs.get("workspace_id") or call_args[1].get("workspace_id")
        assert passed_ws == workspace_id

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_has_next_true(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(
            rule_id,
            total=30,
            page=1,
            page_size=25,
        )

        resp = tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")
        assert resp.json()["has_next"] is True

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_has_next_false(self, mock_svc, client):
        tc, user = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(
            rule_id,
            total=10,
            page=1,
            page_size=25,
        )

        resp = tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")
        assert resp.json()["has_next"] is False

    def test_page_param_validation_min(self, client):
        tc, _ = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        resp = tc.get(
            f"/workspaces/{workspace_id}/rules/{rule_id}/history",
            params={"page": 0},
        )
        assert resp.status_code == 422

    def test_page_size_validation_max(self, client):
        tc, _ = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        resp = tc.get(
            f"/workspaces/{workspace_id}/rules/{rule_id}/history",
            params={"page_size": 101},
        )
        assert resp.status_code == 422

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_response_contains_previous_and_new_data(self, mock_svc, client):
        tc, _ = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        entry = _make_entry(rule_id=rule_id)
        mock_svc.get_page.return_value = _make_page(rule_id, items=[entry], total=1)

        resp = tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")
        item = resp.json()["items"][0]
        assert item["previous_data"] == {"name": "old"}
        assert item["new_data"] == {"name": "new"}

    @patch("app.api.v1.endpoints.rules._history_svc")
    def test_default_page_params(self, mock_svc, client):
        tc, _ = client
        workspace_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        mock_svc.get_page.return_value = _make_page(rule_id)

        tc.get(f"/workspaces/{workspace_id}/rules/{rule_id}/history")

        call_args = mock_svc.get_page.call_args
        filters = call_args.kwargs.get("filters") or call_args[1].get("filters")
        assert filters.page == 1
        assert filters.page_size == 25
        assert filters.action_type is None
