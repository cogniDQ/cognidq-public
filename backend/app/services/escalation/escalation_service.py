"""
F046 — Escalation for Overdue SLA
===================================

Core service that scans for overdue open issues across all workspaces and
logs NotificationEvent records for each matching ``issue_overdue`` alert rule.

Usage (from Celery task or API endpoint):
    from app.services.escalation.escalation_service import EscalationService
    with SessionLocal() as db:
        result = EscalationService().run_escalation_check(db)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.alert_channel import AlertChannel
from app.models.alert_rule import AlertRule
from app.models.issue import Issue
from app.models.notification_event import NotificationEvent

logger = logging.getLogger(__name__)

# Statuses that are still "open" and can be overdue
_OPEN_STATUSES = ("open", "in_progress", "reopened")


class EscalationResult:
    """Summary returned by a single escalation check run."""

    def __init__(self) -> None:
        self.overdue_issues_found: int = 0
        self.workspaces_affected: int = 0
        self.rules_matched: int = 0
        self.notifications_logged: int = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "overdue_issues_found": self.overdue_issues_found,
            "workspaces_affected": self.workspaces_affected,
            "rules_matched": self.rules_matched,
            "notifications_logged": self.notifications_logged,
            "errors": self.errors,
        }


class EscalationService:
    """Scans for overdue issues and emits notification events."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_escalation_check(self, db: Session) -> EscalationResult:
        """
        Single pass of the escalation scanner.

        Steps:
        1. Find all issues where due_at < now() and status in open statuses.
        2. Collect the distinct workspace_ids affected.
        3. For each workspace, load enabled ``issue_overdue`` alert rules
           with at least one configured channel.
        4. For each rule×channel combination, log a NotificationEvent.
        """
        result = EscalationResult()
        now = datetime.now(tz=UTC)

        try:
            overdue_issues = self._find_overdue_issues(db, now)
            result.overdue_issues_found = len(overdue_issues)

            if not overdue_issues:
                logger.info("F046 escalation check: no overdue issues found")
                return result

            # Group by workspace
            workspace_ids: set[UUID] = {issue.workspace_id for issue in overdue_issues}
            result.workspaces_affected = len(workspace_ids)

            for workspace_id in workspace_ids:
                ws_issues = [i for i in overdue_issues if i.workspace_id == workspace_id]
                try:
                    n_logged = self._process_workspace(db, workspace_id, ws_issues, now, result)
                    result.notifications_logged += n_logged
                except Exception as exc:
                    msg = f"workspace {workspace_id}: {exc}"
                    logger.error("F046 escalation error — %s", msg, exc_info=True)
                    result.errors.append(msg)

            db.commit()
            logger.info("F046 escalation check complete: %s", result.to_dict())

        except Exception as exc:
            logger.error("F046 escalation check failed: %s", exc, exc_info=True)
            result.errors.append(str(exc))
            try:
                db.rollback()
            except Exception:
                pass

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_overdue_issues(db: Session, now: datetime) -> list:
        """Return all open issues whose due_at is in the past."""
        return (
            db.query(Issue)
            .filter(
                and_(
                    Issue.status.in_(_OPEN_STATUSES),
                    Issue.due_at.isnot(None),
                    Issue.due_at < now,
                )
            )
            .all()
        )

    @staticmethod
    def _find_issue_overdue_rules(db: Session, workspace_id: UUID) -> list:
        """Return enabled ``issue_overdue`` alert rules for a workspace."""
        return (
            db.query(AlertRule)
            .filter(
                and_(
                    AlertRule.workspace_id == workspace_id,
                    AlertRule.trigger_type == "issue_overdue",
                    AlertRule.enabled.is_(True),
                )
            )
            .all()
        )

    @staticmethod
    def _find_enabled_channels(db: Session, workspace_id: UUID, channel_ids: list) -> list:
        """Return enabled AlertChannel objects for the given IDs."""
        if not channel_ids:
            return []
        return (
            db.query(AlertChannel)
            .filter(
                and_(
                    AlertChannel.workspace_id == workspace_id,
                    AlertChannel.id.in_(channel_ids),
                    AlertChannel.enabled.is_(True),
                )
            )
            .all()
        )

    def _process_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        ws_issues: list,
        now: datetime,
        result: EscalationResult,
    ) -> int:
        """Process one workspace — returns count of notification events logged."""
        rules = self._find_issue_overdue_rules(db, workspace_id)
        if not rules:
            return 0

        result.rules_matched += len(rules)
        n_logged = 0

        # Build a compact issue summary for the notification payload
        issue_summary = [
            {
                "id": str(issue.id),
                "title": issue.title,
                "severity": issue.severity,
                "status": issue.status,
                "due_at": issue.due_at.isoformat() if issue.due_at else None,
            }
            for issue in ws_issues
        ]

        for rule in rules:
            # Resolve channels attached to the rule (channel_ids is JSONB list of UUIDs)
            raw_channel_ids = rule.channel_ids or []
            try:
                channel_ids = [UUID(str(cid)) for cid in raw_channel_ids]
            except Exception:
                channel_ids = []

            channels = self._find_enabled_channels(db, workspace_id, channel_ids)

            # Fallback: if no channels are configured, still log one event with
            # the first recipient_user_id so the event is visible.
            if not channels:
                recipients = list(rule.recipient_user_ids or [])
                if recipients:
                    n_logged += self._log_event(
                        db,
                        workspace_id=workspace_id,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        channel_id=None,
                        recipient=str(recipients[0]),
                        issue_summary=issue_summary,
                        now=now,
                    )
                continue

            for channel in channels:
                # Use the channel email/url as recipient identifier
                recipient = self._extract_recipient(channel)
                n_logged += self._log_event(
                    db,
                    workspace_id=workspace_id,
                    tenant_id=rule.tenant_id,
                    rule=rule,
                    channel_id=channel.id,
                    recipient=recipient,
                    issue_summary=issue_summary,
                    now=now,
                )

        return n_logged

    @staticmethod
    def _extract_recipient(channel: AlertChannel) -> str:
        """Extract a human-readable recipient from channel configuration."""
        cfg = channel.configuration or {}
        return cfg.get("email") or cfg.get("url") or cfg.get("webhook_url") or str(channel.id)

    @staticmethod
    def _log_event(
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        rule: AlertRule,
        channel_id,
        recipient: str,
        issue_summary: list,
        now: datetime,
    ) -> int:
        """Insert a NotificationEvent row. Returns 1 on success, 0 on failure."""
        # Use a sentinel channel_id when no real channel is linked
        _channel_id = channel_id if channel_id is not None else rule.id

        try:
            event = NotificationEvent(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                alert_rule_id=rule.id,
                alert_channel_id=_channel_id,
                recipient=recipient[:500],
                status="pending",
                payload={
                    "trigger": "issue_overdue",
                    "checked_at": now.isoformat(),
                    "overdue_count": len(issue_summary),
                    "issues": issue_summary,
                },
                retry_count=0,
                max_retries=3,
            )
            db.add(event)
            db.flush()
            return 1
        except Exception as exc:
            logger.error(
                "F046 failed to log notification event rule=%s: %s",
                rule.id,
                exc,
                exc_info=True,
            )
            db.rollback()
            return 0
