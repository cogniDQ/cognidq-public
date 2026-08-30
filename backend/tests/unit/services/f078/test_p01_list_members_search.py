"""
F078 P01 — Unit tests for WorkspaceRBACService.list_members and
WorkspaceRBACService.search_non_members
=======================================================================

All tests are database-free and use MagicMock to simulate SQLAlchemy.

Tests:
  1. list_members — returns an empty list when no assignments exist
  2. list_members — returns correctly shaped dicts for multiple members
  3. list_members — passes workspace_id to SQL correctly
  4. search_non_members — returns users matching q prefix
  5. search_non_members — passes all parameters (tenant_id, workspace_id, limit)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import pytest
from app.services.workspaces.rbac import WorkspaceRBACService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.execute.return_value = MagicMock()
    db.flush.return_value = None
    return db


def _make_member_row(
    user_id: uuid.UUID,
    email: str,
    display_name: str,
    role_name: str,
    granted_by: uuid.UUID | None = None,
    granted_at: datetime | None = None,
):
    """Simulate a SQLAlchemy row tuple for a workspace_role_assignments + users join."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: [
        user_id,
        email,
        display_name,
        role_name,
        granted_by,
        granted_at or datetime.now(UTC),
    ][idx]
    return row


def _make_user_row(user_id: uuid.UUID, email: str, display_name: str):
    """Simulate a SQLAlchemy row tuple for a users search result."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: [user_id, email, display_name][idx]
    return row


# ---------------------------------------------------------------------------
# Test 1 — list_members returns empty list when no rows
# ---------------------------------------------------------------------------


class TestListMembersEmpty:
    def test_returns_empty_list_when_no_members(self):
        svc = WorkspaceRBACService()
        db = _mock_db()
        db.execute.return_value.fetchall.return_value = []

        workspace_id = _uuid()
        result = svc.list_members(workspace_id, db)

        assert result == []
        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — list_members returns correctly shaped dicts
# ---------------------------------------------------------------------------


class TestListMembersShape:
    def test_returns_correctly_shaped_dicts(self):
        svc = WorkspaceRBACService()
        db = _mock_db()

        workspace_id = _uuid()
        user1_id = _uuid()
        user2_id = _uuid()
        granted_by_id = _uuid()
        now = datetime.now(UTC)

        rows = [
            _make_member_row(
                user1_id,
                "alice@example.com",
                "Alice",
                "workspace_administrator",
                granted_by_id,
                now,
            ),
            _make_member_row(user2_id, "bob@example.com", "Bob", "data_engineer", None, now),
        ]
        db.execute.return_value.fetchall.return_value = rows

        result = svc.list_members(workspace_id, db)

        assert len(result) == 2

        first = result[0]
        assert first["user_id"] == user1_id
        assert first["email"] == "alice@example.com"
        assert first["display_name"] == "Alice"
        assert first["role_name"] == "workspace_administrator"
        assert first["granted_by"] == granted_by_id
        assert first["granted_at"] == now

        second = result[1]
        assert second["user_id"] == user2_id
        assert second["email"] == "bob@example.com"
        assert second["role_name"] == "data_engineer"
        assert second["granted_by"] is None


# ---------------------------------------------------------------------------
# Test 3 — list_members passes workspace_id to SQL params
# ---------------------------------------------------------------------------


class TestListMembersPassesParams:
    def test_workspace_id_passed_to_sql(self):
        svc = WorkspaceRBACService()
        db = _mock_db()
        db.execute.return_value.fetchall.return_value = []

        workspace_id = _uuid()
        svc.list_members(workspace_id, db)

        call_kwargs = db.execute.call_args
        bound_params = call_kwargs[0][1]  # second positional arg = params dict
        assert bound_params["workspace_id"] == str(workspace_id)


# ---------------------------------------------------------------------------
# Test 4 — search_non_members returns correctly shaped user dicts
# ---------------------------------------------------------------------------


class TestSearchNonMembersShape:
    def test_returns_user_dicts(self):
        svc = WorkspaceRBACService()
        db = _mock_db()

        workspace_id = _uuid()
        tenant_id = _uuid()
        user_id = _uuid()

        rows = [_make_user_row(user_id, "carol@example.com", "Carol")]
        db.execute.return_value.fetchall.return_value = rows

        result = svc.search_non_members(workspace_id, tenant_id, "car", db)

        assert len(result) == 1
        assert result[0]["user_id"] == user_id
        assert result[0]["email"] == "carol@example.com"
        assert result[0]["display_name"] == "Carol"


# ---------------------------------------------------------------------------
# Test 5 — search_non_members passes all SQL parameters correctly
# ---------------------------------------------------------------------------


class TestSearchNonMembersParams:
    def test_all_params_passed_to_sql(self):
        svc = WorkspaceRBACService()
        db = _mock_db()
        db.execute.return_value.fetchall.return_value = []

        workspace_id = _uuid()
        tenant_id = _uuid()
        query_str = "dan"
        custom_limit = 10

        svc.search_non_members(workspace_id, tenant_id, query_str, db, limit=custom_limit)

        call_kwargs = db.execute.call_args
        bound_params = call_kwargs[0][1]

        assert bound_params["workspace_id"] == str(workspace_id)
        assert bound_params["tenant_id"] == str(tenant_id)
        assert bound_params["q_prefix"] == f"{query_str}%"
        assert bound_params["limit"] == custom_limit
