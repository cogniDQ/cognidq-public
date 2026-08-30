"""
F054 P01 — Repository + Models Tests (15 tests)
=================================================

Covers: RuleChangeQueryParams, RuleChangeEntry, RuleChangePage,
        RuleChangeHistoryRepository list_changes/count_changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.services.rules.change_history_models import (
    RuleChangeEntry,
    RuleChangePage,
    RuleChangeQueryParams,
)
from app.services.rules.change_history_repository import RuleChangeHistoryRepository

_TENANT = uuid4()
_WS = uuid4()
_RULE = uuid4()


def _mock_session():
    return MagicMock()


# ── Model tests ─────────────────────────────────────────────────────────────


class TestRuleChangeQueryParams:
    def test_defaults(self):
        p = RuleChangeQueryParams()
        assert p.action_type is None
        assert p.page == 1
        assert p.page_size == 25

    def test_custom_values(self):
        p = RuleChangeQueryParams(action_type="rule_updated", page=2, page_size=10)
        assert p.action_type == "rule_updated"
        assert p.page == 2


class TestRuleChangeEntry:
    def test_all_fields(self):
        now = datetime.now(UTC)
        e = RuleChangeEntry(
            log_id=1,
            occurred_at=now,
            action_type="rule_created",
            actor_id=uuid4(),
            actor_role="admin",
            actor_type="user",
            actor_display_name="Admin User",
            previous_data=None,
            new_data={"name": "test rule"},
            request_id="req-001",
        )
        assert e.log_id == 1
        assert e.action_type == "rule_created"
        assert e.new_data == {"name": "test rule"}

    def test_optional_fields_none(self):
        now = datetime.now(UTC)
        e = RuleChangeEntry(log_id=2, occurred_at=now, action_type="rule_deleted")
        assert e.actor_id is None
        assert e.previous_data is None


class TestRuleChangePage:
    def test_page_shape(self):
        p = RuleChangePage(
            items=[],
            total=0,
            page=1,
            page_size=25,
            has_next=False,
            rule_id=_RULE,
        )
        assert p.total == 0
        assert p.rule_id == _RULE


# ── Repository tests ────────────────────────────────────────────────────────


class TestRuleChangeHistoryRepository:
    def test_list_changes_returns_list(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        result = repo.list_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert isinstance(result, list)

    def test_list_changes_tenant_scope(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        repo.list_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        params = session.execute.call_args[0][1]
        assert params["tenant_id"] == str(_TENANT)
        assert params["workspace_id"] == str(_WS)
        assert params["rule_id"] == str(_RULE)

    def test_list_changes_rule_entity_filter(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        repo.list_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        sql_str = str(session.execute.call_args[0][0])
        assert "target_entity_type = 'rule'" in sql_str

    def test_list_changes_action_filter(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = RuleChangeQueryParams(action_type="rule_updated")
        repo.list_changes(session, _TENANT, _WS, _RULE, filters)
        params = session.execute.call_args[0][1]
        assert params["action_type"] == "rule_updated"

    def test_list_changes_pagination(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        filters = RuleChangeQueryParams(page=3, page_size=10)
        repo.list_changes(session, _TENANT, _WS, _RULE, filters)
        params = session.execute.call_args[0][1]
        assert params["page_size"] == 10
        assert params["offset"] == 20  # (3 - 1) * 10

    def test_count_changes(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        session.execute.return_value.scalar.return_value = 7
        result = repo.count_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert result == 7

    def test_count_changes_zero(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        session.execute.return_value.scalar.return_value = 0
        result = repo.count_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert result == 0

    def test_list_changes_orders_by_occurred_at_desc(self):
        repo = RuleChangeHistoryRepository()
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        session.execute.return_value = mock_result
        repo.list_changes(session, _TENANT, _WS, _RULE, RuleChangeQueryParams())
        sql_str = str(session.execute.call_args[0][0])
        assert "ORDER BY wal.occurred_at DESC" in sql_str
