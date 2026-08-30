"""
F041 P01 — Repository + Schema Tests (15 tests)
=================================================

Covers:
  - IncidentRepository.get_linked_issue_ids / delete_links
  - LinkIssuesRequest / LinkOperationResponse schemas
  - Existing repo methods used by link operations
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest
from app.models.incident import IncidentIssue
from app.services.incidents.incident_models import (
    LinkIssuesRequest,
    LinkOperationResponse,
)
from app.services.incidents.incident_repository import IncidentRepository

_INC = uuid4()
_ISSUE_A = uuid4()
_ISSUE_B = uuid4()
_ISSUE_C = uuid4()


# ═══════════════════════════════════════════════════════════════════════════════
# get_linked_issue_ids
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetLinkedIssueIds:
    """Tests 1-3: get_linked_issue_ids."""

    def test_get_linked_issue_ids_returns_list(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            (_ISSUE_A,),
            (_ISSUE_B,),
        ]
        repo = IncidentRepository()
        result = repo.get_linked_issue_ids(db, _INC)
        assert result == [_ISSUE_A, _ISSUE_B]

    def test_get_linked_issue_ids_empty(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        repo = IncidentRepository()
        result = repo.get_linked_issue_ids(db, _INC)
        assert result == []

    def test_get_linked_issue_ids_filters_incident(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [(_ISSUE_A,)]
        repo = IncidentRepository()
        repo.get_linked_issue_ids(db, _INC)
        db.query.assert_called_once_with(IncidentIssue.issue_id)


# ═══════════════════════════════════════════════════════════════════════════════
# delete_links
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeleteLinks:
    """Tests 4-5, 14: delete_links."""

    def test_delete_links_returns_count(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 2
        repo = IncidentRepository()
        result = repo.delete_links(db, _INC, [_ISSUE_A, _ISSUE_B])
        assert result == 2

    def test_delete_links_calls_flush(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 1
        repo = IncidentRepository()
        repo.delete_links(db, _INC, [_ISSUE_A])
        db.flush.assert_called_once()

    def test_delete_links_no_matching(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 0
        repo = IncidentRepository()
        result = repo.delete_links(db, _INC, [uuid4()])
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════════
# LinkIssuesRequest
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinkIssuesRequest:
    """Tests 6-8: schema validation."""

    def test_link_request_valid(self):
        req = LinkIssuesRequest(issue_ids=[_ISSUE_A, _ISSUE_B])
        assert len(req.issue_ids) == 2

    def test_link_request_empty_rejects(self):
        with pytest.raises(Exception):
            LinkIssuesRequest(issue_ids=[])

    def test_link_request_single_id(self):
        req = LinkIssuesRequest(issue_ids=[_ISSUE_A])
        assert req.issue_ids == [_ISSUE_A]


# ═══════════════════════════════════════════════════════════════════════════════
# LinkOperationResponse
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinkOperationResponse:
    """Tests 9-11: response schema."""

    def test_link_response_has_incident_id(self):
        resp = LinkOperationResponse(
            incident_id=_INC,
            issue_count=2,
            linked_issue_ids=[_ISSUE_A, _ISSUE_B],
        )
        assert resp.incident_id == _INC

    def test_link_response_has_issue_count(self):
        resp = LinkOperationResponse(
            incident_id=_INC,
            issue_count=3,
            linked_issue_ids=[_ISSUE_A, _ISSUE_B, _ISSUE_C],
        )
        assert resp.issue_count == 3

    def test_link_response_has_linked_ids(self):
        resp = LinkOperationResponse(
            incident_id=_INC,
            issue_count=1,
            linked_issue_ids=[_ISSUE_A],
        )
        assert resp.linked_issue_ids == [_ISSUE_A]


# ═══════════════════════════════════════════════════════════════════════════════
# Existing repo methods used by link flow
# ═══════════════════════════════════════════════════════════════════════════════


class TestExistingRepoMethods:
    """Tests 12, 13, 15: bulk_insert_links, get_issues_in_workspace, count_linked_issues."""

    def test_bulk_insert_links_called(self):
        db = MagicMock()
        repo = IncidentRepository()
        links = [MagicMock(spec=IncidentIssue), MagicMock(spec=IncidentIssue)]
        repo.bulk_insert_links(db, links)
        db.add_all.assert_called_once_with(links)
        db.flush.assert_called_once()

    def test_get_issues_in_workspace_filters(self):
        db = MagicMock()
        ws = uuid4()
        db.query.return_value.filter.return_value.all.return_value = [(_ISSUE_A,)]
        repo = IncidentRepository()
        result = repo.get_issues_in_workspace(db, ws, [_ISSUE_A, _ISSUE_B])
        assert result == [_ISSUE_A]

    def test_count_linked_issues_after_insert(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.count.return_value = 3
        repo = IncidentRepository()
        assert repo.count_linked_issues(db, _INC) == 3
