"""
F008 P01 — Unit tests: PermissionAuditRepository
=================================================

No real database connection required — all tests inspect the SQL text
produced by the repository using a mock Session.

ACs covered
-----------
AC-P01-003  tenant_id always in WHERE clause
AC-P01-004  workspace_id always in WHERE clause
AC-P01-004  action_type always restricted to access-control set
AC-P01-005  actor_id filter applied when provided; absent when not
AC-P01-006  sort_dir asc/desc controls ORDER BY direction
           export uses LIMIT 10001
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, call

import pytest
from app.schemas.permission_audit import (
    ACCESS_CONTROL_ACTION_TYPES,
    PermissionAuditExportQueryParams,
    PermissionAuditQueryParams,
)
from app.services.permission_audit.repository import PermissionAuditRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()
_TARGET = uuid.uuid4()


def _make_session() -> MagicMock:
    """Return a mock SQLAlchemy Session."""
    session = MagicMock()
    # list_entries / export: session.execute returns a result with _mapping rows
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([]))
    session.execute.return_value = mock_result
    return session


def _default_filters(**overrides) -> PermissionAuditQueryParams:
    defaults: dict[str, Any] = {
        "page": 1,
        "page_size": 25,
        "sort_dir": "desc",
    }
    defaults.update(overrides)
    return PermissionAuditQueryParams(**defaults)


def _get_sql_text(session: MagicMock) -> str:
    """Return the SQL text from the first session.execute call."""
    args, _ = session.execute.call_args
    return str(args[0].text) if hasattr(args[0], "text") else str(args[0])


def _get_params(session: MagicMock) -> dict:
    """Return the params dict from the first session.execute call."""
    args, _ = session.execute.call_args
    return args[1] if len(args) > 1 else {}


# ---------------------------------------------------------------------------
# Test: tenant and workspace isolation always enforced
# ---------------------------------------------------------------------------


class TestTenantWorkspaceIsolation:
    def test_tenant_id_always_in_where(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        sql = _get_sql_text(session)
        assert "tenant_id" in sql.lower()

    def test_workspace_id_always_in_where(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        sql = _get_sql_text(session)
        assert "workspace_id" in sql.lower()

    def test_tenant_id_bound_correctly(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        params = _get_params(session)
        assert params["tenant_id"] == str(_TENANT)

    def test_workspace_id_bound_correctly(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        params = _get_params(session)
        assert params["workspace_id"] == str(_WORKSPACE)

    def test_count_also_enforces_tenant(self):
        session = _make_session()
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        session.execute.return_value = mock_count_result
        repo = PermissionAuditRepository()
        repo.count_entries(session, _TENANT, _WORKSPACE, _default_filters())
        params = _get_params(session)
        assert params["tenant_id"] == str(_TENANT)


# ---------------------------------------------------------------------------
# Test: action_type always restricted to access-control set
# ---------------------------------------------------------------------------


class TestActionTypeRestriction:
    def test_action_type_set_always_present(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        params = _get_params(session)
        assert "action_type_set" in params
        # All 10 access-control types must be in the set when no filter given
        for at in ACCESS_CONTROL_ACTION_TYPES:
            assert at in params["action_type_set"]

    def test_single_action_type_filter_restricts_to_one(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(action_type="role_assigned")
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params["action_type_set"] == ["role_assigned"]

    def test_sql_contains_any_operator(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        sql = _get_sql_text(session)
        # PostgreSQL ANY(:array) pattern
        assert "any" in sql.lower()


# ---------------------------------------------------------------------------
# Test: optional filters
# ---------------------------------------------------------------------------


class TestOptionalFilters:
    def test_actor_id_filter_included_when_provided(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(actor_id=_ACTOR)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert "actor_id" in params
        assert params["actor_id"] == str(_ACTOR)

    def test_actor_id_filter_absent_when_not_provided(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        repo.list_entries(session, _TENANT, _WORKSPACE, _default_filters())
        params = _get_params(session)
        assert "actor_id" not in params

    def test_target_entity_id_filter_applied(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(target_entity_id=_TARGET)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert "target_entity_id" in params
        assert params["target_entity_id"] == str(_TARGET)

    def test_target_entity_type_filter_applied(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(target_entity_type="team")
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params.get("target_entity_type") == "team"

    def test_from_date_filter_applied(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        dt = datetime(2026, 1, 1, tzinfo=UTC)
        filters = _default_filters(from_date=dt)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params.get("from_date") == dt

    def test_to_date_filter_applied(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        dt = datetime(2026, 1, 31, tzinfo=UTC)
        filters = _default_filters(to_date=dt)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params.get("to_date") == dt


# ---------------------------------------------------------------------------
# Test: sort direction
# ---------------------------------------------------------------------------


class TestSortDirection:
    def test_sort_asc_in_sql(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(sort_dir="asc")
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        sql = _get_sql_text(session)
        assert "ASC" in sql

    def test_sort_desc_in_sql(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(sort_dir="desc")
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        sql = _get_sql_text(session)
        assert "DESC" in sql


# ---------------------------------------------------------------------------
# Test: export uses LIMIT 10001
# ---------------------------------------------------------------------------


class TestExportLimit:
    def test_export_limit_10001(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = PermissionAuditExportQueryParams()
        repo.export_entries(session, _TENANT, _WORKSPACE, filters)
        sql = _get_sql_text(session)
        assert "10001" in sql


# ---------------------------------------------------------------------------
# Test: pagination offset
# ---------------------------------------------------------------------------


class TestPaginationOffset:
    def test_page_1_offset_zero(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(page=1, page_size=25)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params["offset"] == 0

    def test_page_2_offset_equals_page_size(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(page=2, page_size=25)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params["offset"] == 25

    def test_page_3_offset_correct(self):
        session = _make_session()
        repo = PermissionAuditRepository()
        filters = _default_filters(page=3, page_size=10)
        repo.list_entries(session, _TENANT, _WORKSPACE, filters)
        params = _get_params(session)
        assert params["offset"] == 20
