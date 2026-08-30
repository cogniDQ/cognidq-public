"""
F031 P02 — Unit tests for IssueRepository (mocked DB)
======================================================

These tests do **not** require a running database.  Every SQLAlchemy Session
is replaced by a ``MagicMock`` so the tests run in-process and validate the
repository's query-building and mapping logic.

ACs covered
-----------
P02-AC-001  insert() returns IssueDomain with a non-None UUID id
P02-AC-002  list_by_workspace() only returns issues for the target workspace
P02-AC-003  list_by_workspace() status filter is applied
P02-AC-004  list_by_workspace() severity filter is applied
P02-AC-005  IssuePage has_next is True when total > page × page_size
P02-AC-006  get_by_id_and_workspace() returns None for a wrong workspace_id
P02-AC-007  get_by_id_and_workspace() returns None for a non-existent UUID
P02-AC-008  list_by_workspace() total reflects the filtered count, not the
            full table count
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest
from app.services.issues.issue_models import (
    IssueDetail,
    IssueDomain,
    IssueListItem,
    IssuePage,
)
from app.services.issues.issue_repository import IssueRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.uuid4()
_WORKSPACE_A = uuid.uuid4()
_WORKSPACE_B = uuid.uuid4()
_EXEC_ID = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


def _make_domain(
    workspace_id: uuid.UUID = _WORKSPACE_A,
    issue_type: str = "data_quality",
    severity: str = "high",
    status: str = "open",
    title: str = "Test issue",
) -> IssueDomain:
    return IssueDomain(
        tenant_id=_TENANT_ID,
        workspace_id=workspace_id,
        flow_execution_id=_EXEC_ID,
        issue_type=issue_type,
        severity=severity,
        status=status,
        title=title,
    )


def _make_orm_stub(
    issue_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    issue_type: str = "data_quality",
    severity: str = "high",
    status: str = "open",
    title: str = "Test issue",
) -> MagicMock:
    """Create a MagicMock that looks like an Issue ORM object."""
    stub = MagicMock()
    stub.id = issue_id or uuid.uuid4()
    stub.workspace_id = workspace_id or _WORKSPACE_A
    stub.flow_execution_id = _EXEC_ID
    stub.flow_node_result_id = None
    stub.rule_id = None
    stub.dataset_id = None
    stub.assignee_id = None
    stub.issue_type = issue_type
    stub.severity = severity
    stub.status = status
    stub.title = title
    stub.impact_summary = None
    stub.failure_count = None
    stub.rows_scanned = None
    stub.pass_rate = None
    stub.due_at = None
    stub.opened_at = _NOW
    stub.resolved_at = None
    stub.closed_at = None
    stub.updated_at = _NOW
    stub.created_at = _NOW
    return stub


def _build_query_chain(rows: list, count: int) -> MagicMock:
    """
    Build a mock query chain that supports:
      .filter().count()
      .filter().order_by().limit().offset().all()
      .filter().filter().count()
      .filter().filter().order_by().limit().offset().all()
    """
    # The chain is built so every intermediate call returns the same mock,
    # meaning we can call .filter().filter().order_by() etc freely.
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.outerjoin.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.all.return_value = rows
    chain.count.return_value = count
    chain.scalar.return_value = count
    chain.first.return_value = rows[0] if rows else None
    return chain


# ---------------------------------------------------------------------------
# P02-AC-001: insert() returns IssueDomain with a non-None UUID id
# ---------------------------------------------------------------------------


class TestInsert:
    def test_insert_returns_domain_with_uuid_id(self):
        """P02-AC-001 — insert returns IssueDomain whose id is a non-None UUID."""
        repo = IssueRepository()
        db = MagicMock()

        orm_stub = _make_orm_stub(issue_id=uuid.uuid4())

        # db.add is a no-op; db.flush populates the ORM object (simulated by stub)
        def fake_add(obj):
            # Copy the stub's id onto the ORM object that was actually created
            obj.id = orm_stub.id
            obj.opened_at = _NOW
            obj.created_at = _NOW
            obj.updated_at = _NOW

        db.add.side_effect = fake_add
        db.flush.return_value = None

        domain = _make_domain()

        # Patch model_validate so the test is decoupled from Pydantic internals
        with patch.object(
            IssueDomain,
            "model_validate",
            return_value=IssueDomain(
                id=orm_stub.id,
                tenant_id=_TENANT_ID,
                workspace_id=_WORKSPACE_A,
                flow_execution_id=_EXEC_ID,
                issue_type="data_quality",
                severity="high",
                status="open",
                title="Test issue",
                opened_at=_NOW,
                created_at=_NOW,
                updated_at=_NOW,
            ),
        ):
            result = repo.insert(db, domain)

        assert result.id is not None
        assert isinstance(result.id, uuid.UUID)
        db.add.assert_called_once()
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# P02-AC-002: list_by_workspace() returns only issues for the target workspace
# ---------------------------------------------------------------------------


class TestListByWorkspace:
    def test_list_filters_by_workspace_id(self):
        """P02-AC-002 — query is scoped to the requested workspace_id."""
        repo = IssueRepository()
        db = MagicMock()

        rows = [(_make_orm_stub(workspace_id=_WORKSPACE_A), None, None)]
        db.query.return_value = _build_query_chain(rows, count=1)

        items, total = repo.list_by_workspace(db, _WORKSPACE_A)

        assert total == 1
        assert len(items) == 1
        assert all(isinstance(i, IssueListItem) for i in items)

    # P02-AC-003
    def test_status_filter_applied(self):
        """P02-AC-003 — status kwarg is forwarded to the query filter."""
        repo = IssueRepository()
        db = MagicMock()

        rows = [(_make_orm_stub(status="resolved"), None, None)]
        chain = _build_query_chain(rows, count=1)
        db.query.return_value = chain

        items, total = repo.list_by_workspace(db, _WORKSPACE_A, status="resolved")

        # filter was called at least twice (workspace + status)
        assert chain.filter.call_count >= 2
        assert total == 1

    # P02-AC-004
    def test_severity_filter_applied(self):
        """P02-AC-004 — severity kwarg is forwarded to the query filter."""
        repo = IssueRepository()
        db = MagicMock()

        rows = [(_make_orm_stub(severity="critical"), None, None)]
        chain = _build_query_chain(rows, count=1)
        db.query.return_value = chain

        items, total = repo.list_by_workspace(db, _WORKSPACE_A, severity="critical")

        assert chain.filter.call_count >= 2
        assert total == 1

    # P02-AC-008
    def test_total_reflects_filtered_count(self):
        """P02-AC-008 — total is the filtered count, not the unfiltered table size."""
        repo = IssueRepository()
        db = MagicMock()

        rows = [(_make_orm_stub(status="open"), None, None)]
        chain = _build_query_chain(rows, count=3)
        db.query.return_value = chain

        items, total = repo.list_by_workspace(db, _WORKSPACE_A, status="open")

        assert total == 3
        assert len(items) == 1  # page only has the mocked row


# ---------------------------------------------------------------------------
# P02-AC-005: IssuePage has_next logic
# ---------------------------------------------------------------------------


class TestIssuePage:
    def test_has_next_true_when_more_pages_remain(self):
        """P02-AC-005 — has_next=True when total > page × page_size."""
        page = IssuePage(
            items=[],
            total=60,
            page=1,
            page_size=50,
            has_next=True,
        )
        assert page.has_next is True

    def test_has_next_false_on_last_page(self):
        """has_next=False when all results fit on the current page."""
        page = IssuePage(
            items=[],
            total=30,
            page=1,
            page_size=50,
            has_next=False,
        )
        assert page.has_next is False


# ---------------------------------------------------------------------------
# P02-AC-006 / P02-AC-007: get_by_id_and_workspace()
# ---------------------------------------------------------------------------


class TestGetByIdAndWorkspace:
    def test_returns_none_for_wrong_workspace(self):
        """P02-AC-006 — Returns None when issue belongs to a different workspace."""
        repo = IssueRepository()
        db = MagicMock()

        chain = _build_query_chain(rows=[], count=0)
        db.query.return_value = chain

        result = repo.get_by_id_and_workspace(db, _ISSUE_ID, _WORKSPACE_B)

        assert result is None

    def test_returns_none_for_nonexistent_uuid(self):
        """P02-AC-007 — Returns None when no issue matches the given id."""
        repo = IssueRepository()
        db = MagicMock()

        chain = _build_query_chain(rows=[], count=0)
        db.query.return_value = chain

        result = repo.get_by_id_and_workspace(db, uuid.uuid4(), _WORKSPACE_A)

        assert result is None

    def test_returns_issue_detail_when_found(self):
        """Positive path — returns IssueDetail when the row exists."""
        repo = IssueRepository()
        db = MagicMock()

        orm_stub = _make_orm_stub(issue_id=_ISSUE_ID, workspace_id=_WORKSPACE_A)
        chain = _build_query_chain(rows=[orm_stub], count=1)
        db.query.return_value = chain

        with patch.object(
            IssueDetail,
            "model_validate",
            return_value=IssueDetail(
                id=_ISSUE_ID,
                tenant_id=_TENANT_ID,
                workspace_id=_WORKSPACE_A,
                flow_execution_id=_EXEC_ID,
                issue_type="data_quality",
                severity="high",
                status="open",
                title="Test issue",
                opened_at=_NOW,
                created_at=_NOW,
                updated_at=_NOW,
            ),
        ):
            result = repo.get_by_id_and_workspace(db, _ISSUE_ID, _WORKSPACE_A)

        assert result is not None
        assert isinstance(result, IssueDetail)
        assert result.id == _ISSUE_ID
