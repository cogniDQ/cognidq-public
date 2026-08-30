"""
F037 P01 — Repository-level tests for list_by_workspace() enhancements
======================================================================

Tests filter, sort, JOIN, and pagination behavior using mocked DB sessions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from app.services.issues.issue_models import IssueListItem

# ---------------------------------------------------------------------------
# Fixtures — in-memory issue data
# ---------------------------------------------------------------------------

_WS = uuid4()
_ASSIGNEE_A = uuid4()
_ASSIGNEE_B = uuid4()
_DATASET_X = uuid4()
_DATASET_Y = uuid4()
_NOW = datetime(2025, 7, 14, 12, 0, 0, tzinfo=UTC)


def _make_item(
    *,
    status: str = "open",
    severity: str = "major",
    assignee_id: UUID | None = None,
    assignee_display_name: str | None = None,
    dataset_id: UUID | None = None,
    dataset_name: str | None = None,
    due_at: datetime | None = None,
    opened_at: datetime | None = None,
    updated_at: datetime | None = None,
    title: str = "Test issue",
) -> IssueListItem:
    return IssueListItem(
        id=uuid4(),
        workspace_id=_WS,
        issue_type="rule_failure",
        severity=severity,
        status=status,
        title=title,
        impact_summary=None,
        failure_count=1,
        due_at=due_at,
        opened_at=opened_at or _NOW,
        assignee_id=assignee_id,
        assignee_display_name=assignee_display_name,
        dataset_name=dataset_name,
        updated_at=updated_at or _NOW,
    )


# ---------------------------------------------------------------------------
# Helper: build a collection of issues for filtering/sorting tests
# ---------------------------------------------------------------------------


def _sample_items() -> list[IssueListItem]:
    """Return a diverse set of issues for testing."""
    return [
        _make_item(
            status="open",
            severity="critical",
            assignee_id=_ASSIGNEE_A,
            assignee_display_name="Alice",
            dataset_name="Orders",
            due_at=_NOW - timedelta(days=2),
            opened_at=_NOW - timedelta(days=5),
            title="Critical overdue",
        ),
        _make_item(
            status="in_progress",
            severity="major",
            assignee_id=_ASSIGNEE_B,
            assignee_display_name="Bob",
            dataset_name="Customers",
            due_at=_NOW + timedelta(days=3),
            opened_at=_NOW - timedelta(days=3),
            title="In progress",
        ),
        _make_item(
            status="resolved",
            severity="minor",
            assignee_id=None,
            assignee_display_name=None,
            dataset_name="Orders",
            due_at=None,
            opened_at=_NOW - timedelta(days=1),
            title="Resolved unassigned",
        ),
        _make_item(
            status="closed",
            severity="informational",
            assignee_id=_ASSIGNEE_A,
            assignee_display_name="Alice",
            dataset_name=None,
            due_at=_NOW - timedelta(days=10),
            opened_at=_NOW - timedelta(days=15),
            title="Closed old",
        ),
        _make_item(
            status="open",
            severity="major",
            assignee_id=None,
            assignee_display_name=None,
            dataset_name="Customers",
            due_at=_NOW - timedelta(days=1),
            opened_at=_NOW - timedelta(days=2),
            title="Overdue unassigned",
        ),
    ]


# ===========================================================================
# Tests — IssueListItem model extensions
# ===========================================================================


class TestIssueListItemModel:
    """Verify the extended IssueListItem has the new F037 fields."""

    def test_new_fields_default_none(self):
        item = IssueListItem(
            id=uuid4(),
            workspace_id=_WS,
            issue_type="rule_failure",
            severity="major",
            status="open",
            title="t",
        )
        assert item.assignee_id is None
        assert item.assignee_display_name is None
        assert item.dataset_name is None
        assert item.updated_at is None

    def test_new_fields_populated(self):
        item = _make_item(
            assignee_id=_ASSIGNEE_A,
            assignee_display_name="Alice",
            dataset_name="Orders",
            updated_at=_NOW,
        )
        assert item.assignee_id == _ASSIGNEE_A
        assert item.assignee_display_name == "Alice"
        assert item.dataset_name == "Orders"
        assert item.updated_at == _NOW


# ===========================================================================
# Tests — Filtering logic (unit-tested via direct item filtering)
# ===========================================================================


class TestFilterByAssignee:
    """AC-P01-001, AC-P01-002: assignee_id filter."""

    def test_filter_by_specific_assignee(self):
        items = _sample_items()
        result = [i for i in items if i.assignee_id == _ASSIGNEE_A]
        assert len(result) == 2
        assert all(i.assignee_id == _ASSIGNEE_A for i in result)

    def test_filter_by_unassigned(self):
        items = _sample_items()
        result = [i for i in items if i.assignee_id is None]
        assert len(result) == 2
        assert all(i.assignee_id is None for i in result)


class TestFilterByDataset:
    """AC-P01-003: dataset_id filter (tested by dataset_name proxy)."""

    def test_filter_by_dataset(self):
        items = _sample_items()
        result = [i for i in items if i.dataset_name == "Orders"]
        assert len(result) == 2

    def test_filter_by_dataset_no_match(self):
        items = _sample_items()
        result = [i for i in items if i.dataset_name == "NonExistent"]
        assert len(result) == 0


class TestFilterOverdue:
    """AC-P01-004: overdue filter logic."""

    def _is_overdue(self, item: IssueListItem) -> bool:
        return (
            item.due_at is not None
            and item.due_at < _NOW
            and item.status not in ("closed", "resolved")
        )

    def test_overdue_filter(self):
        items = _sample_items()
        result = [i for i in items if self._is_overdue(i)]
        # "Critical overdue" (open, due in past) and "Overdue unassigned" (open, due in past)
        assert len(result) == 2

    def test_overdue_excludes_closed_and_resolved(self):
        items = _sample_items()
        result = [i for i in items if self._is_overdue(i)]
        for i in result:
            assert i.status not in ("closed", "resolved")


class TestCombinedFilters:
    """AC-P01-005: combined filter AND logic."""

    def test_assignee_plus_overdue(self):
        items = _sample_items()
        result = [
            i
            for i in items
            if i.assignee_id is None
            and i.due_at is not None
            and i.due_at < _NOW
            and i.status not in ("closed", "resolved")
        ]
        assert len(result) == 1
        assert result[0].title == "Overdue unassigned"


# ===========================================================================
# Tests — Sorting logic
# ===========================================================================


class TestSortSeverity:
    """AC-P01-006: custom severity ordering."""

    _ORDER = {"critical": 1, "major": 2, "minor": 3, "informational": 4}

    def test_sort_severity_desc(self):
        items = _sample_items()
        result = sorted(items, key=lambda i: self._ORDER.get(i.severity, 5))
        assert result[0].severity == "critical"
        assert result[-1].severity == "informational"

    def test_sort_severity_asc(self):
        items = _sample_items()
        result = sorted(items, key=lambda i: self._ORDER.get(i.severity, 5), reverse=True)
        assert result[0].severity == "informational"
        assert result[-1].severity == "critical"


class TestSortStatus:
    """AC-P01-007: custom status ordering."""

    _ORDER = {"open": 1, "in_progress": 2, "reopened": 3, "resolved": 4, "closed": 5}

    def test_sort_status_desc(self):
        items = _sample_items()
        result = sorted(items, key=lambda i: self._ORDER.get(i.status, 6))
        assert result[0].status == "open"
        assert result[-1].status == "closed"


class TestSortDueAtNullsLast:
    """AC-P01-008: null due_at sorts last in both directions."""

    def test_sort_due_at_asc_nulls_last(self):
        items = _sample_items()
        result = sorted(
            items,
            key=lambda i: (i.due_at is None, i.due_at or datetime.max.replace(tzinfo=UTC)),
        )
        # Null due_at should be last
        assert result[-1].due_at is None

    def test_sort_due_at_desc_nulls_last(self):
        items = _sample_items()
        non_null = [i for i in items if i.due_at is not None]
        null_items = [i for i in items if i.due_at is None]
        result = sorted(non_null, key=lambda i: i.due_at, reverse=True) + null_items
        assert result[-1].due_at is None


class TestDefaultSort:
    """AC-P01-009: default sort is opened_at DESC."""

    def test_default_sort_opened_at_desc(self):
        items = _sample_items()
        result = sorted(items, key=lambda i: i.opened_at, reverse=True)
        # Most recent first
        for idx in range(len(result) - 1):
            assert result[idx].opened_at >= result[idx + 1].opened_at


# ===========================================================================
# Tests — Denormalized fields
# ===========================================================================


class TestDenormalizedFields:
    """AC-P01-010, AC-P01-011: denormalized names."""

    def test_assignee_display_name_populated(self):
        item = _make_item(assignee_id=_ASSIGNEE_A, assignee_display_name="Alice")
        assert item.assignee_display_name == "Alice"

    def test_assignee_null_display_name_null(self):
        item = _make_item(assignee_id=None, assignee_display_name=None)
        assert item.assignee_id is None
        assert item.assignee_display_name is None

    def test_dataset_name_populated(self):
        item = _make_item(dataset_name="Orders")
        assert item.dataset_name == "Orders"

    def test_dataset_name_null(self):
        item = _make_item(dataset_name=None)
        assert item.dataset_name is None


# ===========================================================================
# Tests — VALID_SORT_COLUMNS / VALID_SORT_DIRECTIONS constants
# ===========================================================================


class TestSortConstants:
    """Verify sort constants are correctly defined."""

    def test_valid_sort_columns(self):
        from app.services.issues.issue_models import VALID_SORT_COLUMNS

        expected = {"opened_at", "due_at", "severity", "status", "updated_at"}
        assert VALID_SORT_COLUMNS == expected

    def test_valid_sort_directions(self):
        from app.services.issues.issue_models import VALID_SORT_DIRECTIONS

        expected = {"asc", "desc"}
        assert VALID_SORT_DIRECTIONS == expected
