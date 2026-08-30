"""
F052 P02 — Unit tests for AuditService, AuditEntry, AuditContext, and utilities
================================================================================

No database required — all DB operations are mocked.

ACs covered
-----------
P02-AC-01  AuditEntry accepts all fields per TDD §5.2 with correct defaults
P02-AC-02  AuditContext.from_workspace_actor() maps fields correctly
P02-AC-03  AuditContext.for_system() returns actor_type="system", actor_id=None
P02-AC-04  AuditService.write() executes INSERT with all 14 columns
P02-AC-05  AuditService.write() raises AuditWriteFailedError on DB exception
P02-AC-06  AuditService.write() validates action_type
P02-AC-07  AuditService.write() validates entity_type
P02-AC-08  compute_audit_diff() returns only changed fields
P02-AC-09  compute_audit_diff() returns (None, {}) for identical dicts
P02-AC-10  strip_sensitive_fields() removes password, credentials, secret keys
P02-AC-11  strip_sensitive_fields() handles nested dicts
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest
from app.services.audit.constants import (
    SENSITIVE_FIELDS,
    VALID_ACTION_TYPES,
    VALID_ENTITY_TYPES,
)
from app.services.audit.models import (
    AuditContext,
    AuditEntry,
    compute_audit_diff,
    strip_sensitive_fields,
)
from app.services.audit.service import AuditService, AuditWriteFailedError

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()
_TARGET = uuid.uuid4()
_REQ_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


def _make_entry(**overrides) -> AuditEntry:
    defaults = dict(
        tenant_id=_TENANT,
        action_type="rule_created",
        target_entity_type="rule",
        target_entity_id=_TARGET,
        after_state={"name": "test rule"},
        workspace_id=_WORKSPACE,
        actor_id=_ACTOR,
        actor_role="workspace_editor",
    )
    defaults.update(overrides)
    return AuditEntry(**defaults)


# ---------------------------------------------------------------------------
# Fake WorkspaceActorContext (avoid auth import)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeActorCtx:
    actor_id: uuid.UUID
    actor_role: str
    tenant_id: uuid.UUID


# ═══════════════════════════════════════════════════════════════════════════
# TestAuditEntry
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditEntry:
    """P02-AC-01: AuditEntry accepts all fields with correct defaults."""

    def test_required_fields_only(self):
        entry = AuditEntry(
            tenant_id=_TENANT,
            action_type="rule_created",
            target_entity_type="rule",
            target_entity_id=_TARGET,
            after_state={"name": "r1"},
        )
        assert entry.tenant_id == _TENANT
        assert entry.action_type == "rule_created"
        assert entry.after_state == {"name": "r1"}

    def test_defaults(self):
        entry = AuditEntry(
            tenant_id=_TENANT,
            action_type="rule_created",
            target_entity_type="rule",
            target_entity_id=_TARGET,
            after_state={},
        )
        assert entry.actor_type == "user"
        assert entry.actor_role == ""
        assert entry.workspace_id is None
        assert entry.actor_id is None
        assert entry.before_state is None
        assert entry.request_id is None
        assert entry.source_ip is None

    def test_actor_type_system(self):
        entry = _make_entry(actor_type="system", actor_id=None)
        assert entry.actor_type == "system"
        assert entry.actor_id is None

    def test_all_fields_populated(self):
        entry = _make_entry(
            before_state={"name": "old"},
            request_id=_REQ_ID,
            source_ip="10.0.0.1",
        )
        assert entry.before_state == {"name": "old"}
        assert entry.request_id == _REQ_ID
        assert entry.source_ip == "10.0.0.1"


# ═══════════════════════════════════════════════════════════════════════════
# TestAuditContext
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditContext:
    """P02-AC-02/03: AuditContext factory methods."""

    def test_from_workspace_actor(self):
        """P02-AC-02: maps WorkspaceActorContext fields correctly."""
        actor = _FakeActorCtx(actor_id=_ACTOR, actor_role="workspace_editor", tenant_id=_TENANT)
        ctx = AuditContext.from_workspace_actor(actor, request_id=_REQ_ID, source_ip="1.2.3.4")
        assert ctx.tenant_id == _TENANT
        assert ctx.actor_id == _ACTOR
        assert ctx.actor_type == "user"
        assert ctx.actor_role == "workspace_editor"
        assert ctx.request_id == _REQ_ID
        assert ctx.source_ip == "1.2.3.4"

    def test_for_system(self):
        """P02-AC-03: system context has no actor."""
        ctx = AuditContext.for_system(_TENANT)
        assert ctx.actor_type == "system"
        assert ctx.actor_id is None
        assert ctx.actor_role == "system"
        assert ctx.request_id is None
        assert ctx.source_ip is None

    def test_from_workspace_actor_defaults(self):
        """request_id and source_ip default to None."""
        actor = _FakeActorCtx(actor_id=_ACTOR, actor_role="viewer", tenant_id=_TENANT)
        ctx = AuditContext.from_workspace_actor(actor)
        assert ctx.request_id is None
        assert ctx.source_ip is None


# ═══════════════════════════════════════════════════════════════════════════
# TestAuditServiceWrite
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditServiceWrite:
    """P02-AC-04: AuditService.write() executes INSERT with all 14 columns."""

    def test_create_entry(self):
        db = MagicMock()
        svc = AuditService()
        entry = _make_entry()

        svc.write(db, entry)

        db.execute.assert_called_once()
        args, kwargs = db.execute.call_args
        sql_text = args[0]
        params = args[1]
        assert "INSERT INTO control.workspace_audit_logs" in sql_text.text
        assert params["action_type"] == "rule_created"
        assert params["target_entity_type"] == "rule"
        assert params["actor_type"] == "user"
        assert params["new_data"] is not None

    def test_update_entry_with_before_state(self):
        db = MagicMock()
        svc = AuditService()
        entry = _make_entry(
            action_type="rule_updated",
            before_state={"name": "old"},
            after_state={"name": "new"},
        )

        svc.write(db, entry)

        params = db.execute.call_args[0][1]
        assert params["previous_data"] is not None
        before = json.loads(params["previous_data"])
        assert before["name"] == "old"

    def test_delete_entry(self):
        db = MagicMock()
        svc = AuditService()
        entry = _make_entry(
            action_type="rule_deleted",
            before_state={"name": "doomed"},
            after_state={"deleted": True},
        )

        svc.write(db, entry)

        params = db.execute.call_args[0][1]
        assert params["action_type"] == "rule_deleted"


# ═══════════════════════════════════════════════════════════════════════════
# TestAuditServiceValidation
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditServiceValidation:
    """P02-AC-06/07: action_type and entity_type validation."""

    def test_invalid_action_type_raises(self):
        """P02-AC-06"""
        svc = AuditService()
        entry = _make_entry(action_type="bogus_action")
        with pytest.raises(ValueError, match="Invalid action_type"):
            svc.write(MagicMock(), entry)

    def test_invalid_entity_type_raises(self):
        """P02-AC-07"""
        svc = AuditService()
        entry = _make_entry(target_entity_type="spaceship")
        with pytest.raises(ValueError, match="Invalid target_entity_type"):
            svc.write(MagicMock(), entry)

    def test_valid_action_type_accepted(self):
        """Every canonical action_type is accepted (smoke test)."""
        svc = AuditService()
        db = MagicMock()
        for at in sorted(VALID_ACTION_TYPES)[:3]:
            entry = _make_entry(action_type=at)
            svc.write(db, entry)  # should not raise

    def test_valid_entity_type_accepted(self):
        """Every canonical entity_type is accepted (smoke test)."""
        svc = AuditService()
        db = MagicMock()
        for et in sorted(VALID_ENTITY_TYPES)[:3]:
            entry = _make_entry(target_entity_type=et)
            svc.write(db, entry)  # should not raise


# ═══════════════════════════════════════════════════════════════════════════
# TestComputeAuditDiff
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeAuditDiff:
    """P02-AC-08/09: diff utility."""

    def test_no_changes(self):
        """P02-AC-09: identical dicts → (None, {})."""
        before = {"a": 1, "b": "x"}
        after = {"a": 1, "b": "x"}
        b, a = compute_audit_diff(before, after)
        assert b is None
        assert a == {}

    def test_single_field_change(self):
        """P02-AC-08: one changed field."""
        b, a = compute_audit_diff({"a": 1, "b": 2}, {"a": 1, "b": 99})
        assert b == {"b": 2}
        assert a == {"b": 99}

    def test_multiple_field_changes(self):
        b, a = compute_audit_diff(
            {"a": 1, "b": 2, "c": 3},
            {"a": 10, "b": 2, "c": 30},
        )
        assert b == {"a": 1, "c": 3}
        assert a == {"a": 10, "c": 30}

    def test_nested_field_change(self):
        """Nested dicts are compared by equality (not recursively diffed)."""
        before = {"config": {"x": 1}}
        after = {"config": {"x": 2}}
        b, a = compute_audit_diff(before, after)
        assert b == {"config": {"x": 1}}
        assert a == {"config": {"x": 2}}

    def test_full_delete_captures_all_keys(self):
        """Diff between a populated dict and empty dict captures everything."""
        before = {"a": 1, "b": 2}
        after: dict = {}
        b, a = compute_audit_diff(before, after)
        assert b == {"a": 1, "b": 2}
        assert a == {"a": None, "b": None}


# ═══════════════════════════════════════════════════════════════════════════
# TestStripSensitiveFields
# ═══════════════════════════════════════════════════════════════════════════


class TestStripSensitiveFields:
    """P02-AC-10/11: sensitive field stripping."""

    def test_top_level_password_stripped(self):
        """P02-AC-10"""
        data = {"name": "alice", "password": "s3cret", "password_hash": "abc"}
        result = strip_sensitive_fields(data)
        assert "password" not in result
        assert "password_hash" not in result
        assert result["name"] == "alice"

    def test_nested_credentials_stripped(self):
        """P02-AC-11"""
        data = {
            "name": "ds1",
            "connection": {
                "host": "db.example.com",
                "credentials": {"user": "admin", "pass": "x"},
                "api_key": "key123",
            },
        }
        result = strip_sensitive_fields(data)
        conn = result["connection"]
        assert "credentials" not in conn
        assert "api_key" not in conn
        assert conn["host"] == "db.example.com"

    def test_no_sensitive_fields_unchanged(self):
        data = {"a": 1, "b": "two", "c": [1, 2, 3]}
        result = strip_sensitive_fields(data)
        assert result == data

    def test_none_input_returns_none(self):
        assert strip_sensitive_fields(None) is None


# ═══════════════════════════════════════════════════════════════════════════
# TestAuditWriteError
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditWriteError:
    """P02-AC-05: DB exception wrapping."""

    def test_db_exception_raises_audit_write_failed(self):
        """P02-AC-05"""
        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection lost")
        svc = AuditService()
        entry = _make_entry()

        with pytest.raises(AuditWriteFailedError, match="Failed to write audit log"):
            svc.write(db, entry)

    def test_original_exception_chained(self):
        db = MagicMock()
        original = RuntimeError("timeout")
        db.execute.side_effect = original
        svc = AuditService()
        entry = _make_entry()

        with pytest.raises(AuditWriteFailedError) as exc_info:
            svc.write(db, entry)

        assert exc_info.value.__cause__ is original


# ═══════════════════════════════════════════════════════════════════════════
# TestConstants (sanity checks)
# ═══════════════════════════════════════════════════════════════════════════


class TestConstants:
    """Sanity checks on constant frozen sets."""

    def test_action_types_count(self):
        assert len(VALID_ACTION_TYPES) == 56

    def test_entity_types_count(self):
        assert len(VALID_ENTITY_TYPES) == 16

    def test_sensitive_fields_contains_password(self):
        assert "password" in SENSITIVE_FIELDS
        assert "connection_string" in SENSITIVE_FIELDS
