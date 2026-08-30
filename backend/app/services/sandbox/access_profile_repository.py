"""
F134 — Demo Sandbox Provisioning
AccessProfileRepository: read operations for control.access_profiles.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FIND_BY_ID_SQL = text("""
    SELECT id::text, code, display_name, flags, default_role, is_enabled, created_at
    FROM control.access_profiles
    WHERE id = CAST(:id AS UUID)
""")

_FIND_BY_CODE_SQL = text("""
    SELECT id::text, code, display_name, flags, default_role, is_enabled, created_at
    FROM control.access_profiles
    WHERE code = :code
""")

_LIST_ENABLED_SQL = text("""
    SELECT id::text, code, display_name, flags, default_role, is_enabled, created_at
    FROM control.access_profiles
    WHERE is_enabled = TRUE
    ORDER BY display_name ASC
""")


class AccessProfileRepository:
    """Read access for control.access_profiles."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_id(self, profile_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_ID_SQL, {"id": str(profile_id)}).fetchone()
        return dict(row._mapping) if row else None

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_CODE_SQL, {"code": code}).fetchone()
        return dict(row._mapping) if row else None

    def list_enabled(self) -> list[dict[str, Any]]:
        rows = self._db.execute(_LIST_ENABLED_SQL).fetchall()
        return [dict(r._mapping) for r in rows]
