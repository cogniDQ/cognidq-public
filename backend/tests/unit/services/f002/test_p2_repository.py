"""
F002 P02 — Unit tests for the repository layer (mocked DB)
============================================================

These tests do **not** require a running database.  They exercise:

1. Constraint name → typed exception mapping in ``insert_workspace``
2. ``AuditLogWriter`` key-stripping behaviour (workspace_name_lower, version)
3. ``_escape_ilike`` metacharacter escaping helper
4. ``_extract_constraint_name`` parsing helper
5. ``RBACServiceStub`` interface compliance
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from app.services.workspaces.exceptions import (
    AuditWriteFailedError,
    DuplicateNameError,
    DuplicateSlugError,
    RoleGrantFailedError,
)
from app.services.workspaces.models import Workspace, WorkspaceAuditLog, WorkspaceStatus
from app.services.workspaces.rbac import RBACServiceInterface, RBACServiceStub
from app.services.workspaces.repository import (
    AuditLogWriter,
    WorkspaceRepository,
    _escape_ilike,
    _extract_constraint_name,
    _strip_audit_keys,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_workspace(tenant_id: uuid.UUID | None = None) -> Workspace:
    t = tenant_id or uuid.uuid4()
    actor = uuid.uuid4()
    now = datetime.now(UTC)
    return Workspace(
        tenant_id=t,
        workspace_name="My Workspace",
        workspace_name_lower="my workspace",
        workspace_slug="my-workspace",
        default_timezone="UTC",
        created_at=now,
        updated_at=now,
        created_by=actor,
        updated_by=actor,
    )


def _sample_audit_log(workspace_id: uuid.UUID | None = None) -> WorkspaceAuditLog:
    wid = workspace_id or uuid.uuid4()
    now = datetime.now(UTC)
    return WorkspaceAuditLog(
        tenant_id=uuid.uuid4(),
        workspace_id=wid,
        action_type="workspace_created",
        actor_id=uuid.uuid4(),
        actor_role="workspace_administrator",
        new_data={
            "workspace_id": str(wid),
            "workspace_name": "Test",
            "workspace_name_lower": "test",
            "version": 0,
        },
        occurred_at=now,
    )


# ---------------------------------------------------------------------------
# TestConstraintNameExtraction
# ---------------------------------------------------------------------------


class TestConstraintNameExtraction:
    def test_extracts_name_constraint(self):
        msg = 'duplicate key value violates unique constraint "uq_workspaces_name_lower_per_tenant"'
        assert _extract_constraint_name(msg) == "uq_workspaces_name_lower_per_tenant"

    def test_extracts_slug_constraint(self):
        msg = 'duplicate key value violates unique constraint "uq_workspaces_slug_per_tenant"'
        assert _extract_constraint_name(msg) == "uq_workspaces_slug_per_tenant"

    def test_returns_none_when_not_found(self):
        assert _extract_constraint_name("some unrelated error") is None

    def test_case_insensitive(self):
        msg = 'UNIQUE CONSTRAINT "uq_workspaces_name_lower_per_tenant"'
        assert _extract_constraint_name(msg) == "uq_workspaces_name_lower_per_tenant"


# ---------------------------------------------------------------------------
# TestUniqueViolationMapping
# ---------------------------------------------------------------------------


class TestUniqueViolationMapping:
    """
    ``insert_workspace`` must translate psycopg2 UniqueViolation to the
    correct typed exception based on the constraint name.
    """

    def _make_repo_and_fake_unique_violation(self, constraint_name: str):
        """Return (repo, db_mock) where db.execute raises a UniqueViolation for the given constraint."""
        try:
            from psycopg2.errors import UniqueViolation
        except ImportError:
            pytest.skip("psycopg2 not available")

        # Build a fake UniqueViolation whose string representation contains the constraint name
        exc = UniqueViolation(f'duplicate key value violates unique constraint "{constraint_name}"')

        db_mock = MagicMock()
        db_mock.execute.side_effect = exc

        return WorkspaceRepository(), db_mock

    def test_duplicate_name_raises_DuplicateNameError(self):
        repo, db = self._make_repo_and_fake_unique_violation("uq_workspaces_name_lower_per_tenant")
        workspace = _sample_workspace()
        with pytest.raises(DuplicateNameError):
            repo.insert_workspace(db, workspace)

    def test_duplicate_slug_raises_DuplicateSlugError(self):
        repo, db = self._make_repo_and_fake_unique_violation("uq_workspaces_slug_per_tenant")
        workspace = _sample_workspace()
        with pytest.raises(DuplicateSlugError):
            repo.insert_workspace(db, workspace)

    def test_unknown_unique_violation_propagates(self):
        """A unique violation on an unexpected constraint should not be swallowed."""
        try:
            from psycopg2.errors import UniqueViolation
        except ImportError:
            pytest.skip("psycopg2 not available")

        exc = UniqueViolation('duplicate key value violates unique constraint "something_else"')
        db_mock = MagicMock()
        db_mock.execute.side_effect = exc

        repo = WorkspaceRepository()
        workspace = _sample_workspace()
        with pytest.raises(Exception) as exc_info:
            repo.insert_workspace(db_mock, workspace)
        # Must not be silently transformed into DuplicateNameError / DuplicateSlugError
        assert not isinstance(exc_info.value, (DuplicateNameError, DuplicateSlugError))


# ---------------------------------------------------------------------------
# TestAuditKeyStripping
# ---------------------------------------------------------------------------


class TestAuditKeyStripping:
    """
    ``_strip_audit_keys`` (used by ``AuditLogWriter``) must remove
    ``workspace_name_lower`` and ``version`` from JSONB payloads.
    """

    def test_strips_workspace_name_lower(self):
        data = {"workspace_name": "Test", "workspace_name_lower": "test"}
        result = json.loads(_strip_audit_keys(data))
        assert "workspace_name_lower" not in result
        assert result["workspace_name"] == "Test"

    def test_strips_version(self):
        data = {"workspace_name": "Test", "version": 5}
        result = json.loads(_strip_audit_keys(data))
        assert "version" not in result

    def test_strips_both_simultaneously(self):
        data = {
            "workspace_id": "abc",
            "workspace_name_lower": "stripped",
            "version": 0,
            "status": "active",
        }
        result = json.loads(_strip_audit_keys(data))
        assert "workspace_name_lower" not in result
        assert "version" not in result
        assert result["workspace_id"] == "abc"
        assert result["status"] == "active"

    def test_none_returns_none(self):
        assert _strip_audit_keys(None) is None

    def test_empty_dict_returns_empty_json(self):
        result = json.loads(_strip_audit_keys({}))
        assert result == {}

    def test_keys_not_present_left_intact(self):
        data = {"workspace_name": "Test", "description": "hello"}
        result = json.loads(_strip_audit_keys(data))
        assert result == {"workspace_name": "Test", "description": "hello"}


# ---------------------------------------------------------------------------
# TestAuditLogWriterFailure
# ---------------------------------------------------------------------------


class TestAuditLogWriterFailure:
    """``AuditLogWriter.write`` must raise ``AuditWriteFailedError`` on any DB error."""

    def test_raises_audit_write_failed_error_on_db_exception(self):
        db_mock = MagicMock()
        db_mock.execute.side_effect = Exception("DB connection lost")

        writer = AuditLogWriter()
        entry = _sample_audit_log()

        with pytest.raises(AuditWriteFailedError):
            writer.write(db_mock, entry)

    def test_original_exception_is_chained(self):
        db_mock = MagicMock()
        original = RuntimeError("boom")
        db_mock.execute.side_effect = original

        writer = AuditLogWriter()
        entry = _sample_audit_log()

        with pytest.raises(AuditWriteFailedError) as exc_info:
            writer.write(db_mock, entry)
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# TestIlikEscaping
# ---------------------------------------------------------------------------


class TestIlikeEscaping:
    """``_escape_ilike`` must escape %, _, and \\ metacharacters."""

    def test_escapes_percent(self):
        result = _escape_ilike("test%")
        assert "\\%" in result

    def test_escapes_underscore(self):
        result = _escape_ilike("test_name")
        assert "\\_" in result

    def test_escapes_backslash(self):
        result = _escape_ilike("test\\path")
        assert "\\\\" in result

    def test_wraps_in_percent(self):
        result = _escape_ilike("hello")
        assert result.startswith("%")
        assert result.endswith("%")

    def test_plain_string_unchanged_content(self):
        result = _escape_ilike("hello")
        assert "hello" in result

    def test_combined_metacharacters(self):
        result = _escape_ilike("50%_of\\all")
        assert "\\%" in result
        assert "\\_" in result
        assert "\\\\" in result


# ---------------------------------------------------------------------------
# TestRBACServiceStubInterfaceCompliance
# ---------------------------------------------------------------------------


class TestRBACServiceStubInterfaceCompliance:
    """``RBACServiceStub`` must satisfy ``RBACServiceInterface``."""

    def test_stub_is_subclass_of_interface(self):
        assert issubclass(RBACServiceStub, RBACServiceInterface)

    def test_stub_instance_is_instance_of_interface(self):
        assert isinstance(RBACServiceStub(), RBACServiceInterface)

    def test_has_grant_workspace_admin_method(self):
        stub = RBACServiceStub()
        assert callable(getattr(stub, "grant_workspace_admin", None))


# ---------------------------------------------------------------------------
# TestRBACServiceStubMissingTable
# ---------------------------------------------------------------------------


class TestRBACServiceStubMissingTable:
    """
    When ``control.role_assignments`` does not exist, the stub must return
    without error (no ``RoleGrantFailedError`` raised).
    """

    def test_missing_table_no_error(self):
        stub = RBACServiceStub()

        # Mock the session so _role_assignments_exists returns False
        db_mock = MagicMock()
        # First execute call (information_schema check) returns None
        db_mock.execute.return_value.fetchone.return_value = None

        # Should not raise
        stub.grant_workspace_admin(uuid.uuid4(), uuid.uuid4(), db_mock)

    def test_missing_table_does_not_raise_role_grant_failed(self):
        stub = RBACServiceStub()
        db_mock = MagicMock()
        db_mock.execute.return_value.fetchone.return_value = None

        try:
            stub.grant_workspace_admin(uuid.uuid4(), uuid.uuid4(), db_mock)
        except RoleGrantFailedError:
            pytest.fail("RoleGrantFailedError should not be raised when table is missing")
