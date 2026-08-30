"""
F032 P02 — Unit tests for IssueGroupingService
================================================

All 14 tests use mocked IssueRepository.
No database connection required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from app.services.issues.issue_grouping_service import (
    IssueGroupingService,
    _build_grouped_impact_summary,
    _compute_day_window,
)
from app.services.issues.issue_models import IssueDomain

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_WS = uuid.uuid4()
_RULE = uuid.uuid4()
_DS = uuid.uuid4()
_TENANT = uuid.uuid4()
_EXEC = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)


def _make_domain(
    failure_count: int = 10,
    opened_at: datetime = _NOW,
    last_seen_at: datetime = None,
) -> IssueDomain:
    return IssueDomain(
        id=_ISSUE_ID,
        tenant_id=_TENANT,
        workspace_id=_WS,
        flow_execution_id=_EXEC,
        rule_id=_RULE,
        dataset_id=_DS,
        issue_type="threshold_breach",
        severity="major",
        status="open",
        title="[MAJOR] Check failed",
        impact_summary="10 of 100 rows failed",
        failure_count=failure_count,
        opened_at=opened_at,
        last_seen_at=last_seen_at,
    )


def _make_service(mock_repo=None) -> tuple[IssueGroupingService, MagicMock]:
    if mock_repo is None:
        mock_repo = MagicMock()
    svc = IssueGroupingService(repository=mock_repo)
    return svc, mock_repo


# ===========================================================================
# AC-P02-01: one_per_execution → None without any DB call
# ===========================================================================
class TestOnePerExecutionSkip:
    def test_one_per_execution_returns_none(self):
        svc, repo = _make_service()
        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_execution",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None
        repo.find_open_for_grouping.assert_not_called()
        repo.update_for_grouping.assert_not_called()


# ===========================================================================
# AC-P02-02: null rule_id → None without DB call
# ===========================================================================
class TestNullRuleId:
    def test_null_rule_id_returns_none(self):
        svc, repo = _make_service()
        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=None,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None
        repo.find_open_for_grouping.assert_not_called()


# ===========================================================================
# AC-P02-03: null dataset_id → None without DB call
# ===========================================================================
class TestNullDatasetId:
    def test_null_dataset_id_returns_none(self):
        svc, repo = _make_service()
        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=None,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None
        repo.find_open_for_grouping.assert_not_called()


# ===========================================================================
# AC-P02-04 / test: no candidate → returns None
# ===========================================================================
class TestNoCandidateReturnsNone:
    def test_one_per_rule_no_candidate_returns_none(self):
        svc, repo = _make_service()
        repo.find_open_for_grouping.return_value = None

        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None
        repo.update_for_grouping.assert_not_called()


# ===========================================================================
# Candidate found → update called with correct args
# ===========================================================================
class TestCandidateFound:
    def test_one_per_rule_candidate_found_calls_update(self):
        svc, repo = _make_service()
        candidate = _make_domain(failure_count=10)
        updated_domain = _make_domain(failure_count=15)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = updated_domain

        db = MagicMock()
        svc.find_and_update_candidate(
            db=db,
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )

        repo.update_for_grouping.assert_called_once_with(
            db,
            issue_id=_ISSUE_ID,
            delta_rows_failed=5,
            new_impact_summary="15 failures recorded (last seen: 2026-04-01T09:00:00+00:00)",
            new_last_seen_at=_NOW,
        )

    def test_one_per_rule_returns_updated_domain(self):
        svc, repo = _make_service()
        candidate = _make_domain(failure_count=10)
        updated_domain = _make_domain(failure_count=15)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = updated_domain

        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is updated_domain


# ===========================================================================
# one_per_day — day window tests
# ===========================================================================
class TestOnePerDay:
    def test_one_per_day_computes_correct_window(self):
        """
        completed_at = 2026-04-01T22:30:00Z, tz=Europe/Paris (UTC+2).
        Local date is 2026-04-02. Day window: 2026-04-01T22:00:00Z to 2026-04-02T22:00:00Z.
        """
        svc, repo = _make_service()
        repo.find_open_for_grouping.return_value = None

        completed_at = datetime(2026, 4, 1, 22, 30, 0, tzinfo=UTC)
        db = MagicMock()
        svc.find_and_update_candidate(
            db=db,
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_day",
            workspace_timezone="Europe/Paris",
            new_rows_failed=5,
            new_completed_at=completed_at,
        )

        _, kwargs = repo.find_open_for_grouping.call_args
        # 22:30 UTC = 00:30 local (Paris UTC+2 on April 1)
        # so local date is April 2 → window is April 1 22:00Z to April 2 22:00Z
        assert kwargs["day_start_utc"] == datetime(2026, 4, 1, 22, 0, 0, tzinfo=UTC)
        assert kwargs["day_end_utc"] == datetime(2026, 4, 2, 22, 0, 0, tzinfo=UTC)

    def test_one_per_day_within_window_calls_update(self):
        svc, repo = _make_service()
        candidate = _make_domain(failure_count=5)
        updated = _make_domain(failure_count=10)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = updated

        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_day",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is updated
        repo.update_for_grouping.assert_called_once()

    def test_one_per_day_no_candidate_in_window(self):
        svc, repo = _make_service()
        repo.find_open_for_grouping.return_value = None

        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_day",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None
        repo.update_for_grouping.assert_not_called()


# ===========================================================================
# AC-P02 / FR-018: DB exception → None (fallback)
# ===========================================================================
class TestFallbackOnException:
    def test_db_exception_returns_none(self):
        svc, repo = _make_service()
        repo.find_open_for_grouping.side_effect = RuntimeError("db gone")

        result = svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        assert result is None


# ===========================================================================
# Delta / summary / opened_at invariants
# ===========================================================================
class TestInvariants:
    def test_failure_count_delta_correct(self):
        """delta_rows_failed passed to update equals new_rows_failed."""
        svc, repo = _make_service()
        candidate = _make_domain(failure_count=20)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = candidate

        svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=7,
            new_completed_at=_NOW,
        )
        _, kwargs = repo.update_for_grouping.call_args
        assert kwargs["delta_rows_failed"] == 7

    def test_impact_summary_format_grouped(self):
        result = _build_grouped_impact_summary(42, datetime(2026, 4, 1, 9, 0, 0))
        assert result == "42 failures recorded (last seen: 2026-04-01T09:00:00)"

    def test_last_seen_at_set_to_completed_at(self):
        svc, repo = _make_service()
        candidate = _make_domain(failure_count=10)
        updated = _make_domain(failure_count=15, last_seen_at=_NOW)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = updated

        svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        _, kwargs = repo.update_for_grouping.call_args
        assert kwargs["new_last_seen_at"] == _NOW

    def test_opened_at_not_changed(self):
        """The repository update method must NOT be passed opened_at."""
        svc, repo = _make_service()
        original_opened_at = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
        candidate = _make_domain(failure_count=10, opened_at=original_opened_at)
        updated = _make_domain(failure_count=15, opened_at=original_opened_at)
        repo.find_open_for_grouping.return_value = candidate
        repo.update_for_grouping.return_value = updated

        svc.find_and_update_candidate(
            db=MagicMock(),
            workspace_id=_WS,
            rule_id=_RULE,
            dataset_id=_DS,
            policy="one_per_rule",
            workspace_timezone="UTC",
            new_rows_failed=5,
            new_completed_at=_NOW,
        )
        _, kwargs = repo.update_for_grouping.call_args
        # opened_at must not be a kwarg — only delta, impact_summary, last_seen_at, issue_id
        assert "opened_at" not in kwargs
