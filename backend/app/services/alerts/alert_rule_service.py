"""
F043 Alert Rule Service
========================

CRUD operations for alert rules with validation and audit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.alert_rule import AlertRule
from app.services.alerts.alert_rule_models import AlertRuleResponse
from app.services.alerts.alert_rule_repository import AlertRuleRepository
from app.services.audit.hooks import build_alert_rule_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TRIGGER_TYPES = frozenset(
    {
        "execution_failed",
        "execution_completed",
        "rule_failed",  # F10
        "check_failed",  # F10
        "issue_created",
        "issue_overdue",
        "incident_created",
        "incident_status_changed",
    }
)

MAX_RULES_PER_WORKSPACE = 50


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AlertRuleValidationError(Exception):
    """Raised when alert rule input fails validation."""


class AlertRuleNotFoundError(Exception):
    """Raised when an alert rule is not found in the workspace."""


class DuplicateAlertRuleNameError(Exception):
    """Raised when the name already exists in the workspace."""


class AlertRuleLimitError(Exception):
    """Raised when the workspace exceeds the alert rule limit."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AlertRuleService:
    """CRUD for alert rules."""

    def __init__(
        self,
        repo: AlertRuleRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or AlertRuleRepository()
        self._audit = audit_service or AuditService()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _to_response(rule: AlertRule) -> AlertRuleResponse:
        return AlertRuleResponse(
            id=rule.id,
            workspace_id=rule.workspace_id,
            name=rule.name,
            trigger_type=rule.trigger_type,
            conditions=rule.conditions,
            recipient_user_ids=rule.recipient_user_ids or [],
            channel_ids=[str(c) for c in (rule.channel_ids or [])],
            enabled=rule.enabled,
            created_by_user_id=rule.created_by_user_id,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    # -- create ---------------------------------------------------------------

    def create_rule(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        created_by_user_id: UUID,
        name: str,
        trigger_type: str,
        conditions: dict | None = None,
        recipient_user_ids: list[str],
        channel_ids: list[str] | None = None,
        enabled: bool = True,
        audit_ctx: AuditContext | None = None,
    ) -> AlertRuleResponse:
        # --- 1. Validate ---
        name = (name or "").strip()
        if not name or len(name) > 200:
            raise AlertRuleValidationError("name must be 1–200 characters")
        if trigger_type not in VALID_TRIGGER_TYPES:
            raise AlertRuleValidationError(f"invalid trigger_type: {trigger_type}")
        if not recipient_user_ids:
            raise AlertRuleValidationError("recipient_user_ids must not be empty")

        # --- 2. Check uniqueness ---
        if self._repo.name_exists(db, workspace_id, name):
            raise DuplicateAlertRuleNameError(f"name already exists: {name}")

        # --- 3. Check limit ---
        if self._repo.count_by_workspace(db, workspace_id) >= MAX_RULES_PER_WORKSPACE:
            raise AlertRuleLimitError(f"workspace exceeds {MAX_RULES_PER_WORKSPACE} alert rules")

        # --- 4. Persist ---
        rule = AlertRule(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            trigger_type=trigger_type,
            conditions=conditions,
            recipient_user_ids=recipient_user_ids,
            channel_ids=[str(c) for c in (channel_ids or [])] or None,
            enabled=enabled,
            created_by_user_id=created_by_user_id,
        )
        rule = self._repo.insert(db, rule)

        # --- 5. Audit ---
        if audit_ctx is not None:
            entry = build_alert_rule_audit_entry(
                ctx=audit_ctx,
                action="alert_rule_created",
                workspace_id=workspace_id,
                alert_rule_id=rule.id,
                after_state={
                    "name": name,
                    "trigger_type": trigger_type,
                    "enabled": enabled,
                },
            )
            self._audit.write(db, entry)

        return self._to_response(rule)

    # -- read -----------------------------------------------------------------

    def get_rule(
        self,
        db: Session,
        *,
        rule_id: UUID,
        workspace_id: UUID,
    ) -> AlertRuleResponse:
        rule = self._repo.get_by_id_and_workspace(db, rule_id, workspace_id)
        if rule is None:
            raise AlertRuleNotFoundError(f"alert rule {rule_id} not found")
        return self._to_response(rule)

    def list_rules(
        self,
        db: Session,
        *,
        workspace_id: UUID,
    ) -> list[AlertRuleResponse]:
        rules = self._repo.list_by_workspace(db, workspace_id)
        return [self._to_response(r) for r in rules]

    # -- update ---------------------------------------------------------------

    def update_rule(
        self,
        db: Session,
        *,
        rule_id: UUID,
        workspace_id: UUID,
        audit_ctx: AuditContext | None = None,
        name: str | None = None,
        trigger_type: str | None = None,
        conditions: dict | None = None,
        recipient_user_ids: list[str] | None = None,
        enabled: bool | None = None,
    ) -> AlertRuleResponse:
        rule = self._repo.get_by_id_and_workspace(db, rule_id, workspace_id)
        if rule is None:
            raise AlertRuleNotFoundError(f"alert rule {rule_id} not found")

        # Validate fields if provided
        if name is not None:
            name = name.strip()
            if not name or len(name) > 200:
                raise AlertRuleValidationError("name must be 1–200 characters")
            if self._repo.name_exists(db, workspace_id, name, exclude_id=rule_id):
                raise DuplicateAlertRuleNameError(f"name already exists: {name}")
            rule.name = name

        if trigger_type is not None:
            if trigger_type not in VALID_TRIGGER_TYPES:
                raise AlertRuleValidationError(f"invalid trigger_type: {trigger_type}")
            rule.trigger_type = trigger_type

        if conditions is not None:
            rule.conditions = conditions

        if recipient_user_ids is not None:
            if not recipient_user_ids:
                raise AlertRuleValidationError("recipient_user_ids must not be empty")
            rule.recipient_user_ids = recipient_user_ids

        if enabled is not None:
            rule.enabled = enabled

        rule = self._repo.update(db, rule)

        # Audit
        if audit_ctx is not None:
            entry = build_alert_rule_audit_entry(
                ctx=audit_ctx,
                action="alert_rule_updated",
                workspace_id=workspace_id,
                alert_rule_id=rule.id,
                after_state={
                    "name": rule.name,
                    "trigger_type": rule.trigger_type,
                    "enabled": rule.enabled,
                },
            )
            self._audit.write(db, entry)

        return self._to_response(rule)

    # -- delete ---------------------------------------------------------------

    def delete_rule(
        self,
        db: Session,
        *,
        rule_id: UUID,
        workspace_id: UUID,
        audit_ctx: AuditContext | None = None,
    ) -> None:
        rule = self._repo.get_by_id_and_workspace(db, rule_id, workspace_id)
        if rule is None:
            raise AlertRuleNotFoundError(f"alert rule {rule_id} not found")

        # Audit before deletion
        if audit_ctx is not None:
            entry = build_alert_rule_audit_entry(
                ctx=audit_ctx,
                action="alert_rule_deleted",
                workspace_id=workspace_id,
                alert_rule_id=rule.id,
                after_state={"name": rule.name},
            )
            self._audit.write(db, entry)

        self._repo.delete(db, rule_id, workspace_id)
