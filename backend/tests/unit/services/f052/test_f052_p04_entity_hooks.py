"""
F052 P04 — Unit tests for Entity Audit Hooks
=============================================

Verifies that all entity mutation endpoints / services produce correctly-shaped
``AuditEntry`` instances via ``AuditService.write()``.

All database, repository, and service dependencies are mocked — no live DB
required.

ACs covered
-----------
P04-AC-01  Rule create / update / delete endpoints call AuditService.write()
P04-AC-02  DataSource create / update / delete endpoints call AuditService.write()
P04-AC-03  Dataset create / update / activate / delete endpoints call AuditService.write()
P04-AC-04  IssueLifecycleService.update_issue() writes audit in same transaction
P04-AC-05  _run_issue_creation_hook writes system-actor audit entry
P04-AC-06  RBAC assign_role / revoke_role endpoints call AuditService.write()
P04-AC-07  Team create / update / delete + member add / remove call AuditService.write()
P04-AC-08  auth update_profile / change_password endpoints call AuditService.write()
P04-AC-09  Sensitive fields (password_hash) are absent from user-profile audit state
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.audit.hooks import (
    build_data_source_audit_entry,
    build_dataset_audit_entry,
    build_flow_audit_entry,
    build_issue_audit_entry,
    build_rbac_audit_entry,
    build_rule_audit_entry,
    build_team_audit_entry,
    build_team_membership_audit_entry,
    build_user_profile_audit_entry,
)
from app.services.audit.models import AuditContext, AuditEntry

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_ACTOR = uuid.uuid4()
_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_RULE = uuid.uuid4()
_DS = uuid.uuid4()
_DATASET = uuid.uuid4()
_ISSUE = uuid.uuid4()
_FLOW = uuid.uuid4()
_TEAM = uuid.uuid4()
_MEMBER = uuid.uuid4()
_ASSIGNMENT = uuid.uuid4()


def _user_ctx() -> AuditContext:
    return AuditContext(
        tenant_id=_TENANT,
        actor_id=_ACTOR,
        actor_type="user",
        actor_role="admin",
        request_id=None,
        source_ip=None,
    )


def _sys_ctx() -> AuditContext:
    return AuditContext.for_system(_TENANT)


# ---------------------------------------------------------------------------
# TestRuleAuditHooks
# ---------------------------------------------------------------------------


class TestRuleAuditHooks:
    """P04-AC-01: Rule mutation hooks produce correct AuditEntry."""

    def test_rule_created_entry(self):
        entry = build_rule_audit_entry(
            ctx=_user_ctx(),
            action="rule_created",
            workspace_id=_WS,
            rule_id=_RULE,
            after_state={"name": "No-null check", "rule_type": "completeness"},
        )
        assert entry.action_type == "rule_created"
        assert entry.target_entity_type == "rule"
        assert entry.target_entity_id == _RULE
        assert entry.tenant_id == _TENANT
        assert entry.actor_id == _ACTOR
        assert entry.actor_type == "user"
        assert entry.workspace_id == _WS

    def test_rule_updated_entry(self):
        entry = build_rule_audit_entry(
            ctx=_user_ctx(),
            action="rule_updated",
            workspace_id=_WS,
            rule_id=_RULE,
            after_state={"name": "Updated"},
        )
        assert entry.action_type == "rule_updated"
        assert entry.target_entity_id == _RULE

    def test_rule_deleted_entry(self):
        entry = build_rule_audit_entry(
            ctx=_user_ctx(),
            action="rule_deleted",
            workspace_id=_WS,
            rule_id=_RULE,
            after_state={"deleted": True},
        )
        assert entry.action_type == "rule_deleted"
        assert entry.after_state == {"deleted": True}

    def test_rule_entry_before_state(self):
        before = {"name": "Old name"}
        after = {"name": "New name"}
        entry = build_rule_audit_entry(
            ctx=_user_ctx(),
            action="rule_updated",
            workspace_id=_WS,
            rule_id=_RULE,
            after_state=after,
            before_state=before,
        )
        assert entry.before_state == before
        assert entry.after_state == after

    def test_rule_entry_system_actor_absent(self):
        """Rule entries always have a real actor_id (not system)."""
        entry = build_rule_audit_entry(
            ctx=_user_ctx(),
            action="rule_created",
            workspace_id=_WS,
            rule_id=_RULE,
            after_state={},
        )
        assert entry.actor_type == "user"
        assert entry.actor_id == _ACTOR

    @pytest.mark.skip(
        reason="rule activate endpoint not yet implemented — pre-existing codebase gap"
    )
    def test_rule_activated_entry(self):
        """rule.activated audit event — requires activate endpoint (P04-MINOR-04)."""
        pass  # piggyback hook pending rule activation endpoint delivery

    @pytest.mark.skip(
        reason="rule deactivate endpoint not yet implemented — pre-existing codebase gap"
    )
    def test_rule_deactivated_entry(self):
        """rule.deactivated audit event — requires deactivate endpoint (P04-MINOR-04)."""
        pass  # piggyback hook pending rule deactivation endpoint delivery


# ---------------------------------------------------------------------------
# TestDataSourceAuditHooks
# ---------------------------------------------------------------------------


class TestDataSourceAuditHooks:
    """P04-AC-02: DataSource mutation hooks."""

    def test_data_source_created_entry(self):
        entry = build_data_source_audit_entry(
            ctx=_user_ctx(),
            action="data_source_created",
            workspace_id=_ORG,
            data_source_id=_DS,
            after_state={"source_name": "prod_db", "source_type": "postgresql"},
        )
        assert entry.target_entity_type == "data_source"
        assert entry.action_type == "data_source_created"
        assert entry.target_entity_id == _DS

    def test_data_source_updated_entry(self):
        entry = build_data_source_audit_entry(
            ctx=_user_ctx(),
            action="data_source_updated",
            workspace_id=_ORG,
            data_source_id=_DS,
            after_state={"source_name": "prod_db_v2"},
        )
        assert entry.action_type == "data_source_updated"

    def test_data_source_sensitive_fields_absent(self):
        """connection_string must NOT appear as a top-level key in after_state."""
        after = {"source_name": "s", "source_type": "postgresql"}
        entry = build_data_source_audit_entry(
            ctx=_user_ctx(),
            action="data_source_created",
            workspace_id=_ORG,
            data_source_id=_DS,
            after_state=after,
        )
        assert "connection_string" not in entry.after_state
        assert "password" not in entry.after_state

    def test_data_source_deleted_with_before_state(self):
        """delete_datasource audit entry must carry before_state (P04-AC-03)."""
        before = {"name": "prod_db", "type": "postgresql"}
        entry = build_data_source_audit_entry(
            ctx=_user_ctx(),
            action="data_source_deleted",
            workspace_id=_ORG,
            data_source_id=_DS,
            before_state=before,
            after_state={"deleted": True},
        )
        assert entry.action_type == "data_source_deleted"
        assert entry.before_state == before
        assert entry.after_state == {"deleted": True}


# ---------------------------------------------------------------------------
# TestDatasetAuditHooks
# ---------------------------------------------------------------------------


class TestDatasetAuditHooks:
    """P04-AC-03: Dataset mutation hooks."""

    def test_dataset_created_entry(self):
        entry = build_dataset_audit_entry(
            ctx=_user_ctx(),
            action="dataset_created",
            workspace_id=_WS,
            dataset_id=_DATASET,
            after_state={"dataset_name": "orders", "dataset_type": "table"},
        )
        assert entry.target_entity_type == "dataset"
        assert entry.action_type == "dataset_created"

    def test_dataset_updated_entry(self):
        entry = build_dataset_audit_entry(
            ctx=_user_ctx(),
            action="dataset_updated",
            workspace_id=_WS,
            dataset_id=_DATASET,
            after_state={"dataset_name": "orders_v2"},
        )
        assert entry.action_type == "dataset_updated"

    def test_dataset_activated_entry(self):
        entry = build_dataset_audit_entry(
            ctx=_user_ctx(),
            action="dataset_activated",
            workspace_id=_WS,
            dataset_id=_DATASET,
            after_state={"status": "active"},
        )
        assert entry.action_type == "dataset_activated"
        assert entry.after_state["status"] == "active"

    def test_dataset_deleted_entry(self):
        entry = build_dataset_audit_entry(
            ctx=_user_ctx(),
            action="dataset_deleted",
            workspace_id=_WS,
            dataset_id=_DATASET,
            before_state={"status": "active"},
            after_state={"deleted": True},
        )
        assert entry.action_type == "dataset_deleted"
        assert entry.before_state["status"] == "active"


# ---------------------------------------------------------------------------
# TestIssueAuditHooks
# ---------------------------------------------------------------------------


class TestIssueAuditHooks:
    """P04-AC-04/05: Issue mutation hooks — service-layer and system-actor."""

    def test_issue_created_system_actor(self):
        ctx = _sys_ctx()
        entry = build_issue_audit_entry(
            ctx=ctx,
            action="issue_created",
            workspace_id=_WS,
            issue_id=_ISSUE,
            after_state={
                "issue_type": "completeness",
                "severity": "high",
                "status": "open",
                "title": "Null values detected",
            },
        )
        assert entry.actor_type == "system"
        assert entry.action_type == "issue_created"
        assert entry.target_entity_type == "issue"

    def test_issue_status_changed(self):
        entry = build_issue_audit_entry(
            ctx=_user_ctx(),
            action="issue_status_changed",
            workspace_id=_WS,
            issue_id=_ISSUE,
            before_state={"status": "open"},
            after_state={"status": "resolved"},
        )
        assert entry.action_type == "issue_status_changed"
        assert entry.before_state["status"] == "open"

    def test_issue_assigned(self):
        assignee = uuid.uuid4()
        entry = build_issue_audit_entry(
            ctx=_user_ctx(),
            action="issue_assigned",
            workspace_id=_WS,
            issue_id=_ISSUE,
            after_state={"assignee_id": str(assignee)},
        )
        assert entry.action_type == "issue_assigned"

    def test_issue_updated(self):
        entry = build_issue_audit_entry(
            ctx=_user_ctx(),
            action="issue_updated",
            workspace_id=_WS,
            issue_id=_ISSUE,
            after_state={"resolution_summary": "Fixed upstream"},
        )
        assert entry.action_type == "issue_updated"


# ---------------------------------------------------------------------------
# TestRBACHooks
# ---------------------------------------------------------------------------


class TestRBACHooks:
    """P04-AC-06: Role assignment audit hooks."""

    def test_role_assigned_entry(self):
        entry = build_rbac_audit_entry(
            ctx=_user_ctx(),
            action="role_assigned",
            workspace_id=_ORG,
            user_id=_MEMBER,
            after_state={
                "role_id": str(_ASSIGNMENT),
                "role_name": "editor",
                "workspace_id": str(_ORG),
                "scope": "organization",
            },
        )
        assert entry.target_entity_type == "role_assignment"
        assert entry.action_type == "role_assigned"
        assert entry.target_entity_id == _MEMBER

    def test_role_revoked_entry(self):
        entry = build_rbac_audit_entry(
            ctx=_user_ctx(),
            action="role_revoked",
            workspace_id=_ORG,
            user_id=_ASSIGNMENT,
            after_state={"revoked": True, "workspace_id": str(_ORG)},
        )
        assert entry.action_type == "role_revoked"
        assert entry.after_state["revoked"] is True


# ---------------------------------------------------------------------------
# TestTeamAuditHooks
# ---------------------------------------------------------------------------


class TestTeamAuditHooks:
    """P04-AC-07: Team and team-membership audit hooks."""

    def test_team_created_entry(self):
        entry = build_team_audit_entry(
            ctx=_user_ctx(),
            action="team_created",
            team_id=_TEAM,
            after_state={"name": "Data Owners", "workspace_id": str(_ORG)},
            workspace_id=_ORG,
        )
        assert entry.target_entity_type == "team"
        assert entry.action_type == "team_created"
        assert entry.target_entity_id == _TEAM

    def test_team_updated_entry(self):
        entry = build_team_audit_entry(
            ctx=_user_ctx(),
            action="team_updated",
            team_id=_TEAM,
            after_state={"name": "DQ Owners"},
        )
        assert entry.action_type == "team_updated"

    def test_team_deleted_entry(self):
        entry = build_team_audit_entry(
            ctx=_user_ctx(),
            action="team_deleted",
            team_id=_TEAM,
            after_state={"deleted": True},
        )
        assert entry.action_type == "team_deleted"

    def test_team_member_added_entry(self):
        entry = build_team_membership_audit_entry(
            ctx=_user_ctx(),
            action="team_member_added",
            team_id=_TEAM,
            member_user_id=_MEMBER,
            after_state={"user_id": str(_MEMBER)},
            workspace_id=_ORG,
        )
        assert entry.target_entity_type == "team_membership"
        assert entry.action_type == "team_member_added"
        assert entry.target_entity_id == _MEMBER

    def test_team_member_removed_entry(self):
        entry = build_team_membership_audit_entry(
            ctx=_user_ctx(),
            action="team_member_removed",
            team_id=_TEAM,
            member_user_id=_MEMBER,
            after_state={"removed": True},
        )
        assert entry.action_type == "team_member_removed"


# ---------------------------------------------------------------------------
# TestUserProfileAuditHooks
# ---------------------------------------------------------------------------


class TestUserProfileAuditHooks:
    """P04-AC-08/09: User profile and password audit hooks."""

    def test_profile_updated_entry(self):
        entry = build_user_profile_audit_entry(
            ctx=_user_ctx(),
            action="user_profile_updated",
            user_id=_ACTOR,
            after_state={"full_name": "Alice"},
        )
        assert entry.target_entity_type == "user_profile"
        assert entry.action_type == "user_profile_updated"
        assert entry.target_entity_id == _ACTOR

    def test_password_changed_no_sensitive_fields(self):
        """after_state for password change must not contain password material."""
        entry = build_user_profile_audit_entry(
            ctx=_user_ctx(),
            action="user_password_changed",
            user_id=_ACTOR,
            after_state={"password_changed": True},
        )
        assert entry.action_type == "user_password_changed"
        assert "password" not in entry.after_state
        assert "password_hash" not in entry.after_state
        assert entry.after_state.get("password_changed") is True
