"""
F054 P02 — Service Layer Tests (15 tests)
==========================================

Covers: RuleChangeHistoryService.get_page, describe_action,
        compute_changed_fields, _row_to_entry.
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
from app.services.rules.change_history_service import RuleChangeHistoryService

_TENANT = uuid4()
_WS = uuid4()
_RULE = uuid4()
_NOW = datetime.now(UTC)


def _sample_row(**overrides):
    base = {
        "log_id": 1,
        "occurred_at": _NOW,
        "action_type": "rule_updated",
        "actor_id": uuid4(),
        "actor_role": "admin",
        "actor_type": "user",
        "actor_display_name": "Admin User",
        "previous_data": {"name": "old name"},
        "new_data": {"name": "new name"},
        "request_id": "req-001",
    }
    base.update(overrides)
    return base


def _mock_repo():
    return MagicMock()


def _mock_session():
    return MagicMock()


# ── get_page tests ───────────────────────────────────────────────────────────


class TestGetPage:
    def test_returns_page_model(self):
        repo = _mock_repo()
        repo.list_changes.return_value = [_sample_row()]
        repo.count_changes.return_value = 1
        svc = RuleChangeHistoryService(repository=repo)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert isinstance(result, RuleChangePage)
        assert result.rule_id == _RULE

    def test_has_next_false(self):
        repo = _mock_repo()
        repo.list_changes.return_value = [_sample_row()]
        repo.count_changes.return_value = 1
        svc = RuleChangeHistoryService(repository=repo)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert result.has_next is False

    def test_has_next_true(self):
        repo = _mock_repo()
        repo.list_changes.return_value = [_sample_row() for _ in range(25)]
        repo.count_changes.return_value = 50
        svc = RuleChangeHistoryService(repository=repo)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert result.has_next is True

    def test_items_are_entries(self):
        repo = _mock_repo()
        repo.list_changes.return_value = [_sample_row(), _sample_row(log_id=2)]
        repo.count_changes.return_value = 2
        svc = RuleChangeHistoryService(repository=repo)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, RuleChangeQueryParams())
        for item in result.items:
            assert isinstance(item, RuleChangeEntry)

    def test_empty_page(self):
        repo = _mock_repo()
        repo.list_changes.return_value = []
        repo.count_changes.return_value = 0
        svc = RuleChangeHistoryService(repository=repo)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, RuleChangeQueryParams())
        assert result.total == 0
        assert result.items == []

    def test_page_metadata(self):
        repo = _mock_repo()
        repo.list_changes.return_value = []
        repo.count_changes.return_value = 0
        svc = RuleChangeHistoryService(repository=repo)
        filters = RuleChangeQueryParams(page=3, page_size=10)
        result = svc.get_page(_mock_session(), _TENANT, _WS, _RULE, filters)
        assert result.page == 3
        assert result.page_size == 10


# ── describe_action tests ───────────────────────────────────────────────────


class TestDescribeAction:
    def test_known_actions(self):
        assert RuleChangeHistoryService.describe_action("rule_created") == "Rule created"
        assert RuleChangeHistoryService.describe_action("rule_updated") == "Rule updated"
        assert RuleChangeHistoryService.describe_action("rule_deleted") == "Rule deleted"

    def test_unknown_action_returns_raw(self):
        assert RuleChangeHistoryService.describe_action("unknown_xyz") == "unknown_xyz"


# ── compute_changed_fields tests ────────────────────────────────────────────


class TestComputeChangedFields:
    def test_identifies_changed_fields(self):
        before = {"name": "old", "status": "active", "tags": ["a"]}
        after = {"name": "new", "status": "active", "tags": ["a", "b"]}
        result = RuleChangeHistoryService.compute_changed_fields(before, after)
        assert "name" in result
        assert "tags" in result
        assert "status" not in result

    def test_none_before_returns_empty(self):
        result = RuleChangeHistoryService.compute_changed_fields(None, {"name": "x"})
        assert result == []

    def test_none_after_returns_empty(self):
        result = RuleChangeHistoryService.compute_changed_fields({"name": "x"}, None)
        assert result == []

    def test_no_changes_returns_empty(self):
        data = {"name": "same", "status": "active"}
        result = RuleChangeHistoryService.compute_changed_fields(data, data)
        assert result == []

    def test_new_field_added(self):
        before = {"name": "test"}
        after = {"name": "test", "tags": ["a"]}
        result = RuleChangeHistoryService.compute_changed_fields(before, after)
        assert "tags" in result

    def test_field_removed(self):
        before = {"name": "test", "tags": ["a"]}
        after = {"name": "test"}
        result = RuleChangeHistoryService.compute_changed_fields(before, after)
        assert "tags" in result
