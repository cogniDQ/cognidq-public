"""
F053 P02 — Service Layer Tests (15 tests)
==========================================

Covers: AuditLogSearchService.get_page, build_export_rows,
        formula-injection escaping, export truncation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.audit.search_models import (
    AuditLogEntry,
    AuditLogPage,
    AuditLogQueryParams,
)
from app.services.audit.search_service import (
    _EXPORT_COLUMNS,
    _TRUNCATION_NOTICE,
    AuditLogSearchService,
    _escape_csv_cell,
)

_TENANT = uuid4()
_WS = uuid4()
_NOW = datetime.now(UTC)


def _sample_row(**overrides):
    base = {
        "log_id": uuid4(),
        "occurred_at": _NOW,
        "action_type": "tenant_created",
        "actor_id": uuid4(),
        "actor_role": "admin",
        "actor_type": "user",
        "actor_display_name": "Test User",
        "target_entity_type": "tenant",
        "target_entity_id": uuid4(),
        "workspace_id": _WS,
        "request_id": "req-001",
    }
    base.update(overrides)
    return base


def _mock_repo():
    return MagicMock()


def _mock_session():
    return MagicMock()


# ── get_page tests ───────────────────────────────────────────────────────────


class TestGetPage:
    def test_page_metadata(self):
        repo = _mock_repo()
        repo.list_entries.return_value = []
        repo.count_entries.return_value = 0
        svc = AuditLogSearchService(repository=repo)
        filters = AuditLogQueryParams(page=3, page_size=25)
        result = svc.get_page(_mock_session(), _TENANT, _WS, filters)
        assert result.page == 3
        assert result.page_size == 25
        assert result.total == 0


# ── build_export_rows tests ──────────────────────────────────────────────────


class TestBuildExportRows:
    def test_returns_list_of_dicts(self):
        repo = _mock_repo()
        repo.export_entries.return_value = [_sample_row()]
        svc = AuditLogSearchService(repository=repo)
        result = svc.build_export_rows(_mock_session(), _TENANT, _WS, AuditLogQueryParams())
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    def test_export_dict_keys_match_columns(self):
        repo = _mock_repo()
        repo.export_entries.return_value = [_sample_row()]
        svc = AuditLogSearchService(repository=repo)
        result = svc.build_export_rows(_mock_session(), _TENANT, _WS, AuditLogQueryParams())
        assert set(result[0].keys()) == set(_EXPORT_COLUMNS)

    def test_truncation_adds_notice(self):
        repo = _mock_repo()
        repo.export_entries.return_value = [_sample_row(log_id=uuid4()) for i in range(10001)]
        svc = AuditLogSearchService(repository=repo)
        result = svc.build_export_rows(_mock_session(), _TENANT, _WS, AuditLogQueryParams())
        assert len(result) == 10001  # 10000 data + 1 notice
        assert result[-1]["log_id"] == _TRUNCATION_NOTICE

    def test_no_truncation_within_limit(self):
        repo = _mock_repo()
        repo.export_entries.return_value = [_sample_row(log_id=uuid4()) for i in range(100)]
        svc = AuditLogSearchService(repository=repo)
        result = svc.build_export_rows(_mock_session(), _TENANT, _WS, AuditLogQueryParams())
        assert len(result) == 100
        assert _TRUNCATION_NOTICE not in [r.get("log_id") for r in result]

    def test_all_values_are_strings(self):
        repo = _mock_repo()
        repo.export_entries.return_value = [_sample_row()]
        svc = AuditLogSearchService(repository=repo)
        result = svc.build_export_rows(_mock_session(), _TENANT, _WS, AuditLogQueryParams())
        for val in result[0].values():
            assert isinstance(val, str)


# ── Formula-injection escaping tests ─────────────────────────────────────────


class TestEscapeCsvCell:
    def test_plain_text_unchanged(self):
        assert _escape_csv_cell("hello") == "hello"

    def test_equals_prefix(self):
        assert _escape_csv_cell("=cmd()") == "'=cmd()"

    def test_plus_prefix(self):
        assert _escape_csv_cell("+1234") == "'+1234"

    def test_minus_prefix(self):
        assert _escape_csv_cell("-formula") == "'-formula"

    def test_at_prefix(self):
        assert _escape_csv_cell("@SUM(A1)") == "'@SUM(A1)"
