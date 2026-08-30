"""
F051 P01 — IncidentCsvService + Repository Extension Tests (15 tests)
======================================================================

Covers: list_all_for_export, safe_csv_value, CSV generation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.services.incidents.incident_csv_service import (
    _CSV_COLUMNS,
    IncidentCsvService,
    safe_csv_value,
)
from app.services.incidents.incident_repository import IncidentRepository

_WS = uuid4()


def _mock_db():
    return MagicMock()


def _mock_incident(**overrides):
    inc = MagicMock()
    defaults = dict(
        id=uuid4(),
        title="Test Incident",
        severity="critical",
        priority="p1",
        status="open",
        impact_summary="Impact text",
        owner_id=uuid4(),
        created_by_user_id=uuid4(),
        opened_at=datetime(2025, 1, 1, tzinfo=UTC),
        acknowledged_at=None,
        resolved_at=None,
        closed_at=None,
        resolution_summary=None,
        updated_at=datetime(2025, 1, 2, tzinfo=UTC),
        workspace_id=_WS,
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(inc, k, v)
    return inc


# ── Repository Tests ─────────────────────────────────────────────────────────


class TestListAllForExport:
    def test_returns_tuple(self):
        repo = IncidentRepository()
        db = _mock_db()
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = []
        result = repo.list_all_for_export(db, _WS)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_filters_by_workspace(self):
        repo = IncidentRepository()
        db = _mock_db()
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = []
        repo.list_all_for_export(db, _WS)
        db.query.return_value.filter.assert_called_once()

    def test_truncates_at_max_rows(self):
        repo = IncidentRepository()
        db = _mock_db()
        items = [_mock_incident() for _ in range(10_001)]
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = items
        result_items, truncated = repo.list_all_for_export(db, _WS)
        assert truncated is True
        assert len(result_items) == 10_000

    def test_not_truncated_under_limit(self):
        repo = IncidentRepository()
        db = _mock_db()
        items = [_mock_incident() for _ in range(5)]
        q = db.query.return_value.filter.return_value
        q.order_by.return_value.limit.return_value.all.return_value = items
        result_items, truncated = repo.list_all_for_export(db, _WS)
        assert truncated is False
        assert len(result_items) == 5

    def test_applies_status_filter(self):
        repo = IncidentRepository()
        db = _mock_db()
        base_q = db.query.return_value.filter.return_value
        filtered_q = base_q.filter.return_value
        filtered_q.order_by.return_value.limit.return_value.all.return_value = []
        repo.list_all_for_export(db, _WS, status="open")
        base_q.filter.assert_called_once()


# ── safe_csv_value Tests ─────────────────────────────────────────────────────


class TestSafeCsvValue:
    def test_escapes_equals(self):
        assert safe_csv_value("=SUM(A1)") == "'=SUM(A1)"

    def test_escapes_plus(self):
        assert safe_csv_value("+cmd") == "'+cmd"

    def test_escapes_minus(self):
        assert safe_csv_value("-cmd") == "'-cmd"

    def test_escapes_at(self):
        assert safe_csv_value("@user") == "'@user"

    def test_passes_normal_text(self):
        assert safe_csv_value("Hello World") == "Hello World"


# ── IncidentCsvService Tests ─────────────────────────────────────────────────


class TestIncidentCsvService:
    def test_header_row(self):
        svc = IncidentCsvService()
        data = svc.generate_csv([])
        text = data.decode("utf-8-sig")
        header = text.strip().split("\r\n")[0]
        assert header == ",".join(_CSV_COLUMNS)

    def test_data_row_format(self):
        svc = IncidentCsvService()
        inc = _mock_incident(title="Server Down")
        data = svc.generate_csv([inc])
        text = data.decode("utf-8-sig")
        lines = text.strip().split("\r\n")
        assert len(lines) == 2
        assert "Server Down" in lines[1]

    def test_includes_bom(self):
        svc = IncidentCsvService()
        data = svc.generate_csv([])
        assert data[:3] == b"\xef\xbb\xbf"

    def test_truncation_notice(self):
        svc = IncidentCsvService()
        data = svc.generate_csv([], truncated=True)
        text = data.decode("utf-8-sig")
        assert "truncated at 10000" in text.lower()

    def test_empty_list(self):
        svc = IncidentCsvService()
        data = svc.generate_csv([])
        text = data.decode("utf-8-sig")
        lines = [l for l in text.strip().split("\r\n") if l]
        assert len(lines) == 1  # header only
