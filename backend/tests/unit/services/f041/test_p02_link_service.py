"""
F041 P02 — IncidentLinkService Tests (15 tests)
=================================================

Covers:
  - add_links: success, dedup, all-dup, not-found, issue-scope, audit, response
  - remove_links: success, not-found, min-enforcement, partial-unlinked, audit, response
  - Audit constants, linked_by_user_id tracking
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest
from app.services.audit.constants import VALID_ACTION_TYPES
from app.services.incidents.incident_link_service import (
    IncidentLinkService,
    IncidentNotFoundError,
    IssueNotFoundError,
    MinimumLinkError,
)

_INC = uuid4()
_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_ISSUE_A = uuid4()
_ISSUE_B = uuid4()
_ISSUE_C = uuid4()


def _mock_audit_ctx():
    ctx = MagicMock()
    ctx.tenant_id = _TENANT
    ctx.actor_id = _USER
    ctx.actor_type = "user"
    ctx.actor_role = "admin"
    ctx.request_id = None
    ctx.source_ip = None
    return ctx


def _make_service(repo=None, audit=None):
    return IncidentLinkService(
        repo=repo or MagicMock(),
        audit_service=audit or MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# add_links
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddLinks:
    """Tests 1-7."""

    def test_add_links_success(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_A, _ISSUE_B]
        repo.get_linked_issue_ids.side_effect = [[], [_ISSUE_A, _ISSUE_B]]
        svc = _make_service(repo=repo)
        resp = svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A, _ISSUE_B], actor_id=_USER)
        assert resp.issue_count == 2
        repo.bulk_insert_links.assert_called_once()

    def test_add_links_deduplicates_existing(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_A, _ISSUE_B]
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A], [_ISSUE_A, _ISSUE_B]]
        svc = _make_service(repo=repo)
        svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A, _ISSUE_B], actor_id=_USER)
        # Only ISSUE_B should be inserted (ISSUE_A already linked)
        links_arg = repo.bulk_insert_links.call_args[0][1]
        assert len(links_arg) == 1

    def test_add_links_all_duplicates(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_A]
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A], [_ISSUE_A]]
        svc = _make_service(repo=repo)
        resp = svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A], actor_id=_USER)
        repo.bulk_insert_links.assert_not_called()
        assert resp.issue_count == 1

    def test_add_links_incident_not_found(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = None
        svc = _make_service(repo=repo)
        with pytest.raises(IncidentNotFoundError):
            svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A], actor_id=_USER)

    def test_add_links_issue_not_in_workspace(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = []  # none found
        svc = _make_service(repo=repo)
        with pytest.raises(IssueNotFoundError):
            svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A], actor_id=_USER)

    def test_add_links_audit_written(self):
        repo = MagicMock()
        audit = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_A]
        repo.get_linked_issue_ids.side_effect = [[], [_ISSUE_A]]
        svc = _make_service(repo=repo, audit=audit)
        svc.add_links(
            MagicMock(),
            _INC,
            _WS,
            issue_ids=[_ISSUE_A],
            actor_id=_USER,
            audit_ctx=_mock_audit_ctx(),
        )
        audit.write.assert_called_once()

    def test_add_links_returns_all_linked_ids(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_B]
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A], [_ISSUE_A, _ISSUE_B]]
        svc = _make_service(repo=repo)
        resp = svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_B], actor_id=_USER)
        assert set(resp.linked_issue_ids) == {_ISSUE_A, _ISSUE_B}


# ═══════════════════════════════════════════════════════════════════════════════
# remove_links
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoveLinks:
    """Tests 8-13."""

    def test_remove_links_success(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A, _ISSUE_B], [_ISSUE_B]]
        svc = _make_service(repo=repo)
        resp = svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A])
        assert resp.issue_count == 1
        repo.delete_links.assert_called_once()

    def test_remove_links_incident_not_found(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = None
        svc = _make_service(repo=repo)
        with pytest.raises(IncidentNotFoundError):
            svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A])

    def test_remove_links_minimum_enforcement(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_linked_issue_ids.return_value = [_ISSUE_A]
        svc = _make_service(repo=repo)
        with pytest.raises(MinimumLinkError):
            svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A])

    def test_remove_links_partial_unlinked(self):
        """IDs not currently linked are silently ignored."""
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A, _ISSUE_B], [_ISSUE_B]]
        svc = _make_service(repo=repo)
        unknown = uuid4()
        svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A, unknown])
        # Only ISSUE_A should be in the delete set (unknown is not linked)
        deleted_ids = set(repo.delete_links.call_args[0][2])
        assert unknown not in deleted_ids
        assert _ISSUE_A in deleted_ids

    def test_remove_links_audit_written(self):
        repo = MagicMock()
        audit = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A, _ISSUE_B], [_ISSUE_B]]
        svc = _make_service(repo=repo, audit=audit)
        svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A], audit_ctx=_mock_audit_ctx())
        audit.write.assert_called_once()

    def test_remove_links_returns_remaining_ids(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_linked_issue_ids.side_effect = [[_ISSUE_A, _ISSUE_B], [_ISSUE_B]]
        svc = _make_service(repo=repo)
        resp = svc.remove_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A])
        assert resp.linked_issue_ids == [_ISSUE_B]


# ═══════════════════════════════════════════════════════════════════════════════
# Audit constants + linked_by_user tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditAndTracking:
    """Tests 14-15."""

    def test_audit_constants_have_link_actions(self):
        assert "incident_links_added" in VALID_ACTION_TYPES
        assert "incident_links_removed" in VALID_ACTION_TYPES

    def test_add_links_records_linked_by_user(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = MagicMock()
        repo.get_issues_in_workspace.return_value = [_ISSUE_A]
        repo.get_linked_issue_ids.side_effect = [[], [_ISSUE_A]]
        svc = _make_service(repo=repo)
        svc.add_links(MagicMock(), _INC, _WS, issue_ids=[_ISSUE_A], actor_id=_USER)
        links_arg = repo.bulk_insert_links.call_args[0][1]
        assert links_arg[0].linked_by_user_id == _USER
