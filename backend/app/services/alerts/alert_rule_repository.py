"""
F043 Alert Rule Repository
===========================

Data-access layer for AlertRule ORM objects.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.alert_rule import AlertRule


class AlertRuleRepository:
    """CRUD operations for the alert_rules table."""

    # -- write ----------------------------------------------------------------

    def insert(self, db: Session, rule: AlertRule) -> AlertRule:
        """Persist a new alert rule and flush to populate server defaults."""
        db.add(rule)
        db.flush()
        return rule

    def update(self, db: Session, rule: AlertRule) -> AlertRule:
        """Flush pending changes on *rule* and refresh."""
        db.flush()
        db.refresh(rule)
        return rule

    def delete(self, db: Session, rule_id: UUID, workspace_id: UUID) -> bool:
        """Delete an alert rule. Returns True if found and deleted."""
        rule = self.get_by_id_and_workspace(db, rule_id, workspace_id)
        if rule is None:
            return False
        db.delete(rule)
        db.flush()
        return True

    # -- read -----------------------------------------------------------------

    def get_by_id_and_workspace(
        self,
        db: Session,
        rule_id: UUID,
        workspace_id: UUID,
    ) -> AlertRule | None:
        """Fetch a single alert rule by PK + workspace scope, or None."""
        return (
            db.query(AlertRule)
            .filter(AlertRule.id == rule_id, AlertRule.workspace_id == workspace_id)
            .first()
        )

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        enabled_only: bool = False,
    ) -> list[AlertRule]:
        """Return all alert rules in a workspace, optionally filtered."""
        q = db.query(AlertRule).filter(AlertRule.workspace_id == workspace_id)
        if enabled_only:
            q = q.filter(AlertRule.enabled.is_(True))
        return q.order_by(AlertRule.created_at.desc()).all()

    def name_exists(
        self,
        db: Session,
        workspace_id: UUID,
        name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Check whether *name* is already used in *workspace_id*."""
        q = db.query(AlertRule.id).filter(
            AlertRule.workspace_id == workspace_id,
            AlertRule.name == name,
        )
        if exclude_id is not None:
            q = q.filter(AlertRule.id != exclude_id)
        return q.first() is not None

    def count_by_workspace(self, db: Session, workspace_id: UUID) -> int:
        """Return total alert rules in a workspace."""
        return db.query(AlertRule).filter(AlertRule.workspace_id == workspace_id).count()
