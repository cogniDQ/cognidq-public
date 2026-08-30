"""
F052 Entity Audit Hooks
=======================

Factory functions that build correctly-shaped ``AuditEntry`` instances for
each entity mutation.  These are called by endpoint handlers or service
methods **after** the mutation succeeds, before ``db.commit()``.

Each function validates its ``action_type`` and ``target_entity_type``
through ``AuditService.write()`` downstream — no duplicated validation here.

Usage at endpoint level::

    entry = build_rule_audit_entry(
        ctx=audit_ctx,
        action="rule_created",
        workspace_id=ws_id,
        rule_id=rule.id,
        after_state={"name": rule.name, ...},
    )
    audit_service.write(db, entry)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.audit.models import AuditContext, AuditEntry

# ---------------------------------------------------------------------------
# Rule hooks
# ---------------------------------------------------------------------------


def build_rule_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    rule_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a rule mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="rule",
        target_entity_id=rule_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Data source hooks
# ---------------------------------------------------------------------------


def build_data_source_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    data_source_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a data source mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="data_source",
        target_entity_id=data_source_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Dataset hooks
# ---------------------------------------------------------------------------


def build_dataset_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    dataset_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a dataset mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="dataset",
        target_entity_id=dataset_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Issue hooks
# ---------------------------------------------------------------------------


def build_issue_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    issue_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for an issue mutation.

    For auto-created issues, *ctx* should be ``AuditContext.for_system()``.
    """
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="issue",
        target_entity_id=issue_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Issue comment hooks (F036)
# ---------------------------------------------------------------------------


def build_comment_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    comment_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for an issue comment mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="issue_comment",
        target_entity_id=comment_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Incident hooks (F038)
# ---------------------------------------------------------------------------


def build_incident_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    incident_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for an incident mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="incident",
        target_entity_id=incident_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# RBAC hooks
# ---------------------------------------------------------------------------


def build_rbac_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID | None,
    user_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a role assignment/revocation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="role_assignment",
        target_entity_id=user_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Team hooks
# ---------------------------------------------------------------------------


def build_team_audit_entry(
    ctx: AuditContext,
    action: str,
    team_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
    workspace_id: UUID | None = None,
) -> AuditEntry:
    """Build audit entry for a team mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="team",
        target_entity_id=team_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


def build_team_membership_audit_entry(
    ctx: AuditContext,
    action: str,
    team_id: UUID,
    member_user_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
    workspace_id: UUID | None = None,
) -> AuditEntry:
    """Build audit entry for a team membership mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="team_membership",
        target_entity_id=member_user_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# User profile hooks
# ---------------------------------------------------------------------------


def build_user_profile_audit_entry(
    ctx: AuditContext,
    action: str,
    user_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a user profile mutation.

    The caller must ensure no sensitive fields (password_hash, etc.)
    appear in *before_state* or *after_state*.  The ``AuditService``
    strips them as a safety net, but the caller should pre-strip.
    """
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="user_profile",
        target_entity_id=user_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=None,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Flow hooks
# ---------------------------------------------------------------------------


def build_flow_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    flow_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a flow mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="flow",
        target_entity_id=flow_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Alert rule hooks (F043)
# ---------------------------------------------------------------------------


def build_alert_rule_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    alert_rule_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for an alert rule mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="alert_rule",
        target_entity_id=alert_rule_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


# ---------------------------------------------------------------------------
# Alert channel hooks (F044)
# ---------------------------------------------------------------------------


def build_alert_channel_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    alert_channel_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for an alert channel mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="alert_channel",
        target_entity_id=alert_channel_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )


def build_notification_event_audit_entry(
    ctx: AuditContext,
    action: str,
    workspace_id: UUID,
    notification_event_id: UUID,
    after_state: dict[str, Any],
    before_state: dict[str, Any] | None = None,
) -> AuditEntry:
    """Build audit entry for a notification event mutation."""
    return AuditEntry(
        tenant_id=ctx.tenant_id,
        action_type=action,
        target_entity_type="notification_event",
        target_entity_id=notification_event_id,
        after_state=after_state,
        actor_type=ctx.actor_type,
        actor_role=ctx.actor_role,
        workspace_id=workspace_id,
        actor_id=ctx.actor_id,
        before_state=before_state,
        request_id=ctx.request_id,
        source_ip=ctx.source_ip,
    )
