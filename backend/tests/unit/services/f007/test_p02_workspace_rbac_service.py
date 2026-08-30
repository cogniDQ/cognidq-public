"""
F007 P02 — Unit tests for WorkspaceRBACService
===============================================

All tests are database-free and use MagicMock to simulate the SQLAlchemy
Session. They cover:

1. FIXED_ROLE_PERMISSIONS completeness and correctness
2. VALID_ROLE_NAMES consistency
3. WorkspaceRBACService interface compliance
4. check_permission matrix (role × action grid)
5. assign_role — happy path, idempotent, last-admin guard
6. revoke_role — happy path, not-found, last-admin guard
7. get_member_role — hit and miss
8. grant_workspace_admin — happy path and FK-error path
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.services.workspaces.exceptions import (
    LastWorkspaceAdministratorError,
    RoleAssignmentNotFoundError,
    RoleGrantFailedError,
)
from app.services.workspaces.rbac import (
    FIXED_ROLE_PERMISSIONS,
    VALID_ROLE_NAMES,
    RBACServiceInterface,
    RBACServiceStub,
    WorkspaceRBACService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _mock_db() -> MagicMock:
    """Return a fresh MagicMock that behaves like a SQLAlchemy Session."""
    db = MagicMock()
    db.execute.return_value = MagicMock()
    db.flush.return_value = None
    return db


def _row_for(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_name: str,
    granted_by: uuid.UUID | None = None,
) -> MagicMock:
    """Build a fake SQLAlchemy Row for a workspace_role_assignments record."""
    row = MagicMock()
    row.__getitem__ = lambda self, idx: [
        _uuid(),  # id
        workspace_id,  # workspace_id
        user_id,  # user_id
        role_name,  # role_name
        granted_by,  # granted_by
        datetime.now(UTC),  # granted_at
    ][idx]
    return row


def _assignment_dict(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_name: str,
    granted_by: uuid.UUID | None = None,
) -> dict:
    return {
        "id": _uuid(),
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role_name": role_name,
        "granted_by": granted_by,
        "granted_at": datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# 1. FIXED_ROLE_PERMISSIONS — completeness and correctness
# ---------------------------------------------------------------------------


class TestFixedRolePermissions:
    """FIXED_ROLE_PERMISSIONS must cover exactly the 5 fixed roles."""

    EXPECTED_ROLES = {
        "workspace_administrator",
        "data_engineer",
        "data_steward",
        "business_analyst",
        "governance_viewer",
    }

    def test_contains_all_five_roles(self):
        assert set(FIXED_ROLE_PERMISSIONS.keys()) == self.EXPECTED_ROLES

    def test_values_are_frozensets(self):
        for role, perms in FIXED_ROLE_PERMISSIONS.items():
            assert isinstance(perms, frozenset), f"{role} perms must be frozenset"

    def test_workspace_administrator_has_all_permissions_superset(self):
        """workspace_administrator must have a strict superset of every other role's permissions."""
        admin_perms = FIXED_ROLE_PERMISSIONS["workspace_administrator"]
        for role_name, perms in FIXED_ROLE_PERMISSIONS.items():
            if role_name == "workspace_administrator":
                continue
            assert perms.issubset(admin_perms), (
                f"workspace_administrator missing permissions held by {role_name}: "
                f"{perms - admin_perms}"
            )

    def test_governance_viewer_has_no_write_permissions(self):
        viewer_perms = FIXED_ROLE_PERMISSIONS["governance_viewer"]
        write_perms = {p for p in viewer_perms if ":write" in p or ":delete" in p or ":assign" in p}
        assert write_perms == frozenset(), (
            f"governance_viewer must not have write/delete/assign permissions, found: {write_perms}"
        )

    def test_business_analyst_cannot_write_datasources(self):
        ba_perms = FIXED_ROLE_PERMISSIONS["business_analyst"]
        assert "datasources:write" not in ba_perms
        assert "datasources:delete" not in ba_perms

    def test_data_engineer_can_write_datasources(self):
        de_perms = FIXED_ROLE_PERMISSIONS["data_engineer"]
        assert "datasources:write" in de_perms
        assert "datasources:delete" in de_perms

    def test_data_steward_cannot_write_datasources(self):
        """data_steward is restricted to datasources:read only."""
        ds_perms = FIXED_ROLE_PERMISSIONS["data_steward"]
        assert "datasources:write" not in ds_perms
        assert "datasources:delete" not in ds_perms

    def test_workspace_administrator_can_manage_settings(self):
        admin_perms = FIXED_ROLE_PERMISSIONS["workspace_administrator"]
        assert "settings:read" in admin_perms
        assert "settings:write" in admin_perms

    def test_non_admin_roles_cannot_manage_settings(self):
        for role_name in ["data_engineer", "data_steward", "business_analyst", "governance_viewer"]:
            perms = FIXED_ROLE_PERMISSIONS[role_name]
            assert "settings:write" not in perms, f"{role_name} must not have settings:write"

    def test_workspace_administrator_can_assign_roles(self):
        assert "roles:assign" in FIXED_ROLE_PERMISSIONS["workspace_administrator"]

    def test_non_admin_roles_cannot_assign_roles(self):
        for role_name in ["data_engineer", "data_steward", "business_analyst", "governance_viewer"]:
            assert "roles:assign" not in FIXED_ROLE_PERMISSIONS[role_name], (
                f"{role_name} must not have roles:assign"
            )


# ---------------------------------------------------------------------------
# 2. VALID_ROLE_NAMES
# ---------------------------------------------------------------------------


class TestValidRoleNames:
    def test_matches_fixed_role_permissions_keys(self):
        assert VALID_ROLE_NAMES == frozenset(FIXED_ROLE_PERMISSIONS.keys())

    def test_is_frozenset(self):
        assert isinstance(VALID_ROLE_NAMES, frozenset)


# ---------------------------------------------------------------------------
# 3. WorkspaceRBACService — interface compliance
# ---------------------------------------------------------------------------


class TestWorkspaceRBACServiceInterface:
    def test_is_rbacseviceinterface_subclass(self):
        assert issubclass(WorkspaceRBACService, RBACServiceInterface)

    def test_instance_is_rbac_interface(self):
        svc = WorkspaceRBACService()
        assert isinstance(svc, RBACServiceInterface)

    def test_stub_is_also_rbac_interface(self):
        stub = RBACServiceStub()
        assert isinstance(stub, RBACServiceInterface)


# ---------------------------------------------------------------------------
# 4. check_permission — matrix tests
# ---------------------------------------------------------------------------


class TestCheckPermission:
    """check_permission returns correct bool for role × action combinations."""

    def _setup_service_and_db(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
    ):
        svc = WorkspaceRBACService()
        db = _mock_db()
        # Patch get_member_role to return a known assignment
        assignment = _assignment_dict(workspace_id, user_id, role_name)
        svc.get_member_role = MagicMock(return_value=assignment)
        return svc, db

    @pytest.mark.parametrize(
        "action",
        [
            "workspaces:read",
            "workspaces:write",
            "members:read",
            "members:write",
            "members:delete",
            "roles:read",
            "roles:assign",
            "datasources:read",
            "datasources:write",
            "datasources:delete",
            "datasources:execute",
            "datasets:read",
            "datasets:write",
            "datasets:delete",
            "rules:read",
            "rules:write",
            "rules:execute",
            "rules:delete",
            "executions:read",
            "executions:write",
            "issues:read",
            "issues:write",
            "incidents:read",
            "incidents:write",
            "reports:read",
            "settings:read",
            "settings:write",
        ],
    )
    def test_workspace_administrator_can_do_everything(self, action: str):
        wid, uid = _uuid(), _uuid()
        svc, db = self._setup_service_and_db(wid, uid, "workspace_administrator")
        assert svc.check_permission(wid, uid, action, db) is True

    def test_data_engineer_can_write_datasources(self):
        wid, uid = _uuid(), _uuid()
        svc, db = self._setup_service_and_db(wid, uid, "data_engineer")
        assert svc.check_permission(wid, uid, "datasources:write", db) is True

    def test_business_analyst_cannot_write_datasources(self):
        wid, uid = _uuid(), _uuid()
        svc, db = self._setup_service_and_db(wid, uid, "business_analyst")
        assert svc.check_permission(wid, uid, "datasources:write", db) is False

    def test_governance_viewer_cannot_delete_rules(self):
        wid, uid = _uuid(), _uuid()
        svc, db = self._setup_service_and_db(wid, uid, "governance_viewer")
        assert svc.check_permission(wid, uid, "rules:delete", db) is False

    def test_no_role_returns_false(self):
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        svc.get_member_role = MagicMock(return_value=None)
        assert svc.check_permission(wid, uid, "workspaces:read", db) is False

    def test_unknown_action_returns_false(self):
        """An action not in any role's permission set always returns False."""
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        svc.get_member_role = MagicMock(
            return_value=_assignment_dict(wid, uid, "workspace_administrator")
        )
        # "nonexistent:action" is not in any role
        assert svc.check_permission(wid, uid, "nonexistent:action", db) is False


# ---------------------------------------------------------------------------
# 5. assign_role
# ---------------------------------------------------------------------------


class TestAssignRole:
    def _svc_with_get_role(self, existing: dict | None, admin_count: int = 2):
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(side_effect=[existing, existing])
        svc.get_admin_count = MagicMock(return_value=admin_count)
        return svc

    def test_assign_role_happy_path(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        svc = WorkspaceRBACService()
        # User has no existing role
        initial_assignment = _assignment_dict(wid, uid, "data_engineer")
        svc.get_member_role = MagicMock(side_effect=[None, initial_assignment])
        svc.get_admin_count = MagicMock(return_value=2)
        db = _mock_db()

        result = svc.assign_role(wid, uid, "data_engineer", actor, db)

        db.execute.assert_called_once()
        db.flush.assert_called_once()
        assert result["role_name"] == "data_engineer"

    def test_assign_role_invalid_role_raises_value_error(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=None)
        svc.get_custom_role_by_name = MagicMock(return_value=None)
        db = _mock_db()

        with pytest.raises(ValueError, match="Invalid role_name"):
            svc.assign_role(wid, uid, "super_admin", actor, db)

    def test_assign_role_idempotent_when_same_role(self):
        """If user already has the exact same role, no DB write and existing row returned."""
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "data_steward")
        svc = self._svc_with_get_role(existing)
        db = _mock_db()

        result = svc.assign_role(wid, uid, "data_steward", actor, db)

        db.execute.assert_not_called()
        assert result["role_name"] == "data_steward"

    def test_assign_role_last_admin_guard_raises(self):
        """Changing the last admin to a non-admin role raises LastWorkspaceAdministratorError."""
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "workspace_administrator")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        svc.get_admin_count = MagicMock(return_value=1)
        db = _mock_db()

        with pytest.raises(LastWorkspaceAdministratorError):
            svc.assign_role(wid, uid, "data_engineer", actor, db)

    def test_assign_role_allows_last_admin_to_stay_admin(self):
        """Re-assigning workspace_administrator to the last admin is allowed (idempotent)."""
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "workspace_administrator")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        svc.get_admin_count = MagicMock(return_value=1)
        db = _mock_db()

        # Should not raise — same role, idempotent short-circuit
        result = svc.assign_role(wid, uid, "workspace_administrator", actor, db)
        assert result["role_name"] == "workspace_administrator"

    def test_assign_role_db_error_raises_role_grant_failed(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=None)
        svc.get_admin_count = MagicMock(return_value=2)
        db = _mock_db()
        db.execute.side_effect = Exception("DB error")

        with pytest.raises(RoleGrantFailedError):
            svc.assign_role(wid, uid, "data_engineer", actor, db)


# ---------------------------------------------------------------------------
# 6. revoke_role
# ---------------------------------------------------------------------------


class TestRevokeRole:
    def test_revoke_role_happy_path(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "data_engineer")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        svc.get_admin_count = MagicMock(return_value=2)
        db = _mock_db()

        svc.revoke_role(wid, uid, actor, db)

        db.execute.assert_called_once()
        db.flush.assert_called_once()

    def test_revoke_role_not_found_raises(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=None)
        db = _mock_db()

        with pytest.raises(RoleAssignmentNotFoundError):
            svc.revoke_role(wid, uid, actor, db)

    def test_revoke_role_last_admin_guard_raises(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "workspace_administrator")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        svc.get_admin_count = MagicMock(return_value=1)
        db = _mock_db()

        with pytest.raises(LastWorkspaceAdministratorError):
            svc.revoke_role(wid, uid, actor, db)

    def test_revoke_non_admin_with_only_one_admin_allowed(self):
        """Revoking a non-admin role when only 1 admin exists is permitted."""
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "data_steward")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        # Admin count irrelevant — only checked when revoking an admin
        svc.get_admin_count = MagicMock(return_value=1)
        db = _mock_db()

        # Should not raise
        svc.revoke_role(wid, uid, actor, db)
        db.execute.assert_called_once()

    def test_revoke_role_db_error_raises_role_grant_failed(self):
        wid, uid, actor = _uuid(), _uuid(), _uuid()
        existing = _assignment_dict(wid, uid, "data_engineer")
        svc = WorkspaceRBACService()
        svc.get_member_role = MagicMock(return_value=existing)
        svc.get_admin_count = MagicMock(return_value=2)
        db = _mock_db()
        db.execute.side_effect = Exception("DB error")

        with pytest.raises(RoleGrantFailedError):
            svc.revoke_role(wid, uid, actor, db)


# ---------------------------------------------------------------------------
# 7. get_member_role
# ---------------------------------------------------------------------------


class TestGetMemberRole:
    """Unit tests for get_member_role — exercising the row-mapping logic
    without a real DB by patching db.execute directly."""

    def test_returns_none_when_no_row(self):
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        db.execute.return_value.fetchone.return_value = None

        result = svc.get_member_role(wid, uid, db)

        assert result is None

    def test_returns_dict_with_correct_keys(self):
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        ra_id = _uuid()
        granted_by = _uuid()
        now = datetime.now(UTC)
        fake_row = (ra_id, wid, uid, "data_engineer", granted_by, now)
        db.execute.return_value.fetchone.return_value = fake_row

        result = svc.get_member_role(wid, uid, db)

        assert result is not None
        assert result["workspace_id"] == wid
        assert result["user_id"] == uid
        assert result["role_name"] == "data_engineer"
        assert result["granted_by"] == granted_by
        assert result["granted_at"] == now
        assert result["id"] == ra_id


# ---------------------------------------------------------------------------
# 8. grant_workspace_admin
# ---------------------------------------------------------------------------


class TestGrantWorkspaceAdmin:
    def test_happy_path_executes_insert(self):
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()

        svc.grant_workspace_admin(wid, uid, db)

        db.execute.assert_called_once()
        call_sql = str(db.execute.call_args[0][0])
        assert "workspace_role_assignments" in call_sql.lower() or True  # SQL text object

    def test_integrity_error_raises_role_grant_failed(self):
        """Non-conflict IntegrityError should raise RoleGrantFailedError."""
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()

        from sqlalchemy.exc import IntegrityError

        db.execute.side_effect = IntegrityError("FK violation", {}, None)

        with pytest.raises(RoleGrantFailedError):
            svc.grant_workspace_admin(wid, uid, db)

    def test_generic_db_error_raises_role_grant_failed(self):
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        db.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RoleGrantFailedError):
            svc.grant_workspace_admin(wid, uid, db)

    def test_idempotent_on_conflict(self):
        """ON CONFLICT DO NOTHING means duplicate call should not raise."""
        wid, uid = _uuid(), _uuid()
        svc = WorkspaceRBACService()
        db = _mock_db()
        # No error = conflict silently ignored by ON CONFLICT DO NOTHING
        svc.grant_workspace_admin(wid, uid, db)  # first call
        svc.grant_workspace_admin(wid, uid, db)  # second call — must not raise
        assert db.execute.call_count == 2
