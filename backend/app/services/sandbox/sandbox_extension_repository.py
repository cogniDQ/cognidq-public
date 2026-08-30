"""
F134 — Demo Sandbox Provisioning
SandboxExtensionRepository: DB operations for control.sandbox_extensions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_INSERT_SQL = text("""
    INSERT INTO control.sandbox_extensions (
        id, sandbox_id, extended_by, extension_days,
        note, previous_expires_at, new_expires_at
    ) VALUES (
        :id,
        CAST(:sandbox_id AS UUID),
        CAST(:extended_by AS UUID),
        :extension_days,
        :note,
        :previous_expires_at,
        :new_expires_at
    )
    RETURNING id::text, sandbox_id::text, extension_days, new_expires_at, created_at
""")

_COUNT_SQL = text("""
    SELECT COUNT(*) AS n
    FROM control.sandbox_extensions
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
""")

_LIST_SQL = text("""
    SELECT
        id::text, sandbox_id::text, extended_by::text,
        extension_days, note, previous_expires_at, new_expires_at, created_at
    FROM control.sandbox_extensions
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
    ORDER BY created_at ASC
""")


class SandboxExtensionRepository:
    """Data access for control.sandbox_extensions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        sandbox_id: UUID,
        extended_by: UUID | None,
        extension_days: int,
        note: str,
        previous_expires_at: datetime,
        new_expires_at: datetime,
    ) -> dict[str, Any]:
        row = self._db.execute(
            _INSERT_SQL,
            {
                "id": str(uuid4()),
                "sandbox_id": str(sandbox_id),
                "extended_by": str(extended_by) if extended_by else None,
                "extension_days": extension_days,
                "note": note,
                "previous_expires_at": previous_expires_at,
                "new_expires_at": new_expires_at,
            },
        ).fetchone()
        return dict(row._mapping)

    def count_by_sandbox(self, sandbox_id: UUID) -> int:
        row = self._db.execute(_COUNT_SQL, {"sandbox_id": str(sandbox_id)}).fetchone()
        return int(row._mapping["n"]) if row else 0

    def list_by_sandbox(self, sandbox_id: UUID) -> list[dict[str, Any]]:
        rows = self._db.execute(_LIST_SQL, {"sandbox_id": str(sandbox_id)}).fetchall()
        return [dict(r._mapping) for r in rows]
