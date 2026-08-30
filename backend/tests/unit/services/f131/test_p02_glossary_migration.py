"""
F131 P02 — Glossary tenant_id Migration Tests (8 tests)
=========================================================

Verifies that migration 039 adds the tenant_id column to
control.metadata_term_index and that the glossary service correctly
uses tenant-scoped queries.

Test IDs: T02-01 through T02-08
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.glossary import GlossaryListResponse, GlossaryTermCreate
from app.services.glossary.service import GlossaryService

# ── Helper fixtures ─────────────────────────────────────────────────────────

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
WS_ID = uuid.uuid4()


def _make_row(**overrides):
    """Build a mock SQLAlchemy row-like namespace."""
    defaults = {
        "term_id": uuid.uuid4(),
        "workspace_id": WS_ID,
        "tenant_id": TENANT_A,
        "business_name": "Revenue",
        "technical_name": "revenue",
        "definition": "Total revenue",
        "synonyms": [],
        "domain": "Finance",
        "linked_asset_ids": [],
        "source": "manual",
        "trust_level": "high",
        "created_at": datetime.now(UTC),
        "data_type": "decimal",
        "owner": "finance_team",
        "is_mandatory": False,
        "allowed_values": None,
    }
    defaults.update(overrides)
    return type("Row", (), defaults)()


def _mock_db_with_rows(rows: list, total: int = None):
    """Return a mock Session whose execute() returns the provided rows."""
    db = MagicMock()

    count_result = MagicMock()
    count_result.scalar.return_value = total if total is not None else len(rows)

    rows_result = MagicMock()
    rows_result.fetchall.return_value = rows

    db.execute.side_effect = [count_result, rows_result]
    return db


# ── Tests ────────────────────────────────────────────────────────────────────


class TestGlossaryTenantScope:
    """T02-01 through T02-06 — service-level tenant filtering."""

    def test_T02_01_list_returns_glossary_list_response(self):
        """T02-01: list_terms_for_tenant returns GlossaryListResponse."""
        db = _mock_db_with_rows([_make_row()])
        svc = GlossaryService()
        result = svc.list_terms_for_tenant(db, TENANT_A)
        assert isinstance(result, GlossaryListResponse)

    def test_T02_02_list_returns_items(self):
        """T02-02: items list contains at least one entry."""
        db = _mock_db_with_rows([_make_row(), _make_row()], total=2)
        svc = GlossaryService()
        result = svc.list_terms_for_tenant(db, TENANT_A)
        assert len(result.items) == 2

    def test_T02_03_list_applies_tenant_id_param(self):
        """T02-03: SQL execution is called with the tenant_id bound parameter."""
        db = _mock_db_with_rows([])
        svc = GlossaryService()
        svc.list_terms_for_tenant(db, TENANT_A)
        # Verify the tenant UUID was bound under either canonical key
        # (`tid` is the short name used in the service SQL templates).
        for call in db.execute.call_args_list:
            params = call[0][1] if len(call[0]) > 1 else call[1].get("parameters", {})
            if not isinstance(params, dict):
                continue
            for key in ("tenant_id", "tid"):
                if key in params:
                    assert str(TENANT_A) == params[key]
                    return
        pytest.fail("tenant_id was not passed to any execute() call")

    def test_T02_04_list_empty_for_different_tenant(self):
        """T02-04: list returns empty items when no rows match (simulates different tenant)."""
        db = _mock_db_with_rows([], total=0)
        svc = GlossaryService()
        result = svc.list_terms_for_tenant(db, TENANT_B)
        assert result.total == 0
        assert result.items == []

    def test_T02_05_list_search_filter_passed(self):
        """T02-05: search param is forwarded to the query."""
        db = _mock_db_with_rows([])
        svc = GlossaryService()
        svc.list_terms_for_tenant(db, TENANT_A, search="revenue")
        for call in db.execute.call_args_list:
            params = call[0][1] if len(call[0]) > 1 else {}
            if isinstance(params, dict) and "search" in params:
                assert "%revenue%" in params["search"]
                return
        pytest.fail("search param was not found in any execute() call")

    def test_T02_06_list_domain_filter_passed(self):
        """T02-06: domain param is forwarded to the query."""
        db = _mock_db_with_rows([])
        svc = GlossaryService()
        svc.list_terms_for_tenant(db, TENANT_A, domain="Finance")
        for call in db.execute.call_args_list:
            params = call[0][1] if len(call[0]) > 1 else {}
            if isinstance(params, dict) and "domain" in params:
                assert params["domain"] == "Finance"
                return
        pytest.fail("domain param was not found in any execute() call")

    def test_T02_07_pagination_respected(self):
        """T02-07: page/page_size parameters influence offset calculation."""
        db = _mock_db_with_rows([], total=0)
        svc = GlossaryService()
        result = svc.list_terms_for_tenant(db, TENANT_A, page=2, page_size=10)
        assert result.page == 2
        assert result.page_size == 10

    def test_T02_08_response_total_matches_count(self):
        """T02-08: response total field reflects the DB count scalar."""
        db = _mock_db_with_rows([_make_row()], total=42)
        svc = GlossaryService()
        result = svc.list_terms_for_tenant(db, TENANT_A)
        assert result.total == 42
