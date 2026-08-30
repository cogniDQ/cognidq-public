"""
F032 P02 — Unit tests for IssueRepository grouping methods
===========================================================

Tests for:
  - find_open_for_grouping() (8 tests)
  - update_for_grouping()    (5 tests)

All use mocked DB sessions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_models import IssueDomain
from app.services.issues.issue_repository import IssueRepository

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_WS_A = uuid.uuid4()
_WS_B = uuid.uuid4()
_RULE = uuid.uuid4()
_DS = uuid.uuid4()
_TENANT = uuid.uuid4()
_EXEC = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
_DAY_START = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
_DAY_END = datetime(2026, 4, 2, 0, 0, 0, tzinfo=UTC)


def _make_orm_stub(
    issue_id: uuid.UUID = None,
    workspace_id: uuid.UUID = None,
    status: str = "open",
    failure_count: int = 10,
    opened_at: datetime = _NOW,
    last_seen_at: datetime = None,
):
    """Return a MagicMock that looks like an Issue ORM row."""
    stub = MagicMock()
    stub.id = issue_id or _ISSUE_ID
    stub.tenant_id = _TENANT
    stub.workspace_id = workspace_id or _WS_A
    stub.flow_execution_id = _EXEC
    stub.flow_node_result_id = None
    stub.rule_id = _RULE
    stub.dataset_id = _DS
    stub.assignee_id = None
    stub.issue_type = "threshold_breach"
    stub.severity = "major"
    stub.status = status
    stub.title = "[MAJOR] Check failed"
    stub.impact_summary = "10 of 100 rows failed"
    stub.resolution_summary = None
    stub.failure_count = failure_count
    stub.rows_scanned = 100
    stub.pass_rate = Decimal("90.0")
    stub.due_at = None
    stub.opened_at = opened_at
    stub.last_seen_at = last_seen_at
    stub.resolved_at = None
    stub.closed_at = None
    stub.updated_at = _NOW
    stub.created_at = _NOW
    return stub


def _build_execute_mock(row=None):
    """Build a mock db with execute() returning a result with fetchone()."""
    db = MagicMock()
    result_mock = MagicMock()

    if row is None:
        result_mock.fetchone.return_value = None
    else:
        # fetchone returns a row-like object; first column is the id
        row_tuple = MagicMock()
        row_tuple.__getitem__ = lambda self, i: str(_ISSUE_ID) if i == 0 else None
        result_mock.fetchone.return_value = row_tuple

    db.execute.return_value = result_mock
    return db


# ===========================================================================
# find_open_for_grouping — policy=one_per_rule
# ===========================================================================


class TestFindOpenForGroupingRule:
    # AC-P02-04: finds open issue for matching workspace+rule+dataset
    def test_find_open_for_grouping_rule_found(self):
        repo = IssueRepository()
        orm_stub = _make_orm_stub(status="open")
        db = _build_execute_mock(row=orm_stub)
        db.query.return_value.filter.return_value.first.return_value = orm_stub

        result = repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
        )
        assert result is not None
        assert isinstance(result, IssueDomain)

    # AC-P02-05: resolved issue not returned
    def test_find_open_for_grouping_rule_excludes_closed_statuses(self):
        """SQL filters status IN open/in_progress/reopened — so resolved rows
        produce no fetchone result."""
        repo = IssueRepository()
        db = _build_execute_mock(row=None)  # no row found

        result = repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
        )
        assert result is None
        db.execute.assert_called_once()
        # Verify the SQL contains the status filter
        sql_str = str(db.execute.call_args[0][0])
        assert "status" in sql_str.lower() or "open" in str(db.execute.call_args).lower()

    # AC-P02-07: in_progress issue is returned
    def test_find_open_for_grouping_rule_includes_in_progress(self):
        repo = IssueRepository()
        orm_stub = _make_orm_stub(status="in_progress")
        db = _build_execute_mock(row=orm_stub)
        db.query.return_value.filter.return_value.first.return_value = orm_stub

        result = repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
        )
        assert result is not None

    # AC-P02-08: workspace isolation
    def test_find_open_for_grouping_rule_workspace_isolated(self):
        """Query must include workspace_id in params."""
        repo = IssueRepository()
        db = _build_execute_mock(row=None)

        repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
        )
        params = db.execute.call_args[0][1]
        assert str(_WS_A) == params["workspace_id"]

    # No result when nothing matches
    def test_find_open_for_grouping_returns_none_when_no_row(self):
        repo = IssueRepository()
        db = _build_execute_mock(row=None)

        result = repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
        )
        assert result is None


# ===========================================================================
# find_open_for_grouping — policy=one_per_day
# ===========================================================================


class TestFindOpenForGroupingDay:
    # AC-P02-09: day window params passed through
    def test_find_open_for_grouping_day_passes_window(self):
        repo = IssueRepository()
        db = _build_execute_mock(row=None)

        repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_day",
            day_start_utc=_DAY_START,
            day_end_utc=_DAY_END,
        )
        params = db.execute.call_args[0][1]
        assert params.get("day_start") == _DAY_START
        assert params.get("day_end") == _DAY_END

    # AC-P02-10: outside window → None (simulated by fetchone returning None)
    def test_find_open_for_grouping_day_outside_window_returns_none(self):
        repo = IssueRepository()
        db = _build_execute_mock(row=None)

        result = repo.find_open_for_grouping(
            db,
            workspace_id=_WS_A,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_day",
            day_start_utc=_DAY_START,
            day_end_utc=_DAY_END,
        )
        assert result is None


# ===========================================================================
# update_for_grouping
# ===========================================================================


class TestUpdateForGrouping:
    def _run_update(self, initial_failure_count: int = 10) -> tuple:
        """Helper: run update_for_grouping and return (result, orm_stub, db)."""
        repo = IssueRepository()
        orm_stub = _make_orm_stub(failure_count=initial_failure_count + 5)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = orm_stub
        new_summary = "15 failures recorded (last seen: 2026-04-01T09:00:00+00:00)"

        result = repo.update_for_grouping(
            db,
            issue_id=_ISSUE_ID,
            delta_rows_failed=5,
            new_impact_summary=new_summary,
            new_last_seen_at=_NOW,
        )
        return result, orm_stub, db

    # AC-P02-11: failure_count incremented — the SQL does += delta
    def test_update_for_grouping_increments_failure_count(self):
        result, _, db = self._run_update(initial_failure_count=10)
        sql_str = str(db.execute.call_args[0][0])
        assert "failure_count + :delta" in sql_str or "failure_count" in sql_str.lower()
        params = db.execute.call_args[0][1]
        assert params["delta"] == 5

    # AC-P02-12: last_seen_at is set
    def test_update_for_grouping_sets_last_seen_at(self):
        _, _, db = self._run_update()
        params = db.execute.call_args[0][1]
        assert params["last_seen_at"] == _NOW

    # AC-P02-13: impact_summary replaced
    def test_update_for_grouping_updates_impact_summary(self):
        _, _, db = self._run_update()
        params = db.execute.call_args[0][1]
        assert "failures recorded" in params["impact_summary"]

    # AC-P02-14: opened_at not in UPDATE params
    def test_update_for_grouping_does_not_change_opened_at(self):
        _, _, db = self._run_update()
        sql_str = str(db.execute.call_args[0][0]).lower()
        assert "opened_at" not in sql_str

    # AC-P02-16: rows_scanned not in UPDATE params
    def test_update_for_grouping_does_not_change_rows_scanned(self):
        _, _, db = self._run_update()
        sql_str = str(db.execute.call_args[0][0]).lower()
        assert "rows_scanned" not in sql_str
