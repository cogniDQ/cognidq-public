"""
F053 P01 — Repository + Pydantic Models Tests (15 tests)
=========================================================

Covers: AuditLogQueryParams validation, AuditLogEntry/Page shape,
        AuditLogSearchRepository list/count/export.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.services.audit.search_models import (
    AuditLogEntry,
    AuditLogPage,
    AuditLogQueryParams,
)
from app.services.audit.search_repository import AuditLogSearchRepository

_TENANT = uuid4()
_WS = uuid4()


def _mock_session():
    return MagicMock()


# ── Pydantic Model Tests ────────────────────────────────────────────────────


class TestAuditLogQueryParams:
    def test_defaults(self):
        params = AuditLogQueryParams()
        assert params.action_type is None
        assert params.entity_type is None
        assert params.actor_id is None
        assert params.from_date is None
        assert params.to_date is None
        assert params.sort_dir == "desc"
        assert params.page == 1
        assert params.page_size == 50

    def test_validates_action_type(self):
        with pytest.raises(Exception):
            AuditLogQueryParams(action_type="invalid_action_xyz")

    def test_validates_entity_type(self):
        with pytest.raises(Exception):
            AuditLogQueryParams(entity_type="invalid_entity_xyz")

    def test_date_range_validation(self):
        now = datetime.now(UTC)
        with pytest.raises(Exception):
            AuditLogQueryParams(
                from_date=now,
                to_date=now - timedelta(days=1),
            )

    def test_valid_action_type_accepted(self):
        params = AuditLogQueryParams(action_type="tenant_created")
        assert params.action_type == "tenant_created"


class TestAuditLogEntry:
    def test_fields(self):
        now = datetime.now(UTC)
        lid = uuid4()
        entry = AuditLogEntry(
            log_id=lid,
            occurred_at=now,
            action_type="tenant_created",
            actor_id=uuid4(),
            actor_role="admin",
            actor_type="user",
            actor_display_name="Admin User",
            target_entity_type="tenant",
            target_entity_id=uuid4(),
            workspace_id=_WS,
            request_id=None,
        )
        assert entry.log_id == lid
        assert entry.action_type == "tenant_created"


class TestAuditLogPage:
    def test_page_shape(self):
        page = AuditLogPage(
            items=[],
            total=0,
            page=1,
            page_size=50,
            has_next=False,
        )
        assert page.total == 0
        assert page.has_next is False


# ── Repository Tests ─────────────────────────────────────────────────────────


class TestAuditLogSearchRepository:
    def test_list_entries_returns_list(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams()
        result = repo.list_entries(session, _TENANT, _WS, filters)
        assert isinstance(result, list)

    def test_list_entries_tenant_scope(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams()
        repo.list_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["tenant_id"] == str(_TENANT)
        assert params["workspace_id"] == str(_WS)

    def test_list_entries_action_filter(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams(action_type="tenant_created")
        repo.list_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["action_type"] == "tenant_created"

    def test_list_entries_entity_filter(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams(entity_type="tenant")
        repo.list_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["entity_type"] == "tenant"

    def test_list_entries_actor_filter(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        actor = uuid4()
        filters = AuditLogQueryParams(actor_id=actor)
        repo.list_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["actor_id"] == str(actor)

    def test_list_entries_date_range_filter(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        now = datetime.now(UTC)
        filters = AuditLogQueryParams(from_date=now - timedelta(days=7), to_date=now)
        repo.list_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert "from_date" in params
        assert "to_date" in params

    def test_count_entries(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        session.execute.return_value.scalar.return_value = 42
        filters = AuditLogQueryParams()
        result = repo.count_entries(session, _TENANT, _WS, filters)
        assert result == 42

    def test_export_entries_max_rows(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams()
        repo.export_entries(session, _TENANT, _WS, filters)
        call_args = session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "10001" in sql_str

    def test_export_entries_truncation_detection(self):
        repo = AuditLogSearchRepository()
        session = _mock_session()
        # Simulate 10001 rows returned — each row needs _mapping for dict()
        mock_rows = []
        for i in range(10001):
            row = MagicMock()
            row._mapping = {"log_id": i}
            mock_rows.append(row)
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(mock_rows)
        session.execute.return_value = mock_result
        filters = AuditLogQueryParams()
        result = repo.export_entries(session, _TENANT, _WS, filters)
        assert len(result) == 10001  # service layer truncates
