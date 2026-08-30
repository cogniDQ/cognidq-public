"""
F134 — Demo Sandbox Provisioning
DemoRequestRepository: all DB operations for control.demo_requests.

All methods use SQLAlchemy text() queries (codebase convention) and
return dicts or DTO-like objects — never raw SQLAlchemy Row proxies in
the public interface.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Query constants
# ──────────────────────────────────────────────────────────────────────────────

_INSERT_SQL = text("""
    INSERT INTO control.demo_requests (
        id, status, public_status_token,
        work_email, first_name, last_name,
        company_name, job_title, team_size, country,
        primary_use_case, stack, heard_about_us,
        consent, is_personal_email,
        source_ip, user_agent,
        admin_tags, internal_note
    ) VALUES (
        :id, 'submitted', :token,
        :work_email, :first_name, :last_name,
        :company_name, :job_title, :team_size, :country,
        :primary_use_case, CAST(:stack AS JSONB), :heard_about_us,
        :consent, :is_personal_email,
        CAST(:source_ip AS INET), :user_agent,
        '[]'::JSONB, NULL
    )
    RETURNING
        id::text, status, public_status_token,
        work_email, first_name, last_name,
        company_name, created_at, updated_at
""")

_FIND_BY_ID_SQL = text("""
    SELECT
        id::text, status, public_status_token,
        work_email, first_name, last_name,
        company_name, job_title, team_size, country,
        primary_use_case, stack, heard_about_us,
        consent, is_personal_email,
        source_ip::text, user_agent,
        admin_tags, internal_note, rejection_reason,
        decided_by::text, decided_at,
        created_at, updated_at
    FROM control.demo_requests
    WHERE id = :id
""")

_FIND_BY_TOKEN_SQL = text("""
    SELECT
        id::text, status, public_status_token,
        work_email, first_name, last_name,
        company_name, created_at, updated_at
    FROM control.demo_requests
    WHERE public_status_token = :token
""")

_FIND_ACTIVE_BY_EMAIL_SQL = text("""
    SELECT id::text, status, public_status_token, work_email, created_at
    FROM control.demo_requests
    WHERE work_email = :email
      AND status IN ('submitted', 'under_review', 'approved', 'provisioned', 'active')
    ORDER BY created_at DESC
    LIMIT 1
""")

_UPDATE_STATUS_SQL = text("""
    UPDATE control.demo_requests
    SET
        status     = CAST(:status AS text),
        updated_at = NOW(),
        decided_by = CAST(:decided_by AS UUID),
        decided_at = CASE WHEN :set_decided_at THEN NOW() ELSE decided_at END,
        rejection_reason = COALESCE(:rejection_reason, rejection_reason),
        internal_note    = COALESCE(:internal_note, internal_note),
        admin_tags       = COALESCE(CAST(:admin_tags AS JSONB), admin_tags)
    WHERE id = :id
    RETURNING id::text, status, updated_at
""")

_LIST_SQL_TEMPLATE = """
    SELECT
        id::text, status, public_status_token,
        work_email, first_name, last_name,
        company_name, is_personal_email,
        created_at, updated_at,
        COUNT(*) OVER() AS total_count
    FROM control.demo_requests
    {where_clause}
    ORDER BY {sort_col} {sort_dir}
    LIMIT :limit OFFSET :offset
"""


class DemoRequestRepository:
    """Data access for control.demo_requests."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Write ──────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        work_email: str,
        first_name: str,
        last_name: str,
        company_name: str,
        job_title: str | None,
        team_size: str,
        country: str | None,
        primary_use_case: str,
        stack: dict[str, Any],
        heard_about_us: str | None,
        consent: bool,
        is_personal_email: bool,
        public_status_token: str,
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        row = self._db.execute(
            _INSERT_SQL,
            {
                "id": str(uuid4()),
                "token": public_status_token,
                "work_email": work_email,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company_name,
                "job_title": job_title,
                "team_size": team_size,
                "country": country,
                "primary_use_case": primary_use_case,
                "stack": json.dumps(stack),
                "heard_about_us": heard_about_us,
                "consent": consent,
                "is_personal_email": is_personal_email,
                "source_ip": source_ip,
                "user_agent": user_agent,
            },
        ).fetchone()
        return dict(row._mapping)

    def update_status(
        self,
        *,
        request_id: UUID,
        status: str,
        decided_by: UUID | None = None,
        set_decided_at: bool = False,
        rejection_reason: str | None = None,
        internal_note: str | None = None,
        admin_tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        row = self._db.execute(
            _UPDATE_STATUS_SQL,
            {
                "id": str(request_id),
                "status": status,
                "decided_by": str(decided_by) if decided_by else None,
                "set_decided_at": set_decided_at,
                "rejection_reason": rejection_reason,
                "internal_note": internal_note,
                "admin_tags": json.dumps(admin_tags) if admin_tags is not None else None,
            },
        ).fetchone()
        return dict(row._mapping) if row else None

    # ── Read ───────────────────────────────────────────────────────────────

    def find_by_id(self, request_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_ID_SQL, {"id": str(request_id)}).fetchone()
        return dict(row._mapping) if row else None

    def find_by_public_token(self, token: str) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_TOKEN_SQL, {"token": token}).fetchone()
        return dict(row._mapping) if row else None

    def find_active_by_email(self, email: str) -> dict[str, Any] | None:
        """Return the most recent non-terminal request for an email, or None."""
        row = self._db.execute(_FIND_ACTIVE_BY_EMAIL_SQL, {"email": email.lower()}).fetchone()
        return dict(row._mapping) if row else None

    def list_with_filters(
        self,
        *,
        status: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (rows, total_count) for admin list view."""
        # Whitelist sort column and direction
        allowed_cols = {"created_at", "updated_at", "status", "work_email"}
        if sort_by not in allowed_cols:
            sort_by = "created_at"
        if sort_dir not in ("asc", "desc"):
            sort_dir = "desc"

        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if status:
            conditions.append("status = :status")
            params["status"] = status

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = text(
            _LIST_SQL_TEMPLATE.format(
                where_clause=where_clause,
                sort_col=sort_by,
                sort_dir=sort_dir,
            )
        )
        rows = self._db.execute(sql, params).fetchall()
        total = int(rows[0]._mapping["total_count"]) if rows else 0
        return [dict(r._mapping) for r in rows], total
