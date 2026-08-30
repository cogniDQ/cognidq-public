"""
F052 Audit Constants
====================

Frozen sets of valid action types, entity types, and sensitive field names
that must be stripped from audit entry state snapshots.
"""

from __future__ import annotations

VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "tenant",
        "workspace",
        "data_source",
        "dataset",
        "rule",
        "flow",
        "issue",
        "issue_comment",
        "incident",
        "alert_rule",
        "alert_channel",
        "notification_event",
        "role_assignment",
        "team",
        "team_membership",
        "user_profile",
    }
)

VALID_ACTION_TYPES: frozenset[str] = frozenset(
    {
        # Tenant
        "tenant_created",
        "tenant_updated",
        "tenant_suspended",
        "tenant_reactivated",
        # Workspace (F002 existing + F003)
        "workspace_created",
        "workspace_metadata_updated",
        "workspace_archived",
        "workspace_restored",
        "workspace_settings_updated",
        # Data source
        "data_source_created",
        "data_source_updated",
        "data_source_deleted",
        # Dataset
        "dataset_created",
        "dataset_updated",
        "dataset_activated",
        "dataset_deleted",
        # Rule
        "rule_created",
        "rule_updated",
        "rule_deleted",
        "rule_activated",
        "rule_deactivated",
        "rule_owner_changed",
        # Flow
        "flow_created",
        "flow_updated",
        "flow_deleted",
        "flow_owner_changed",
        # Issue
        "issue_created",
        "issue_status_changed",
        "issue_assigned",
        "issue_updated",
        # Issue comment (F036)
        "issue_comment_added",
        # Incident (F038)
        "incident_created",
        # Incident lifecycle (F040)
        "incident_status_changed",
        "incident_owner_changed",
        "incident_assigned",
        "incident_updated",
        # Incident links (F041)
        "incident_links_added",
        "incident_links_removed",
        # Alert rule (F043)
        "alert_rule_created",
        "alert_rule_updated",
        "alert_rule_deleted",
        # Alert channel (F044)
        "alert_channel_created",
        "alert_channel_updated",
        "alert_channel_deleted",
        # Notification event (F045)
        "notification_event_created",
        "notification_event_status_updated",
        # RBAC
        "role_assigned",
        "role_revoked",
        # Team
        "team_created",
        "team_updated",
        "team_deleted",
        "team_member_added",
        "team_member_updated",
        "team_member_removed",
        # User
        "user_profile_updated",
        "user_password_changed",
    }
)

SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "hashed_password",
        "connection_string",
        "credentials",
        "secret",
        "api_key",
        "token",
    }
)
