"""
F001 — Tenant repository layer
================================

All SQL operations against ``control.tenants`` and ``control.tenant_audit_logs``.
Uses SQLAlchemy ``Session.execute(text(...))`` so that the existing ``get_db()``
dependency can be reused in the FastAPI handler — no separate psycopg2 connection
pool is needed.

Enum-typed columns require an explicit SQL cast
    CAST(:val AS control.<enum_name>)
because psycopg2 cannot infer the target type from a parameterised query.

The JSONB ``new_data`` column in tenant_audit_logs is inserted via
    CAST(:new_data AS JSONB)
where the parameter value is a ``json.dumps(...)`` string.

Packet 4 — list() implementation notes
---------------------------------------
* A single SQL query with ``COUNT(*) OVER()`` is used so that the data page
  and the total row count are fetched atomically (TDD S-04).
* The only exception: when the requested page is beyond the last page, the
  window function returns no rows and cannot report a total.  In that case a
  second ``COUNT(*)`` query is issued against the same WHERE clause.
* ``sort_by`` and ``sort_dir`` are injected as f-string literals into the SQL
  template.  They are safe to interpolate because ``parse_list_tenants_query``
  whitelist-validates them before they reach this layer.  A programmer assert
  guard is included as defence-in-depth.
"""

from __future__ import annotations

import builtins
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.queries import ListTenantsQuery, escape_ilike_term

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_CHECK_NAME_SQL = text("""
    SELECT 1
    FROM control.tenants
    WHERE tenant_name_lower = LOWER(TRIM(:name))
    LIMIT 1
""")

_CHECK_SLUG_SQL = text("""
    SELECT 1
    FROM control.tenants
    WHERE tenant_slug = :slug
    LIMIT 1
""")

_FIND_BY_ID_SQL = text("""
    SELECT
        tenant_id::text,
        tenant_name,
        tenant_slug,
        status::text,
        status_reason,
        region::text,
        plan::text,
        service_start_date,
        tenant_notes,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text
    FROM control.tenants
    WHERE tenant_id = CAST(:tenant_id AS UUID)
""")

_INSERT_TENANT_SQL = text("""
    INSERT INTO control.tenants (
        tenant_id,
        tenant_name,
        tenant_slug,
        status,
        status_reason,
        region,
        plan,
        service_start_date,
        tenant_notes,
        created_by,
        updated_by,
        version
    ) VALUES (
        :tenant_id,
        :tenant_name,
        :tenant_slug,
        CAST(:status AS control.tenant_status_enum),
        :status_reason,
        CAST(:region AS control.tenant_region_enum),
        CAST(:plan   AS control.tenant_plan_enum),
        :service_start_date,
        :tenant_notes,
        :created_by,
        :updated_by,
        0
    )
    RETURNING
        tenant_id::text,
        tenant_name,
        tenant_slug,
        status::text,
        status_reason,
        region::text,
        plan::text,
        service_start_date,
        tenant_notes,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text
""")

_INSERT_AUDIT_SQL = text("""
    INSERT INTO control.tenant_audit_logs (
        log_id,
        tenant_id,
        event_type,
        actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        reason
    ) VALUES (
        :log_id,
        :tenant_id,
        'tenant_created',
        :actor_id,
        :actor_role,
        NULL,
        CAST(:new_data AS JSONB),
        NOW(),
        NULL
    )
""")

# ---------------------------------------------------------------------------
# Packet 6 — update-tenant SQL statements
# ---------------------------------------------------------------------------

_CHECK_NAME_EXCLUDING_SQL = text("""
    SELECT 1
    FROM control.tenants
    WHERE tenant_name_lower = LOWER(TRIM(:name))
      AND tenant_id != CAST(:exclude_id AS UUID)
    LIMIT 1
""")

_FIND_BY_ID_FOR_UPDATE_SQL = text("""
    SELECT
        tenant_id::text,
        tenant_name,
        tenant_slug,
        status::text,
        status_reason,
        region::text,
        plan::text,
        service_start_date,
        tenant_notes,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text
    FROM control.tenants
    WHERE tenant_id = CAST(:tenant_id AS UUID)
    FOR UPDATE NOWAIT
""")

_INSERT_UPDATE_AUDIT_SQL = text("""
    INSERT INTO control.tenant_audit_logs (
        log_id,
        tenant_id,
        event_type,
        actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        reason
    ) VALUES (
        :log_id,
        :tenant_id,
        'tenant_updated',
        :actor_id,
        :actor_role,
        CAST(:previous_data AS JSONB),
        CAST(:new_data AS JSONB),
        NOW(),
        NULL
    )
""")

# ---------------------------------------------------------------------------
# Packet 7 — change-status SQL statements
# ---------------------------------------------------------------------------

_UPDATE_STATUS_SQL = text("""
    UPDATE control.tenants
    SET
        status       = CAST(:status AS control.tenant_status_enum),
        status_reason = :status_reason,
        updated_at   = NOW(),
        updated_by   = :updated_by,
        version      = version + 1
    WHERE tenant_id = CAST(:tenant_id AS UUID)
    RETURNING
        tenant_id::text,
        status::text,
        status_reason,
        updated_at,
        updated_by::text
""")

_INSERT_STATUS_AUDIT_SQL = text("""
    INSERT INTO control.tenant_audit_logs (
        log_id,
        tenant_id,
        event_type,
        actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        reason
    ) VALUES (
        :log_id,
        :tenant_id,
        'tenant_status_changed',
        :actor_id,
        :actor_role,
        CAST(:previous_data AS JSONB),
        CAST(:new_data AS JSONB),
        NOW(),
        :reason
    )
""")

_INSERT_OUTBOX_SQL = text("""
    INSERT INTO control.outbox_events (
        event_id,
        event_type,
        tenant_id,
        payload,
        occurred_at,
        delivered,
        retry_count
    ) VALUES (
        CAST(:event_id AS UUID),
        :event_type,
        CAST(:tenant_id AS UUID),
        CAST(:payload AS JSONB),
        :occurred_at,
        FALSE,
        0
    )
""")

# ---------------------------------------------------------------------------
# Packet 8 — audit-logs read SQL
# ---------------------------------------------------------------------------

_EXISTS_SQL = text("""
    SELECT 1
    FROM control.tenants
    WHERE tenant_id = CAST(:tenant_id AS UUID)
    LIMIT 1
""")

# The audit log list query uses COUNT(*) OVER() so that the page rows and the
# total count are fetched atomically (consistent with the List Tenants pattern
# from Packet 4 / TDD S-04).  Optional filter clauses are appended at runtime.
_LIST_AUDIT_LOGS_BASE = """
    SELECT
        log_id::text                    AS log_id,
        tenant_id::text                 AS tenant_id,
        event_type,
        actor_id::text                  AS actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        reason,
        COUNT(*) OVER()                 AS total_count
    FROM control.tenant_audit_logs
    WHERE tenant_id = CAST(:tenant_id AS UUID)
"""


# ---------------------------------------------------------------------------
# Repository classes
# ---------------------------------------------------------------------------


class TenantRepository:
    """Read and write operations for ``control.tenants``."""

    @staticmethod
    def check_name_exists(db: Session, tenant_name: str) -> bool:
        """Return True if a tenant row already exists with the same normalised name."""
        row = db.execute(_CHECK_NAME_SQL, {"name": tenant_name}).first()
        return row is not None

    @staticmethod
    def check_slug_exists(db: Session, tenant_slug: str) -> bool:
        """Return True if a tenant row already exists with the given slug."""
        row = db.execute(_CHECK_SLUG_SQL, {"slug": tenant_slug}).first()
        return row is not None

    @staticmethod
    def insert(db: Session, params: dict[str, Any]) -> dict[str, Any]:
        """Insert a new tenant row and return all RETURNING columns as a plain dict."""
        result = db.execute(_INSERT_TENANT_SQL, params)
        row = result.mappings().one()
        return dict(row)

    @staticmethod
    def find_by_id(db: Session, tenant_id_str: str) -> dict[str, Any] | None:
        """Return the full tenant row as a plain dict, or None if not found.

        Args:
            tenant_id_str: UUID string of the tenant to look up.

        Returns:
            Dict with all 13 tenant columns, or ``None`` if no matching row.
        """
        row = db.execute(_FIND_BY_ID_SQL, {"tenant_id": tenant_id_str}).mappings().first()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def find_by_id_for_update(db: Session, tenant_id_str: str) -> dict[str, Any] | None:
        """Return the tenant row with a ``FOR UPDATE NOWAIT`` row lock.

        Acquires an exclusive row lock so that a concurrent writer cannot
        modify the same row.  If the lock is not immediately available,
        PostgreSQL raises ``LockNotAvailable`` (pgcode ``55P03``), which
        SQLAlchemy wraps as ``OperationalError``.  The caller is responsible
        for translating this into HTTP 409.

        Args:
            tenant_id_str: UUID string of the tenant to lock.

        Returns:
            Dict with all 13 tenant columns, or ``None`` if no matching row.
        """
        row = (
            db.execute(_FIND_BY_ID_FOR_UPDATE_SQL, {"tenant_id": tenant_id_str}).mappings().first()
        )
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def check_name_exists_excluding(db: Session, tenant_name: str, exclude_tenant_id: str) -> bool:
        """Return True if any *other* tenant has the same normalised name.

        Used by the PATCH flow so that renaming without changing effective
        normalised name does not block the update.

        Args:
            tenant_name:       The candidate name (unnormalised).
            exclude_tenant_id: UUID string of the tenant being updated.
        """
        row = db.execute(
            _CHECK_NAME_EXCLUDING_SQL,
            {"name": tenant_name, "exclude_id": exclude_tenant_id},
        ).first()
        return row is not None

    @staticmethod
    def exists(db: Session, tenant_id_str: str) -> bool:
        """Return True if a tenant row with the given id exists.

        Used as a lightweight pre-check before reading audit logs so that
        the endpoint can return 404 for an unknown tenant rather than an
        empty audit log list.

        Args:
            tenant_id_str: UUID string of the tenant to check.
        """
        row = db.execute(_EXISTS_SQL, {"tenant_id": tenant_id_str}).first()
        return row is not None

    @staticmethod
    def update(
        db: Session,
        tenant_id_str: str,
        changes: dict[str, Any],
        updated_by: str,
    ) -> dict[str, Any]:
        """Apply a validated change set and return the updated tenant row.

        Builds a dynamic UPDATE statement from ``changes``.  Only the keys
        present in ``changes`` are updated; all other columns are untouched.
        ``updated_at``, ``updated_by``, and ``version`` are always set.

        Args:
            tenant_id_str: UUID string of the tenant to update.
            changes:       Dict mapping column name → new value (validated).
                           Keys must be in the mutable-field whitelist.
            updated_by:    UUID string of the actor performing the update.

        Returns:
            Dict with all 13 tenant columns as returned by RETURNING.
        """
        # Safety: only whitelisted mutable columns may appear in changes.
        _ALLOWED_UPDATE_COLS: frozenset = frozenset(
            {"tenant_name", "plan", "status_reason", "service_start_date", "tenant_notes"}
        )
        for col in changes:
            assert col in _ALLOWED_UPDATE_COLS, (
                f"Column '{col}' is not in the PATCH mutable whitelist"
            )

        # Build the SET clause dynamically.
        set_parts: list[str] = []
        params: dict[str, Any] = {
            "tenant_id": tenant_id_str,
            "updated_by": updated_by,
        }

        for col in changes:
            if col == "plan":
                set_parts.append(f"plan = CAST(:{col} AS control.tenant_plan_enum)")
            else:
                set_parts.append(f"{col} = :{col}")
            params[col] = changes[col]

        set_parts += ["updated_at = NOW()", "updated_by = :updated_by", "version = version + 1"]

        update_sql = text(f"""
            UPDATE control.tenants
            SET {", ".join(set_parts)}
            WHERE tenant_id = CAST(:tenant_id AS UUID)
            RETURNING
                tenant_id::text,
                tenant_name,
                tenant_slug,
                status::text,
                status_reason,
                region::text,
                plan::text,
                service_start_date,
                tenant_notes,
                created_at,
                updated_at,
                created_by::text,
                updated_by::text
        """)

        result = db.execute(update_sql, params)
        return dict(result.mappings().one())

    @staticmethod
    def update_status(
        db: Session,
        tenant_id_str: str,
        new_status: str,
        new_reason: str | None,
        updated_by: str,
    ) -> dict[str, Any]:
        """UPDATE tenant status/status_reason and return the RETURNING columns.

        Always increments ``version`` by 1 and sets ``updated_at = NOW()``.
        Called inside the same DB transaction that issued ``find_by_id_for_update``
        so that the exclusive row lock is still held.

        Args:
            tenant_id_str: UUID string of the tenant to update.
            new_status:    Validated target status enum string.
            new_reason:    Trimmed ``status_reason``, or ``None`` to clear.
            updated_by:    UUID string of the actor performing the change.

        Returns:
            Dict with keys: ``tenant_id``, ``status``, ``status_reason``,
            ``updated_at``, ``updated_by``.
        """
        result = db.execute(
            _UPDATE_STATUS_SQL,
            {
                "tenant_id": tenant_id_str,
                "status": new_status,
                "status_reason": new_reason,
                "updated_by": updated_by,
            },
        )
        return dict(result.mappings().one())

    @staticmethod
    def list(
        db: Session,
        query: ListTenantsQuery,
    ) -> tuple[builtins.list[dict[str, Any]], int]:
        """Execute the list query and return ``(page_rows, total_count)``.

        Implements TDD S-04: a single query with ``COUNT(*) OVER()`` is used
        for the normal path so that the page data and the total count are
        fetched atomically.  The only exception is the over-page case, where
        the window function returns 0 rows and a separate ``COUNT(*)`` query
        is issued with the same WHERE clause.

        Args:
            db:    SQLAlchemy session.
            query: Validated ``ListTenantsQuery`` from the HTTP handler.

        Returns:
            A 2-tuple: (list of row dicts for the current page, total count
            matching all WHERE conditions — respecting include_archived).
        """
        # Programmer safety: sort_by and sort_dir are injected as SQL literals
        assert query.sort_by in {"created_at", "updated_at"}, (
            f"sort_by '{query.sort_by}' not in whitelist"
        )
        assert query.sort_dir in {"asc", "desc"}, f"sort_dir '{query.sort_dir}' not in whitelist"

        conditions: list[str] = []
        params: dict[str, Any] = {}

        # ------------------------------------------------------------------
        # include_archived guard — exclude archived from data AND total
        # ------------------------------------------------------------------
        if not query.include_archived:
            conditions.append("status::text != 'archived'")

        # ------------------------------------------------------------------
        # Enum filters — cast column to text for plain-string comparison
        # ------------------------------------------------------------------
        if query.status is not None:
            conditions.append("status::text = :status")
            params["status"] = query.status

        if query.region is not None:
            conditions.append("region::text = :region")
            params["region"] = query.region

        if query.plan is not None:
            conditions.append("plan::text = :plan")
            params["plan"] = query.plan

        # ------------------------------------------------------------------
        # Full-text search — ILIKE on tenant_name and tenant_slug (TDD §3.3)
        # ILIKE metacharacters are escaped before building the pattern.
        # ------------------------------------------------------------------
        if query.q is not None:
            escaped = escape_ilike_term(query.q)
            q_pattern = f"%{escaped}%"
            conditions.append("(tenant_name ILIKE :q_pattern OR tenant_slug ILIKE :q_pattern)")
            params["q_pattern"] = q_pattern

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # sort_by / sort_dir are whitelist-validated; safe to interpolate as
        # SQL identifiers.  Uppercase dir avoids any edge-case differences.
        sort_col = query.sort_by
        sort_dir_sql = query.sort_dir.upper()

        offset = (query.page - 1) * query.page_size
        params["page_size"] = query.page_size
        params["offset"] = offset

        list_sql = text(f"""
            SELECT
                tenant_id::text,
                tenant_name,
                tenant_slug,
                status::text,
                region::text,
                plan::text,
                created_at,
                updated_at,
                COUNT(*) OVER() AS total_count
            FROM control.tenants
            WHERE {where_clause}
            ORDER BY {sort_col} {sort_dir_sql}
            LIMIT :page_size OFFSET :offset
        """)

        rows = list(db.execute(list_sql, params).mappings().all())

        if rows:
            total = int(rows[0]["total_count"])
            return [dict(r) for r in rows], total

        # ------------------------------------------------------------------
        # Over-page fallback: the window function returned no rows, so
        # issue a separate COUNT with the same WHERE clause to return the
        # accurate total (TDD E-06).
        # ------------------------------------------------------------------
        count_params = {k: v for k, v in params.items() if k not in ("page_size", "offset")}
        count_sql = text(f"""
            SELECT COUNT(*) AS cnt
            FROM control.tenants
            WHERE {where_clause}
        """)
        count_row = db.execute(count_sql, count_params).one()
        return [], int(count_row[0])


class AuditLogRepository:
    """Write-only operations for ``control.tenant_audit_logs``."""

    @staticmethod
    def insert(
        db: Session,
        *,
        log_id: str,
        tenant_id: str,
        actor_id: str,
        actor_role: str,
        new_data: dict[str, Any],
    ) -> None:
        """Insert a ``tenant_created`` audit log entry."""
        db.execute(
            _INSERT_AUDIT_SQL,
            {
                "log_id": log_id,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "new_data": json.dumps(new_data),
            },
        )

    @staticmethod
    def insert_update(
        db: Session,
        *,
        log_id: str,
        tenant_id: str,
        actor_id: str,
        actor_role: str,
        previous_data: dict[str, Any],
        new_data: dict[str, Any],
    ) -> None:
        """Insert a ``tenant_updated`` audit log entry.

        Both ``previous_data`` and ``new_data`` must contain only the fields
        that actually changed (TDD §4.6, §2.4).
        """
        db.execute(
            _INSERT_UPDATE_AUDIT_SQL,
            {
                "log_id": log_id,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "previous_data": json.dumps(previous_data, default=str),
                "new_data": json.dumps(new_data, default=str),
            },
        )

    @staticmethod
    def insert_status_change(
        db: Session,
        *,
        log_id: str,
        tenant_id: str,
        actor_id: str,
        actor_role: str,
        previous_data: dict[str, Any],
        new_data: dict[str, Any],
        reason: str | None,
    ) -> None:
        """Insert a ``tenant_status_changed`` audit log entry (TDD §4.4, §4.6)."""
        db.execute(
            _INSERT_STATUS_AUDIT_SQL,
            {
                "log_id": log_id,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "previous_data": json.dumps(previous_data, default=str),
                "new_data": json.dumps(new_data, default=str),
                "reason": reason,
            },
        )

    @staticmethod
    def list_by_tenant(
        db: Session,
        tenant_id_str: str,
        event_type: str | None,
        actor_id_str: str | None,
        from_dt: Any,
        to_dt: Any,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query audit log rows for a single tenant with optional filters.

        Implements TDD §3.7: ordered by ``occurred_at DESC``, paginated,
        total count via ``COUNT(*) OVER()`` (atomic single-query approach,
        consistent with Packet 4 list pattern).

        Args:
            tenant_id_str: UUID string — already validated by the endpoint.
            event_type:    Optional filter on the event_type column.
            actor_id_str:  Optional filter on the actor_id column.
            from_dt:       Optional lower bound for occurred_at (inclusive).
            to_dt:         Optional upper bound for occurred_at (inclusive).
            page:          1-based page number.
            page_size:     Rows per page (1–100).

        Returns:
            (rows, total) where rows is a list of plain dicts and total is
            the number of matching rows across all pages.
        """
        extra_conditions: list[str] = []
        params: dict[str, Any] = {"tenant_id": tenant_id_str}

        if event_type is not None:
            extra_conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        if actor_id_str is not None:
            extra_conditions.append("actor_id = CAST(:actor_id AS UUID)")
            params["actor_id"] = actor_id_str

        if from_dt is not None:
            extra_conditions.append("occurred_at >= :from_dt")
            params["from_dt"] = from_dt

        if to_dt is not None:
            extra_conditions.append("occurred_at <= :to_dt")
            params["to_dt"] = to_dt

        extra_where = ""
        if extra_conditions:
            extra_where = " AND " + " AND ".join(extra_conditions)

        offset = (page - 1) * page_size
        params["page_size"] = page_size
        params["offset"] = offset

        sql = text(
            _LIST_AUDIT_LOGS_BASE
            + extra_where
            + "\n    ORDER BY occurred_at DESC"
            + "\n    LIMIT :page_size OFFSET :offset"
        )

        rows = list(db.execute(sql, params).mappings().all())

        if rows:
            total = int(rows[0]["total_count"])
            return [dict(r) for r in rows], total

        # Over-page fallback: window function returned no rows; count separately.
        count_params = {k: v for k, v in params.items() if k not in ("page_size", "offset")}
        count_sql = text(
            "SELECT COUNT(*) AS cnt FROM control.tenant_audit_logs"
            " WHERE tenant_id = CAST(:tenant_id AS UUID)" + extra_where
        )
        count_row = db.execute(count_sql, count_params).one()
        return [], int(count_row[0])


class OutboxRepository:
    """Write operations for ``control.outbox_events`` (TDD §4.4, §9)."""

    @staticmethod
    def insert_suspended_event(
        db: Session,
        *,
        event_id: str,
        tenant_id: str,
        occurred_at: Any,
    ) -> None:
        """Insert a ``tenant_suspended`` outbox event within the caller's transaction.

        The INSERT must be issued on the same ``db`` session as the tenant
        UPDATE and audit log INSERT so that all three writes are atomic.

        Args:
            event_id:    UUID string for the new outbox row.
            tenant_id:   UUID string of the suspended tenant.
            occurred_at: UTC datetime at which the suspension occurred.
        """
        payload = json.dumps(
            {"event_type": "tenant_suspended", "tenant_id": tenant_id},
        )
        db.execute(
            _INSERT_OUTBOX_SQL,
            {
                "event_id": event_id,
                "event_type": "tenant_suspended",
                "tenant_id": tenant_id,
                "payload": payload,
                "occurred_at": occurred_at,
            },
        )


def _translate_integrity_error(exc: Exception) -> None:
    """Convert a psycopg2 UniqueViolation (wrapped in SQLAlchemy IntegrityError)
    into the appropriate ``TenantAPIError``.

    Always raises — never returns.
    """
    orig = getattr(exc, "orig", None)
    if orig is not None:
        pgcode = getattr(orig, "pgcode", None)
        if pgcode == "23505":  # UniqueViolation
            constraint: str = getattr(getattr(orig, "diag", None), "constraint_name", "") or ""
            if "name_lower" in constraint or "name" in constraint:
                raise TenantAPIError(
                    422,
                    "duplicate_name",
                    "A tenant with this name already exists.",
                ) from exc
            if "slug" in constraint:
                raise TenantAPIError(
                    422,
                    "duplicate_slug",
                    "A tenant with this slug already exists.",
                ) from exc
    logger.exception("Unhandled DB integrity error")
    raise TenantAPIError(500, "internal_error", "An unexpected database error occurred.") from exc
