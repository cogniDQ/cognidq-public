"""
F042 P02 — IncidentListService Tests (15 tests)
==================================================

Covers:
  - list_incidents: pagination, filtering, SLA enrichment, name resolution
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.services.incidents.incident_list_service import IncidentListService
from app.services.incidents.incident_models import IncidentPage

_WS = uuid4()
_NOW = datetime.now(UTC)


def _mock_incident(**overrides):
    inc = MagicMock()
    inc.id = overrides.get("id", uuid4())
    inc.title = overrides.get("title", "Pipeline Failure")
    inc.severity = overrides.get("severity", "critical")
    inc.priority = overrides.get("priority", "P1")
    inc.status = overrides.get("status", "open")
    inc.impact_summary = overrides.get("impact_summary", "High impact")
    inc.owner_id = overrides.get("owner_id", uuid4())
    inc.opened_at = overrides.get("opened_at", _NOW)
    inc.acknowledged_at = overrides.get("acknowledged_at", None)
    inc.resolved_at = overrides.get("resolved_at", None)
    inc.closed_at = overrides.get("closed_at", None)
    # Relationships
    owner = MagicMock()
    owner.full_name = "Alice"
    inc.owner = overrides.get("owner", owner)
    creator = MagicMock()
    creator.full_name = "Bob"
    inc.creator = overrides.get("creator", creator)
    return inc


def _make_service(items=None, total=None, sla=None):
    repo = MagicMock()
    repo.list_by_workspace.return_value = (
        items or [],
        total if total is not None else len(items or []),
    )
    repo.count_linked_issues.return_value = 3
    repo.get_sla_info.return_value = sla or {}
    return IncidentListService(repo=repo), repo


# ═══════════════════════════════════════════════════════════════════════════════
# Core listing
# ═══════════════════════════════════════════════════════════════════════════════


class TestListCore:
    """Tests 1-5: core list behaviour."""

    def test_list_returns_page(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert isinstance(result, IncidentPage)
        assert len(result.items) == 1

    def test_list_items_have_issue_count(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].issue_count == 3

    def test_list_items_have_owner_name(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].owner_name == "Alice"

    def test_list_items_have_creator_name(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].created_by_name == "Bob"

    def test_list_sla_breach_enriched(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, True)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].has_sla_breach is True


# ═══════════════════════════════════════════════════════════════════════════════
# SLA + Timestamps
# ═══════════════════════════════════════════════════════════════════════════════


class TestSlaAndTimestamps:
    """Tests 6, 13-15: SLA enrichment and item fields."""

    def test_list_earliest_due_enriched(self):
        inc = _mock_incident()
        due = _NOW + timedelta(hours=8)
        svc, _ = _make_service(items=[inc], sla={inc.id: (due, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].earliest_due_at == due

    def test_list_item_timestamps(self):
        ack = _NOW - timedelta(hours=2)
        inc = _mock_incident(acknowledged_at=ack)
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].acknowledged_at == ack

    def test_list_severity_in_item(self):
        inc = _mock_incident(severity="minor")
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].severity == "minor"

    def test_list_priority_in_item(self):
        inc = _mock_incident(priority="P3")
        svc, _ = _make_service(items=[inc], sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items[0].priority == "P3"


# ═══════════════════════════════════════════════════════════════════════════════
# Pagination
# ═══════════════════════════════════════════════════════════════════════════════


class TestPagination:
    """Tests 7-9, 10-12: pagination behaviour."""

    def test_list_pagination_page_1(self):
        inc = _mock_incident()
        svc, repo = _make_service(items=[inc], total=100, sla={inc.id: (None, False)})
        svc.list_incidents(MagicMock(), _WS, page=1, page_size=50)
        call_kwargs = repo.list_by_workspace.call_args
        assert call_kwargs.kwargs["offset"] == 0
        assert call_kwargs.kwargs["limit"] == 50

    def test_list_pagination_page_2(self):
        inc = _mock_incident()
        svc, repo = _make_service(items=[inc], total=100, sla={inc.id: (None, False)})
        svc.list_incidents(MagicMock(), _WS, page=2, page_size=50)
        call_kwargs = repo.list_by_workspace.call_args
        assert call_kwargs.kwargs["offset"] == 50

    def test_list_has_next_computed(self):
        inc = _mock_incident()
        svc, _ = _make_service(items=[inc], total=100, sla={inc.id: (None, False)})
        result = svc.list_incidents(MagicMock(), _WS, page=1, page_size=50)
        assert result.has_next is True

    def test_list_empty_workspace(self):
        svc, _ = _make_service(items=[], total=0)
        result = svc.list_incidents(MagicMock(), _WS)
        assert result.items == []
        assert result.total == 0
        assert result.has_next is False

    def test_list_filters_forwarded(self):
        svc, repo = _make_service(items=[], total=0)
        owner = uuid4()
        svc.list_incidents(
            MagicMock(),
            _WS,
            status="open",
            severity="critical",
            priority="P1",
            owner_id=owner,
        )
        call_kwargs = repo.list_by_workspace.call_args.kwargs
        assert call_kwargs["status"] == "open"
        assert call_kwargs["severity"] == "critical"
        assert call_kwargs["priority"] == "P1"
        assert call_kwargs["owner_id"] == owner

    def test_list_default_page_size(self):
        svc, repo = _make_service(items=[], total=0)
        svc.list_incidents(MagicMock(), _WS)
        call_kwargs = repo.list_by_workspace.call_args.kwargs
        assert call_kwargs["limit"] == 50
