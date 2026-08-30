"""
F034 P02 — Unit tests: SampleRepository

AC-P02-10: insert() calls db.add() once with an IssueSample instance
AC-P02-11: insert() calls db.flush() and db.refresh()
AC-P02-12: find_by_issue() returns SampleDomain when row found
AC-P02-13: find_by_issue() returns None when no row
AC-P02-14: find_by_issue() filters by workspace_id (isolation)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call

import pytest
from app.models.issue import IssueSample
from app.services.issues.issue_sample_models import SampleDomain
from app.services.issues.sample_repository import SampleRepository

_ISSUE_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_OTHER_WS = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)


def _make_domain(**kwargs) -> SampleDomain:
    base = dict(
        issue_id=_ISSUE_ID,
        workspace_id=_WS_ID,
        sample_count=3,
        rows=[{"col": "val"}],
        masking_applied=False,
        masking_threshold=None,
    )
    base.update(kwargs)
    return SampleDomain(**base)


# ---------------------------------------------------------------------------
# AC-P02-10: insert() calls db.add() with IssueSample
# ---------------------------------------------------------------------------
class TestInsert:
    def test_db_add_called_with_issue_sample(self):
        repo = SampleRepository()
        db = MagicMock()
        domain = _make_domain()
        repo.insert(db, domain)
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, IssueSample)

    def test_flush_and_refresh_called(self):
        repo = SampleRepository()
        db = MagicMock()
        domain = _make_domain()
        repo.insert(db, domain)
        db.flush.assert_called_once()
        db.refresh.assert_called_once()

    def test_correct_fields_passed(self):
        repo = SampleRepository()
        db = MagicMock()
        domain = _make_domain(
            sample_count=7, masking_applied=True, masking_threshold="confidential"
        )
        repo.insert(db, domain)
        added = db.add.call_args[0][0]
        assert added.issue_id == _ISSUE_ID
        assert added.workspace_id == _WS_ID
        assert added.sample_count == 7
        assert added.masking_applied is True
        assert added.masking_threshold == "confidential"


# ---------------------------------------------------------------------------
# AC-P02-12 / AC-P02-13 / AC-P02-14: find_by_issue()
# ---------------------------------------------------------------------------
class TestFindByIssue:
    def _build_db(self, orm_result):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = orm_result
        return db

    def test_returns_domain_when_row_found(self):
        orm_row = MagicMock(spec=IssueSample)
        orm_row.id = uuid.uuid4()
        orm_row.issue_id = _ISSUE_ID
        orm_row.workspace_id = _WS_ID
        orm_row.captured_at = _NOW
        orm_row.sample_count = 3
        orm_row.rows = [{"col": "val"}]
        orm_row.masking_applied = False
        orm_row.masking_threshold = None
        db = self._build_db(orm_row)
        repo = SampleRepository()
        result = repo.find_by_issue(db, _ISSUE_ID, _WS_ID)
        assert result is not None
        assert result.issue_id == _ISSUE_ID
        assert result.sample_count == 3

    def test_returns_none_when_not_found(self):
        db = self._build_db(None)
        repo = SampleRepository()
        result = repo.find_by_issue(db, _ISSUE_ID, _WS_ID)
        assert result is None

    def test_workspace_filter_applied(self):
        # Verify that the query includes workspace_id in the filter call
        db = MagicMock()
        filter_mock = MagicMock()
        filter_mock.first.return_value = None
        db.query.return_value.filter.return_value = filter_mock
        repo = SampleRepository()
        repo.find_by_issue(db, _ISSUE_ID, _OTHER_WS)
        # filter should have been called — workspace_id is passed to it
        db.query.return_value.filter.assert_called_once()
        filter_args = db.query.return_value.filter.call_args
        # The filter call contains two conditions (issue_id and workspace_id)
        # We verify it is called with exactly 2 positional criteria
        assert len(filter_args[0]) == 2
