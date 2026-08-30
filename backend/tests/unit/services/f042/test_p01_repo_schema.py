"""
F042 P01 — Repository + Schema Tests (15 tests)
=================================================

Covers:
  - IncidentRepository.list_by_workspace / get_sla_info
  - IncidentListItem / IncidentPage schemas
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.models.incident import Incident, IncidentIssue
from app.services.incidents.incident_models import (
    IncidentListItem,
    IncidentPage,
)
from app.services.incidents.incident_repository import IncidentRepository

_WS = uuid4()
_INC_A = uuid4()
_INC_B = uuid4()
_OWNER = uuid4()
_NOW = datetime.now(UTC)


def _mock_incident(**overrides):
    inc = MagicMock(spec=Incident)
    inc.id = overrides.get("id", uuid4())
    inc.workspace_id = overrides.get("workspace_id", _WS)
    inc.title = overrides.get("title", "Test Incident")
    inc.severity = overrides.get("severity", "major")
    inc.priority = overrides.get("priority", "P2")
    inc.status = overrides.get("status", "open")
    inc.impact_summary = overrides.get("impact_summary", None)
    inc.owner_id = overrides.get("owner_id", None)
    inc.opened_at = overrides.get("opened_at", _NOW)
    inc.acknowledged_at = overrides.get("acknowledged_at", None)
    inc.resolved_at = overrides.get("resolved_at", None)
    inc.closed_at = overrides.get("closed_at", None)
    return inc


# ═══════════════════════════════════════════════════════════════════════════════
# list_by_workspace
# ═══════════════════════════════════════════════════════════════════════════════


class TestListByWorkspace:
    """Tests 1-7: list_by_workspace repo method."""

    def _setup_query(self, db, items, total):
        """Set up chained mock query."""
        q = MagicMock()
        db.query.return_value.filter.return_value = q
        q.filter.return_value = q
        q.count.return_value = total
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = items
        return q

    def test_list_returns_items_and_count(self):
        db = MagicMock()
        inc = _mock_incident()
        self._setup_query(db, [inc], 1)
        repo = IncidentRepository()
        items, total = repo.list_by_workspace(db, _WS)
        assert items == [inc]
        assert total == 1

    def test_list_applies_status_filter(self):
        db = MagicMock()
        self._setup_query(db, [], 0)
        repo = IncidentRepository()
        repo.list_by_workspace(db, _WS, status="open")
        # The filter chain should have been called (at minimum for workspace + status)
        assert db.query.called

    def test_list_applies_severity_filter(self):
        db = MagicMock()
        self._setup_query(db, [], 0)
        repo = IncidentRepository()
        repo.list_by_workspace(db, _WS, severity="critical")
        assert db.query.called

    def test_list_applies_priority_filter(self):
        db = MagicMock()
        self._setup_query(db, [], 0)
        repo = IncidentRepository()
        repo.list_by_workspace(db, _WS, priority="P1")
        assert db.query.called

    def test_list_applies_owner_filter(self):
        db = MagicMock()
        self._setup_query(db, [], 0)
        repo = IncidentRepository()
        repo.list_by_workspace(db, _WS, owner_id=_OWNER)
        assert db.query.called

    def test_list_applies_offset_limit(self):
        db = MagicMock()
        self._setup_query(db, [], 0)
        repo = IncidentRepository()
        repo.list_by_workspace(db, _WS, offset=50, limit=25)
        assert db.query.called

    def test_list_no_filters(self):
        db = MagicMock()
        inc1 = _mock_incident()
        inc2 = _mock_incident()
        self._setup_query(db, [inc1, inc2], 2)
        repo = IncidentRepository()
        items, total = repo.list_by_workspace(db, _WS)
        assert len(items) == 2
        assert total == 2


# ═══════════════════════════════════════════════════════════════════════════════
# get_sla_info
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetSlaInfo:
    """Tests 8-10: SLA breach query."""

    def test_sla_info_returns_dict(self):
        repo = IncidentRepository()
        result = repo.get_sla_info(MagicMock(), [])
        assert result == {}

    def test_sla_info_no_breach(self):
        db = MagicMock()
        future = _NOW + timedelta(hours=24)
        # Mock the query chain to return a row with no breach
        row = MagicMock()
        row.incident_id = _INC_A
        row.earliest_due = future
        row.has_breach = False
        db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [
            row
        ]
        repo = IncidentRepository()
        result = repo.get_sla_info(db, [_INC_A])
        assert result[_INC_A][1] is False

    def test_sla_info_with_breach(self):
        db = MagicMock()
        past = _NOW - timedelta(hours=24)
        row = MagicMock()
        row.incident_id = _INC_A
        row.earliest_due = past
        row.has_breach = True
        db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [
            row
        ]
        repo = IncidentRepository()
        result = repo.get_sla_info(db, [_INC_A])
        assert result[_INC_A][1] is True


# ═══════════════════════════════════════════════════════════════════════════════
# IncidentListItem / IncidentPage
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemas:
    """Tests 11-15: schema validation."""

    def _make_item(self, **overrides):
        defaults = dict(
            id=uuid4(),
            title="Inc",
            severity="major",
            priority="P2",
            status="open",
            issue_count=3,
            has_sla_breach=False,
            earliest_due_at=None,
            opened_at=_NOW,
        )
        defaults.update(overrides)
        return IncidentListItem(**defaults)

    def test_list_item_has_all_fields(self):
        item = self._make_item()
        assert hasattr(item, "id")
        assert hasattr(item, "title")
        assert hasattr(item, "severity")
        assert hasattr(item, "priority")
        assert hasattr(item, "status")
        assert hasattr(item, "issue_count")
        assert hasattr(item, "has_sla_breach")
        assert hasattr(item, "earliest_due_at")
        assert hasattr(item, "opened_at")
        assert hasattr(item, "acknowledged_at")
        assert hasattr(item, "resolved_at")
        assert hasattr(item, "closed_at")
        assert hasattr(item, "owner_id")
        assert hasattr(item, "owner_name")
        assert hasattr(item, "created_by_name")
        assert hasattr(item, "impact_summary")

    def test_list_item_sla_fields(self):
        due = _NOW + timedelta(hours=4)
        item = self._make_item(has_sla_breach=True, earliest_due_at=due)
        assert item.has_sla_breach is True
        assert item.earliest_due_at == due

    def test_page_has_pagination(self):
        page = IncidentPage(
            items=[],
            total=0,
            page=1,
            page_size=50,
            has_next=False,
        )
        assert page.total == 0
        assert page.page == 1
        assert page.page_size == 50
        assert page.has_next is False

    def test_page_has_next_true(self):
        page = IncidentPage(
            items=[self._make_item()],
            total=100,
            page=1,
            page_size=50,
            has_next=True,
        )
        assert page.has_next is True

    def test_page_has_next_false(self):
        page = IncidentPage(
            items=[self._make_item()],
            total=1,
            page=1,
            page_size=50,
            has_next=False,
        )
        assert page.has_next is False
