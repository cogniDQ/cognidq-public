"""
Alert Trigger Service
======================

Centralized fan-out from lifecycle events (execution failed, issue created,
incident created, incident status changed, incident assigned, …) to the alert
pipeline. Resolves matching enabled rules, expands recipients (user_ids +
roles), and logs one ``NotificationEvent`` per (rule, channel, recipient)
tuple. Delivery itself is handled asynchronously by
``NotificationDispatcher.dispatch_pending`` (see notification dispatcher and
the periodic ``notification.dispatch_pending`` Celery task).

This module is the *only* code path that creates notification events from
business logic. Lifecycle services should not query alert rules directly.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.alert_channel import AlertChannel
from app.models.alert_rule import AlertRule
from app.models.user import User
from app.services.audit.models import AuditContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper — extract a string list out of JSONB columns that may contain
# either UUIDs/strings already, or list-of-dicts.
# ---------------------------------------------------------------------------


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            if v is None:
                continue
            out.append(str(v))
        return out
    return [str(value)]


# ---------------------------------------------------------------------------
# Conditions matching
# ---------------------------------------------------------------------------


def _conditions_match(conditions: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    """Lightweight rule-level filter.

    Supports the shape ``{"field": value}`` or ``{"field": {"in": [...]}}``.
    Empty / ``None`` conditions match everything.
    """
    if not conditions:
        return True
    for key, expected in conditions.items():
        actual = payload.get(key)
        if isinstance(expected, dict):
            if "in" in expected:
                if actual not in (expected.get("in") or []):
                    return False
                continue
            if "eq" in expected:
                if actual != expected["eq"]:
                    return False
                continue
            if "ne" in expected:
                if actual == expected["ne"]:
                    return False
                continue
            # Unknown operator – conservative: do not match.
            return False
        elif isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True


# ---------------------------------------------------------------------------
# AlertTriggerService
# ---------------------------------------------------------------------------


class AlertTriggerService:
    """Resolve matching rules → recipients → emit NotificationEvent rows."""

    @staticmethod
    def _resolve_tenant_id(db: Session, workspace_id: UUID) -> UUID | None:
        """Look up the owning tenant for *workspace_id*.

        Uses a raw SQL fallback because the ``Workspace`` ORM model may not be
        importable from every call site without circular imports.
        """
        try:
            from sqlalchemy import text

            row = db.execute(
                text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid"),
                {"wid": str(workspace_id)},
            ).first()
            if row and row[0]:
                return UUID(str(row[0]))
        except Exception as exc:  # noqa: BLE001
            logger.debug("AlertTriggerService: tenant lookup failed: %s", exc)
        return None

    def trigger_for_workspace(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        trigger_type: str,
        payload: dict[str, Any],
        audit_ctx: AuditContext | None = None,
    ) -> int:
        """Convenience wrapper that resolves ``tenant_id`` from the workspace."""
        tenant_id: UUID | None = audit_ctx.tenant_id if audit_ctx is not None else None
        if tenant_id is None:
            tenant_id = self._resolve_tenant_id(db, workspace_id)
        if tenant_id is None:
            logger.warning(
                "AlertTriggerService: cannot resolve tenant_id for workspace %s; skipping",
                workspace_id,
            )
            return 0
        return self.trigger(
            db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            payload=payload,
            audit_ctx=audit_ctx,
        )

    def trigger(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        trigger_type: str,
        payload: dict[str, Any],
        audit_ctx: AuditContext | None = None,
    ) -> int:
        """Fire all enabled alert rules whose ``trigger_type`` matches.

        Returns the number of NotificationEvents created. Never raises on
        per-rule errors — failures are logged and skipped so the originating
        business action is never blocked by alerting.
        """
        try:
            rules = (
                db.query(AlertRule)
                .filter(
                    AlertRule.workspace_id == workspace_id,
                    AlertRule.trigger_type == trigger_type,
                    AlertRule.enabled.is_(True),
                )
                .all()
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("AlertTriggerService: failed to load rules: %s", exc, exc_info=True)
            return 0

        if not rules:
            return 0

        from app.services.alerts.notification_event_service import NotificationEventService

        evt_service = NotificationEventService()

        n_logged = 0
        for rule in rules:
            try:
                if not _conditions_match(rule.conditions, payload):
                    continue
                channel_ids = self._resolve_channel_ids(db, rule, workspace_id)
                if not channel_ids:
                    logger.debug(
                        "AlertTriggerService: rule %s has no resolvable channels; skipping",
                        rule.id,
                    )
                    continue
                recipients = self._resolve_recipients(db, rule, workspace_id)
                if not recipients:
                    logger.debug(
                        "AlertTriggerService: rule %s has no recipients; skipping",
                        rule.id,
                    )
                    continue
                subject, body = self._render(trigger_type, payload)
                full_payload = {
                    "subject": subject,
                    "body": body,
                    "trigger_type": trigger_type,
                    **payload,
                }
                for channel_id in channel_ids:
                    for recipient in recipients:
                        try:
                            evt_service.log_event(
                                db,
                                workspace_id=workspace_id,
                                tenant_id=tenant_id,
                                alert_rule_id=rule.id,
                                alert_channel_id=channel_id,
                                recipient=recipient,
                                payload=full_payload,
                                audit_ctx=audit_ctx,
                            )
                            n_logged += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "AlertTriggerService: log_event failed for rule=%s channel=%s recipient=%s: %s",
                                rule.id,
                                channel_id,
                                recipient,
                                exc,
                            )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "AlertTriggerService: rule %s processing error: %s",
                    getattr(rule, "id", "?"),
                    exc,
                    exc_info=True,
                )

        return n_logged

    # ------------------------------------------------------------------
    # Recipient / channel resolution
    # ------------------------------------------------------------------

    def _resolve_channel_ids(
        self,
        db: Session,
        rule: AlertRule,
        workspace_id: UUID,
    ) -> list[UUID]:
        ids = _coerce_str_list(getattr(rule, "channel_ids", None))
        if not ids:
            return []
        try:
            uuid_ids = [UUID(i) for i in ids]
        except Exception:  # noqa: BLE001
            logger.warning("AlertTriggerService: invalid channel_ids on rule %s: %s", rule.id, ids)
            return []
        rows = (
            db.query(AlertChannel.id)
            .filter(
                AlertChannel.id.in_(uuid_ids),
                AlertChannel.workspace_id == workspace_id,
                AlertChannel.enabled.is_(True),
            )
            .all()
        )
        return [r[0] for r in rows]

    def _resolve_recipients(
        self,
        db: Session,
        rule: AlertRule,
        workspace_id: UUID,
    ) -> list[str]:
        """Return a deduplicated list of email addresses to notify."""
        emails: list[str] = []

        # Direct user IDs
        user_ids = _coerce_str_list(getattr(rule, "recipient_user_ids", None))
        if user_ids:
            try:
                uuid_ids = [UUID(u) for u in user_ids]
            except Exception:  # noqa: BLE001
                logger.warning(
                    "AlertTriggerService: invalid recipient_user_ids on rule %s",
                    rule.id,
                )
                uuid_ids = []
            if uuid_ids:
                rows = db.query(User.email).filter(User.id.in_(uuid_ids)).all()
                emails.extend(r[0] for r in rows if r[0])

        # Roles (best effort — workspace-scoped)
        roles = _coerce_str_list(getattr(rule, "recipient_roles", None))
        if roles:
            emails.extend(self._resolve_role_emails(db, workspace_id, roles))

        # Dedup, preserve order
        seen = set()
        out: list[str] = []
        for e in emails:
            if e and e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def _resolve_role_emails(
        self,
        db: Session,
        workspace_id: UUID,
        roles: list[str],
    ) -> list[str]:
        try:
            from app.models.role import Role, UserRoleAssignment  # type: ignore
        except Exception:  # noqa: BLE001
            return []
        try:
            rows = (
                db.query(User.email)
                .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
                .join(Role, Role.id == UserRoleAssignment.role_id)
                .filter(
                    UserRoleAssignment.workspace_id == workspace_id,
                    Role.name.in_(roles),
                )
                .distinct()
                .all()
            )
            return [r[0] for r in rows if r[0]]
        except Exception as exc:  # noqa: BLE001
            logger.debug("AlertTriggerService: role resolution skipped: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Payload rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _render(trigger_type: str, payload: dict[str, Any]) -> tuple[str, str]:
        title = payload.get("title") or payload.get("name") or ""
        subject_map = {
            "execution_failed": f"DQ Hub: Execution failed — {title or payload.get('flow_name') or payload.get('flow_id') or ''}".strip(
                " —"
            ),
            "execution_completed": f"DQ Hub: Execution completed — {title or payload.get('flow_name') or payload.get('flow_id') or ''}".strip(
                " —"
            ),
            "rule_failed": f"DQ Hub: Rule failed — {title or payload.get('rule_name') or payload.get('rule_id') or ''}".strip(
                " —"
            ),
            "check_failed": f"DQ Hub: Check failed — {title or payload.get('node_id') or ''}".strip(
                " —"
            ),
            "issue_created": f"DQ Hub: New issue — {title}".strip(" —"),
            "issue_overdue": f"DQ Hub: Issue overdue — {title}".strip(" —"),
            "incident_created": f"DQ Hub: New incident — {title}".strip(" —"),
            "incident_status_changed": f"DQ Hub: Incident status changed — {title}".strip(" —"),
            "incident_assigned": f"DQ Hub: Incident assigned to you — {title}".strip(" —"),
        }
        subject = subject_map.get(trigger_type, f"DQ Hub: {trigger_type}")

        lines = [f"Trigger: {trigger_type}"]
        for k, v in payload.items():
            if k in ("subject", "body"):
                continue
            lines.append(f"{k}: {v}")
        body = "\n".join(lines)
        return subject, body
