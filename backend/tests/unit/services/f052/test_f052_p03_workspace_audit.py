"""
F052 P03 — Unit tests for Workspace Service audit write refactoring
===================================================================

Verifies that all four workspace mutation methods (create, update, archive,
restore) now produce ``AuditEntry`` instances written via ``AuditService``
instead of the legacy ``WorkspaceAuditLog`` / ``AuditLogWriter``.

All repository and service dependencies are mocked — no database required.

ACs covered
-----------
P03-AC-01  create_workspace() produces audit entry with target_entity_type="workspace"
P03-AC-02  update_workspace() produces audit entry with diff-only before/after states
P03-AC-03  update_workspace() no-op produces no audit entry
P03-AC-04  archive_workspace() produces audit entry with action_type="workspace_archived"
P03-AC-05  restore_workspace() produces audit entry with action_type="workspace_restored"
P03-AC-07  Audit entries include actor_type="user" from AuditContext
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from app.services.audit.models import AuditEntry
from app.services.workspaces.models import Workspace, WorkspaceStatus
from app.services.workspaces.service import WorkspaceService

# ---------------------------------------------------------------------------
# Shared test UUIDs
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()
_REQ_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Helpers — mock workspace objects and service construction
# ---------------------------------------------------------------------------


def _make_workspace(
    workspace_id: uuid.UUID = _WORKSPACE,
    status: WorkspaceStatus = WorkspaceStatus.active,
    **overrides,
) -> Workspace:
    defaults = dict(
        workspace_id=workspace_id,
        tenant_id=_TENANT,
        workspace_name="Test WS",
        workspace_name_lower="test ws",
        workspace_slug="test-ws",
        description="desc",
        default_timezone="UTC",
        status=status,
        status_reason=None,
        created_at=_NOW,
        updated_at=_NOW,
        created_by=_ACTOR,
        updated_by=_ACTOR,
        version=1,
    )
    defaults.update(overrides)
    return Workspace(**defaults)


def _build_service() -> tuple:
    """Return (service, mocks_dict) with all deps mocked."""
    workspace_repo = MagicMock()
    tenant_repo = MagicMock()
    audit_writer = MagicMock()
    rbac_service = MagicMock()
    audit_service = MagicMock()

    svc = WorkspaceService(
        workspace_repo=workspace_repo,
        tenant_repo=tenant_repo,
        audit_writer=audit_writer,
        rbac_service=rbac_service,
        audit_service=audit_service,
    )
    return svc, {
        "workspace_repo": workspace_repo,
        "tenant_repo": tenant_repo,
        "audit_writer": audit_writer,
        "rbac_service": rbac_service,
        "audit_service": audit_service,
    }


# ═══════════════════════════════════════════════════════════════════════════
# TestWorkspaceCreateAudit
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspaceCreateAudit:
    """P03-AC-01: create_workspace produces audit entry with target_entity_type='workspace'."""

    def test_audit_entry_produced(self):
        svc, mocks = _build_service()
        db = MagicMock()

        # Tenant exists and is active
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}

        # Workspace insert returns a populated Workspace
        created = _make_workspace()
        mocks["workspace_repo"].insert_workspace.return_value = created

        svc.create_workspace(
            db=db,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            actor_role="workspace_administrator",
            raw_payload={"workspace_name": "Test WS", "workspace_slug": "test-ws"},
            request_id=_REQ_ID,
            source_ip="10.0.0.1",
        )

        # audit_service.write should have been called once
        mocks["audit_service"].write.assert_called_once()
        call_args = mocks["audit_service"].write.call_args
        entry: AuditEntry = call_args[0][1]  # second positional arg

        assert isinstance(entry, AuditEntry)
        assert entry.action_type == "workspace_created"
        assert entry.target_entity_type == "workspace"
        assert entry.target_entity_id == _WORKSPACE
        assert entry.actor_type == "user"
        assert entry.workspace_id == _WORKSPACE
        assert entry.actor_id == _ACTOR
        assert entry.request_id == _REQ_ID
        assert entry.source_ip == "10.0.0.1"

    def test_audit_entry_fields_correct(self):
        """P03-AC-01: after_state contains workspace snapshot."""
        svc, mocks = _build_service()
        db = MagicMock()
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}
        created = _make_workspace()
        mocks["workspace_repo"].insert_workspace.return_value = created

        svc.create_workspace(
            db=db,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            actor_role="workspace_administrator",
            raw_payload={"workspace_name": "Test WS", "workspace_slug": "test-ws"},
        )

        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert entry.after_state["workspace_name"] == "Test WS"
        assert entry.before_state is None


# ═══════════════════════════════════════════════════════════════════════════
# TestWorkspaceUpdateAudit
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspaceUpdateAudit:
    """P03-AC-02/03: update produces diff-only audit; no-op skips audit."""

    def test_changed_fields_diffed(self):
        """P03-AC-02: update audit contains only changed fields."""
        svc, mocks = _build_service()
        db = MagicMock()

        existing = _make_workspace(description="old desc")
        mocks["workspace_repo"].find_by_id.return_value = existing
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}

        svc.update_workspace(
            db=db,
            workspace_id=_WORKSPACE,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            raw_payload={"description": "new desc"},
            request_id=_REQ_ID,
        )

        mocks["audit_service"].write.assert_called_once()
        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert entry.action_type == "workspace_metadata_updated"
        assert entry.target_entity_type == "workspace"
        assert entry.target_entity_id == _WORKSPACE
        assert entry.after_state == {"description": "new desc"}
        assert entry.before_state == {"description": "old desc"}

    def test_noop_skips_audit(self):
        """P03-AC-03: no-op update (identical values) writes no audit entry."""
        svc, mocks = _build_service()
        db = MagicMock()

        existing = _make_workspace(description="same")
        mocks["workspace_repo"].find_by_id.return_value = existing
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}

        result = svc.update_workspace(
            db=db,
            workspace_id=_WORKSPACE,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            raw_payload={"description": "same"},
        )

        assert result is None  # no-op
        mocks["audit_service"].write.assert_not_called()

    def test_multiple_field_update(self):
        svc, mocks = _build_service()
        db = MagicMock()

        existing = _make_workspace(description="old", default_timezone="UTC")
        mocks["workspace_repo"].find_by_id.return_value = existing
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}

        svc.update_workspace(
            db=db,
            workspace_id=_WORKSPACE,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            raw_payload={"description": "new", "default_timezone": "US/Eastern"},
        )

        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert "description" in entry.after_state
        assert "default_timezone" in entry.after_state


# ═══════════════════════════════════════════════════════════════════════════
# TestWorkspaceArchiveAudit
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspaceArchiveAudit:
    """P03-AC-04: archive produces audit entry."""

    def test_archive_entry(self):
        svc, mocks = _build_service()
        db = MagicMock()

        existing = _make_workspace(status=WorkspaceStatus.active)
        mocks["workspace_repo"].find_by_id.return_value = existing
        mocks["workspace_repo"].count_active_workspaces.return_value = 2

        svc.archive_workspace(
            db=db,
            workspace_id=_WORKSPACE,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            actor_role="workspace_administrator",
            raw_payload={"status_reason": "no longer needed"},
            request_id=_REQ_ID,
            source_ip="10.0.0.1",
        )

        mocks["audit_service"].write.assert_called_once()
        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert entry.action_type == "workspace_archived"
        assert entry.target_entity_type == "workspace"
        assert entry.target_entity_id == _WORKSPACE
        assert entry.before_state["status"] == "active"
        assert entry.after_state["status"] == "archived"
        assert entry.actor_type == "user"


# ═══════════════════════════════════════════════════════════════════════════
# TestWorkspaceRestoreAudit
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspaceRestoreAudit:
    """P03-AC-05: restore produces audit entry."""

    def test_restore_entry(self):
        svc, mocks = _build_service()
        db = MagicMock()

        existing = _make_workspace(
            status=WorkspaceStatus.archived,
            status_reason="old reason",
        )
        mocks["workspace_repo"].find_by_id.return_value = existing
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}

        svc.restore_workspace(
            db=db,
            workspace_id=_WORKSPACE,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            actor_role="workspace_administrator",
            request_id=_REQ_ID,
            source_ip="10.0.0.1",
        )

        mocks["audit_service"].write.assert_called_once()
        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert entry.action_type == "workspace_restored"
        assert entry.target_entity_type == "workspace"
        assert entry.target_entity_id == _WORKSPACE
        assert entry.before_state["status"] == "archived"
        assert entry.after_state["status"] == "active"
        assert entry.actor_type == "user"


# ═══════════════════════════════════════════════════════════════════════════
# TestWorkspaceAuditContext
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkspaceAuditContext:
    """P03-AC-07: AuditEntry includes correct actor fields from handler."""

    def test_actor_fields_passed_through(self):
        svc, mocks = _build_service()
        db = MagicMock()
        mocks["tenant_repo"].find_tenant_by_id.return_value = {"status": "active"}
        mocks["workspace_repo"].insert_workspace.return_value = _make_workspace()

        svc.create_workspace(
            db=db,
            tenant_id=_TENANT,
            actor_id=_ACTOR,
            actor_role="workspace_administrator",
            raw_payload={"workspace_name": "Test", "workspace_slug": "test"},
            request_id=_REQ_ID,
            source_ip="1.2.3.4",
        )

        entry: AuditEntry = mocks["audit_service"].write.call_args[0][1]
        assert entry.actor_type == "user"
        assert entry.actor_id == _ACTOR
        assert entry.actor_role == "workspace_administrator"
        assert entry.tenant_id == _TENANT
