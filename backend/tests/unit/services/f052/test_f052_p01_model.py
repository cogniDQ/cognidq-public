"""
F052 P01 — Unit tests for AuditLog ORM model and migration column assertions
=============================================================================

Tests validate that the ``AuditLog`` ORM model correctly maps all 14 columns
of the ``control.workspace_audit_logs`` table (11 original + 3 F052 extensions).

No running database is required — all assertions are against the model class
metadata and in-memory instantiation.

ACs covered
-----------
P01-AC-07  AuditLog ORM model maps all 14 columns correctly
P01-AC-01  actor_type column has server_default 'user'
P01-AC-02  target_entity_type is nullable
P01-AC-03  target_entity_id is nullable
P01-AC-04  workspace_id is nullable
P01-AC-05  actor_id is nullable
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import pytest
from app.models.audit_log import AuditLog

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.uuid4()
_WORKSPACE_ID = uuid.uuid4()
_ACTOR_ID = uuid.uuid4()
_TARGET_ID = uuid.uuid4()
_LOG_ID = uuid.uuid4()
_REQUEST_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# TestAuditLogModel: model instantiation and column mapping
# ---------------------------------------------------------------------------


class TestAuditLogModel:
    """P01-AC-07: AuditLog ORM model maps all 14 columns correctly."""

    def test_table_name_and_schema(self):
        """Model targets control.workspace_audit_logs."""
        assert AuditLog.__tablename__ == "workspace_audit_logs"
        assert AuditLog.__table_args__ == {"schema": "control"}

    def test_all_14_columns_present(self):
        """Model exposes all 14 expected column attributes."""
        expected = {
            "log_id",
            "tenant_id",
            "workspace_id",
            "action_type",
            "actor_id",
            "actor_role",
            "actor_type",
            "target_entity_type",
            "target_entity_id",
            "previous_data",
            "new_data",
            "occurred_at",
            "request_id",
            "source_ip",
        }
        actual = {c.name for c in AuditLog.__table__.columns}
        assert actual == expected

    def test_instantiation_with_all_fields(self):
        """Model can be instantiated with all 14 fields."""
        entry = AuditLog(
            log_id=_LOG_ID,
            tenant_id=_TENANT_ID,
            workspace_id=_WORKSPACE_ID,
            action_type="rule_created",
            actor_id=_ACTOR_ID,
            actor_role="workspace_editor",
            actor_type="user",
            target_entity_type="rule",
            target_entity_id=_TARGET_ID,
            previous_data=None,
            new_data={"name": "test rule"},
            occurred_at=_NOW,
            request_id=_REQUEST_ID,
            source_ip="192.168.1.1",
        )
        assert entry.log_id == _LOG_ID
        assert entry.tenant_id == _TENANT_ID
        assert entry.action_type == "rule_created"
        assert entry.new_data == {"name": "test rule"}

    def test_instantiation_nullable_fields(self):
        """Nullable fields accept None without error."""
        entry = AuditLog(
            log_id=_LOG_ID,
            tenant_id=_TENANT_ID,
            workspace_id=None,
            action_type="tenant_updated",
            actor_id=None,
            actor_role="system",
            actor_type="system",
            target_entity_type=None,
            target_entity_id=None,
            previous_data=None,
            new_data={"name": "updated tenant"},
            occurred_at=_NOW,
            request_id=None,
            source_ip=None,
        )
        assert entry.workspace_id is None
        assert entry.actor_id is None
        assert entry.target_entity_type is None
        assert entry.target_entity_id is None
        assert entry.request_id is None
        assert entry.source_ip is None


# ---------------------------------------------------------------------------
# TestMigrationColumns: column metadata assertions
# ---------------------------------------------------------------------------


class TestMigrationColumns:
    """Validates column definitions match F052 migration requirements."""

    def _col(self, name: str):
        """Retrieve a column object by name."""
        return AuditLog.__table__.columns[name]

    def test_actor_type_not_null_with_default(self):
        """P01-AC-01: actor_type is NOT NULL with server_default 'user'."""
        col = self._col("actor_type")
        assert col.nullable is False
        assert str(col.server_default.arg) == "user"

    def test_target_entity_type_nullable(self):
        """P01-AC-02: target_entity_type is nullable."""
        col = self._col("target_entity_type")
        assert col.nullable is True

    def test_target_entity_id_nullable(self):
        """P01-AC-03: target_entity_id is nullable UUID."""
        col = self._col("target_entity_id")
        assert col.nullable is True

    def test_workspace_id_nullable(self):
        """P01-AC-04: workspace_id is nullable (relaxed from NOT NULL)."""
        col = self._col("workspace_id")
        assert col.nullable is True

    def test_actor_id_nullable(self):
        """P01-AC-05: actor_id is nullable (relaxed from NOT NULL)."""
        col = self._col("actor_id")
        assert col.nullable is True

    def test_primary_key_is_log_id(self):
        """PK is log_id column."""
        col = self._col("log_id")
        assert col.primary_key is True

    def test_new_data_not_nullable(self):
        """new_data (JSONB) must not be nullable — after-state is always required."""
        col = self._col("new_data")
        assert col.nullable is False
