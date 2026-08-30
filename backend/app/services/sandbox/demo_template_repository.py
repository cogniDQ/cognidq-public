"""
F134 — Demo Sandbox Provisioning
DemoTemplateRepository: read-only access for control.demo_templates.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FIND_BY_ID_SQL = text("""
    SELECT id, display_name, description, seeder_module,
           default_duration_days, is_enabled, created_at
    FROM control.demo_templates
    WHERE id = :id
""")

_LIST_ENABLED_SQL = text("""
    SELECT id, display_name, description, seeder_module,
           default_duration_days, is_enabled, created_at
    FROM control.demo_templates
    WHERE is_enabled = TRUE
    ORDER BY display_name ASC
""")

_LIST_ALL_SQL = text("""
    SELECT id, display_name, description, seeder_module,
           default_duration_days, is_enabled, created_at
    FROM control.demo_templates
    ORDER BY display_name ASC
""")


class DemoTemplateRepository:
    """Read-only access for control.demo_templates."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_id(self, template_id: str) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_ID_SQL, {"id": template_id}).fetchone()
        return dict(row._mapping) if row else None

    def list_enabled(self) -> list[dict[str, Any]]:
        rows = self._db.execute(_LIST_ENABLED_SQL).fetchall()
        return [dict(r._mapping) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._db.execute(_LIST_ALL_SQL).fetchall()
        return [dict(r._mapping) for r in rows]
