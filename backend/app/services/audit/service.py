"""
F052 Audit Service
==================

Provides the central ``AuditService.write()`` method that every mutation
endpoint calls to persist an immutable audit entry.

Design invariants
-----------------
- Exceptions are **not** caught — they propagate to roll back the caller's
  transaction (FR-015).
- Sensitive fields are stripped before INSERT.
- ``action_type`` and ``target_entity_type`` are validated against the
  canonical frozen sets defined in ``constants.py``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.constants import VALID_ACTION_TYPES, VALID_ENTITY_TYPES
from app.services.audit.models import AuditEntry, strip_sensitive_fields

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_INSERT_SQL = """
    INSERT INTO control.workspace_audit_logs (
        log_id,
        tenant_id,
        workspace_id,
        action_type,
        actor_id,
        actor_role,
        actor_type,
        target_entity_type,
        target_entity_id,
        previous_data,
        new_data,
        occurred_at,
        request_id,
        source_ip
    ) VALUES (
        CAST(:log_id              AS UUID),
        CAST(:tenant_id           AS UUID),
        CAST(:workspace_id        AS UUID),
        :action_type,
        CAST(:actor_id            AS UUID),
        :actor_role,
        :actor_type,
        :target_entity_type,
        CAST(:target_entity_id    AS UUID),
        CAST(:previous_data       AS JSONB),
        CAST(:new_data            AS JSONB),
        :occurred_at,
        CAST(:request_id          AS UUID),
        :source_ip
    )
"""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class AuditWriteFailedError(Exception):
    """Raised when the audit INSERT fails."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AuditService:
    """Stateless service that writes immutable audit entries."""

    def write(self, db: Session, entry: AuditEntry) -> None:
        """Persist *entry* using the caller's DB session.

        Validates ``action_type`` and ``target_entity_type`` before INSERT.
        Strips sensitive fields from ``before_state`` and ``after_state``.

        Raises
        ------
        ValueError
            If ``action_type`` or ``target_entity_type`` is not in the
            canonical frozen set.
        AuditWriteFailedError
            On any database exception during the INSERT.
        """
        # --- Validation ---
        if entry.action_type not in VALID_ACTION_TYPES:
            raise ValueError(
                f"Invalid action_type: {entry.action_type!r}. Must be one of VALID_ACTION_TYPES."
            )
        if entry.target_entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid target_entity_type: {entry.target_entity_type!r}. "
                f"Must be one of VALID_ENTITY_TYPES."
            )

        # --- Prepare values ---
        log_id = uuid.uuid4()
        occurred_at = datetime.now(UTC)

        cleaned_before = strip_sensitive_fields(entry.before_state)
        cleaned_after = strip_sensitive_fields(entry.after_state)

        params = {
            "log_id": str(log_id),
            "tenant_id": str(entry.tenant_id),
            "workspace_id": str(entry.workspace_id) if entry.workspace_id else None,
            "action_type": entry.action_type,
            "actor_id": str(entry.actor_id) if entry.actor_id else None,
            "actor_role": entry.actor_role,
            "actor_type": entry.actor_type,
            "target_entity_type": entry.target_entity_type,
            "target_entity_id": str(entry.target_entity_id) if entry.target_entity_id else None,
            "previous_data": json.dumps(cleaned_before) if cleaned_before is not None else None,
            "new_data": json.dumps(cleaned_after),
            "occurred_at": occurred_at,
            "request_id": str(entry.request_id) if entry.request_id else None,
            "source_ip": entry.source_ip,
        }

        try:
            db.execute(text(_INSERT_SQL), params)
            logger.debug(
                "audit_entry_written action_type=%s entity_type=%s entity_id=%s",
                entry.action_type,
                entry.target_entity_type,
                entry.target_entity_id,
            )
        except Exception as exc:
            logger.error(
                "audit_write_failed action_type=%s entity_type=%s: %s",
                entry.action_type,
                entry.target_entity_type,
                exc,
            )
            raise AuditWriteFailedError(
                f"Failed to write audit log for {entry.action_type}"
            ) from exc
