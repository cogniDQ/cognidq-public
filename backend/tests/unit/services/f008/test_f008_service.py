"""
F008 P01 — Unit tests: PermissionAuditService and _escape_csv_cell
==================================================================

No database required — repository is mocked.

ACs covered
-----------
AC-P01-007  get_page constructs PermissionAuditPage with correct has_next logic
AC-P01-008  _escape_csv_cell prefixes =, +, -, @ with '
AC-P01-009  build_export_rows appends truncation notice when repo returns 10001 rows
AC-P01-010  actor_display_name=None for system actors
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.permission_audit import (
    PermissionAuditExportQueryParams,
    PermissionAuditPage,
    PermissionAuditQueryParams,
)
from app.services.permission_audit.service import (
    _TRUNCATION_NOTICE,
    PermissionAuditService,
    _escape_csv_cell,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()
_TARGET = uuid.uuid4()
_LOG_ID = uuid.uuid4()
_NOW = datetime(2026, 3, 31, 10, 0, 0, tzinfo=UTC)


def _make_row(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "log_id": _LOG_ID,
        "occurred_at": _NOW,
        "action_type": "role_assigned",
        "actor_id": _ACTOR,
        "actor_role": "admin",
        "actor_type": "user",
        "actor_display_name": "Jane Doe",
        "target_entity_type": "user",
        "target_entity_id": _TARGET,
        "target_display_name": "John Smith",
        "workspace_id": _WORKSPACE,
        "request_id": None,
    }
    base.update(overrides)
    return base


def _make_filters(**overrides) -> PermissionAuditQueryParams:
    defaults: dict[str, Any] = {"page": 1, "page_size": 25, "sort_dir": "desc"}
    defaults.update(overrides)
    return PermissionAuditQueryParams(**defaults)


def _make_mock_repo(rows: list[dict], total: int = None) -> MagicMock:
    repo = MagicMock()
    repo.list_entries.return_value = rows
    repo.count_entries.return_value = total if total is not None else len(rows)
    repo.export_entries.return_value = rows
    return repo


# ---------------------------------------------------------------------------
# Test: get_page / has_next
# ---------------------------------------------------------------------------


class TestGetPage:
    def test_returns_permission_audit_page(self):
        rows = [_make_row()]
        mock_repo = _make_mock_repo(rows, total=1)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()
        filters = _make_filters(page=1, page_size=25)

        result = service.get_page(session, _TENANT, _WORKSPACE, filters)

        assert isinstance(result, PermissionAuditPage)
        assert len(result.items) == 1
        assert result.total == 1

    def test_has_next_true_when_more_pages(self):
        rows = [_make_row() for _ in range(25)]
        mock_repo = _make_mock_repo(rows, total=50)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters(page=1, page_size=25))

        assert result.has_next is True

    def test_has_next_false_on_last_page(self):
        rows = [_make_row() for _ in range(10)]
        mock_repo = _make_mock_repo(rows, total=10)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters(page=1, page_size=25))

        assert result.has_next is False

    def test_has_next_exact_page_boundary_false(self):
        # exactly 25 total, page_size 25, page 1 → no next
        rows = [_make_row() for _ in range(25)]
        mock_repo = _make_mock_repo(rows, total=25)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters(page=1, page_size=25))

        assert result.has_next is False

    def test_has_next_one_over_boundary_true(self):
        # 26 total, page_size 25, page 1 → has next
        rows = [_make_row() for _ in range(25)]
        mock_repo = _make_mock_repo(rows, total=26)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters(page=1, page_size=25))

        assert result.has_next is True

    def test_entry_fields_mapped_correctly(self):
        rows = [_make_row()]
        mock_repo = _make_mock_repo(rows, total=1)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters())

        entry = result.items[0]
        assert entry.log_id == _LOG_ID
        assert entry.action_type == "role_assigned"
        assert entry.actor_display_name == "Jane Doe"
        assert entry.actor_type == "user"

    def test_system_actor_display_name_none(self):
        row = _make_row(actor_id=None, actor_type="system", actor_display_name=None)
        mock_repo = _make_mock_repo([row], total=1)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters())

        entry = result.items[0]
        assert entry.actor_id is None
        assert entry.actor_display_name is None

    def test_empty_result_returns_zero_total(self):
        mock_repo = _make_mock_repo([], total=0)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.get_page(session, _TENANT, _WORKSPACE, _make_filters())

        assert result.total == 0
        assert result.items == []
        assert result.has_next is False


# ---------------------------------------------------------------------------
# Test: build_export_rows — truncation
# ---------------------------------------------------------------------------


class TestBuildExportRows:
    def test_no_truncation_for_exactly_10000_rows(self):
        rows = [_make_row() for _ in range(10_000)]
        mock_repo = _make_mock_repo(rows)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.build_export_rows(
            session, _TENANT, _WORKSPACE, PermissionAuditExportQueryParams()
        )

        assert len(result) == 10_000
        # Last row should not be truncation notice
        assert result[-1]["log_id"] != _TRUNCATION_NOTICE

    def test_truncation_notice_appended_for_10001_rows(self):
        rows = [_make_row() for _ in range(10_001)]
        mock_repo = _make_mock_repo(rows)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.build_export_rows(
            session, _TENANT, _WORKSPACE, PermissionAuditExportQueryParams()
        )

        assert len(result) == 10_001  # 10000 data rows + 1 notice
        last = result[-1]
        assert last["log_id"] == _TRUNCATION_NOTICE

    def test_export_rows_contain_correct_columns(self):
        from app.services.permission_audit.service import _EXPORT_COLUMNS

        rows = [_make_row()]
        mock_repo = _make_mock_repo(rows)
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.build_export_rows(
            session, _TENANT, _WORKSPACE, PermissionAuditExportQueryParams()
        )

        assert len(result) == 1
        for col in _EXPORT_COLUMNS:
            assert col in result[0], f"Missing column: {col}"

    def test_export_for_zero_rows_returns_empty_list(self):
        mock_repo = _make_mock_repo([])
        service = PermissionAuditService(repository=mock_repo)
        session = MagicMock()

        result = service.build_export_rows(
            session, _TENANT, _WORKSPACE, PermissionAuditExportQueryParams()
        )

        assert result == []


# ---------------------------------------------------------------------------
# Test: _escape_csv_cell — formula injection
# ---------------------------------------------------------------------------


class TestEscapeCsvCell:
    @pytest.mark.parametrize("char", ["=", "+", "-", "@"])
    def test_formula_prefix_escaped(self, char: str):
        value = f"{char}SUM(A1:A10)"
        result = _escape_csv_cell(value)
        assert result.startswith("'")
        assert result == f"'{value}"

    def test_normal_value_unchanged(self):
        assert _escape_csv_cell("John Doe") == "John Doe"

    def test_empty_string_unchanged(self):
        assert _escape_csv_cell("") == ""

    def test_none_handled_as_empty_before_calling(self):
        # The service converts None to "" before calling _escape_csv_cell
        assert _escape_csv_cell("") == ""

    def test_non_injection_symbols_unchanged(self):
        assert _escape_csv_cell("Hello, World!") == "Hello, World!"
        assert _escape_csv_cell("100") == "100"
        assert _escape_csv_cell("#comment") == "#comment"

    def test_equals_only_char_escaped(self):
        assert _escape_csv_cell("=") == "'="

    def test_plus_at_start_escaped(self):
        result = _escape_csv_cell("+1234567890")
        assert result == "'+1234567890"

    def test_minus_at_start_escaped(self):
        result = _escape_csv_cell("-revenue")
        assert result == "'-revenue"

    def test_at_at_start_escaped(self):
        result = _escape_csv_cell("@formula")
        assert result == "'@formula"

    def test_middle_injection_char_not_escaped(self):
        # Only the FIRST character triggers escaping
        result = _escape_csv_cell("normal=value")
        assert result == "normal=value"
