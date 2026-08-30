"""
F131 P04 — Audit Log Pydantic Fix Tests (5 tests)
===================================================

Verifies that AuditLogEntry.log_id is typed as UUID (not int) and that
the search service correctly constructs AuditLogEntry from UUID log_id values.

Test IDs: T04-01 through T04-05
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import pytest
from app.services.audit.search_models import AuditLogEntry, AuditLogPage
from app.services.audit.search_service import AuditLogQueryParams, AuditLogSearchService

_TENANT = uuid.uuid4()
_WS = uuid.uuid4()
_NOW = datetime.now(UTC)


def _mock_repo():
    return MagicMock()


def _uuid_row(**overrides):
    base = {
        "log_id": uuid.uuid4(),
        "occurred_at": _NOW,
        "action_type": "workspace_created",
        "actor_id": uuid.uuid4(),
        "actor_role": "workspace_admin",
        "actor_type": "user",
        "actor_display_name": "Alice",
        "target_entity_type": "workspace",
        "target_entity_id": uuid.uuid4(),
        "workspace_id": _WS,
        "request_id": None,
    }
    base.update(overrides)
    return base


class TestAuditLogEntryUUID:
    def test_T04_01_log_id_field_accepts_uuid_object(self):
        """T04-01: AuditLogEntry accepts a UUID object for log_id."""
        lid = uuid.uuid4()
        entry = AuditLogEntry(
            log_id=lid,
            occurred_at=_NOW,
            action_type="workspace_created",
        )
        assert entry.log_id == lid
        assert isinstance(entry.log_id, uuid.UUID)

    def test_T04_02_log_id_field_accepts_uuid_string(self):
        """T04-02: AuditLogEntry accepts a valid UUID string for log_id."""
        lid_str = str(uuid.uuid4())
        entry = AuditLogEntry(
            log_id=lid_str,
            occurred_at=_NOW,
            action_type="workspace_created",
        )
        assert str(entry.log_id) == lid_str

    def test_T04_03_log_id_rejects_plain_integer(self):
        """T04-03: AuditLogEntry rejects a plain integer for log_id."""
        with pytest.raises(Exception):
            AuditLogEntry(
                log_id=1,
                occurred_at=_NOW,
                action_type="workspace_created",
            )

    def test_T04_04_service_builds_entry_from_uuid_row(self):
        """T04-04: AuditLogSearchService._row_to_entry works with UUID log_id."""
        row = _uuid_row()
        entry = AuditLogSearchService._row_to_entry(row)
        assert isinstance(entry, AuditLogEntry)
        assert isinstance(entry.log_id, uuid.UUID)

    def test_T04_05_get_page_returns_entries_with_uuid_log_ids(self):
        """T04-05: get_page returns AuditLogPage with UUID log_ids."""
        repo = _mock_repo()
        repo.list_entries.return_value = [_uuid_row(), _uuid_row()]
        repo.count_entries.return_value = 2
        svc = AuditLogSearchService(repository=repo)
        page = svc.get_page(MagicMock(), _TENANT, _WS, AuditLogQueryParams())
        assert isinstance(page, AuditLogPage)
        assert len(page.items) == 2
        for item in page.items:
            assert isinstance(item.log_id, uuid.UUID)
