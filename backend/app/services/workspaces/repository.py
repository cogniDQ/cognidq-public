"""
F002 — Workspace repository layer
====================================

Provides:
* ``WorkspaceRepository`` — all SQL operations against ``control.workspaces``
* ``AuditLogWriter``       — append-only INSERT into ``control.workspace_audit_logs``
* ``TenantRepository``     — read-only SELECT from ``control.tenants``

Design notes
------------
* All SQL is parameterised via SQLAlchemy ``text()`` with named bind parameters.
  String interpolation into SQL text is *never* used for user-supplied data.
* The only exception to the parameterisation rule is the ORDER BY column
  expression in ``list_workspaces``, which is resolved from a compile-time
  allowlist dict before being spliced into the query text.  PostgreSQL cannot
  bind column identifiers as parameters (TDD §10.5 / A-12).
* Every query against ``control.workspaces`` includes
  ``AND tenant_id = CAST(:tenant_id AS UUID)`` for cross-tenant isolation
  (TDD §5.4).
* ``SELECT FOR UPDATE`` is appended in ``find_by_id`` when
  ``for_update=True``, enabling optimistic locking in mutation flows.
* The ``ILIKE`` search in ``list_workspaces`` escapes ``%``, ``_``, and ``\\``
  metacharacters before binding to prevent wildcard injection (TDD §10.5).
* ``AuditLogWriter`` strips ``workspace_name_lower`` and ``version`` from
  both ``new_data`` and ``previous_data`` before writing (TDD §9.3).

Connection management
---------------------
All methods accept an SQLAlchemy ``Session`` as their first argument so that
callers (the service layer) can wrap multiple operations in a single
transaction.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.workspaces.exceptions import (
    AuditWriteFailedError,
    DuplicateNameError,
    DuplicateSlugError,
    TenantNotFoundError,
    WorkspaceNotFoundError,
)
from app.services.workspaces.models import Workspace, WorkspaceAuditLog, WorkspaceStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Constraint names that map to typed exceptions (TDD §5.1 / packet plan task 4)
_CONSTRAINT_DUPLICATE_NAME = "uq_workspaces_name_lower_per_tenant"
_CONSTRAINT_DUPLICATE_SLUG = "uq_workspaces_slug_per_tenant"

# Keys stripped from JSONB audit payloads (TDD §9.3)
_AUDIT_STRIPPED_KEYS = frozenset({"workspace_name_lower", "version"})

# Compile-time allowlist for ORDER BY column expressions (A-12 / TDD §10.5)
# Maps the external API sort_by value to the safe SQL column expression.
_SORT_COLUMN_ALLOWLIST: dict[str, str] = {
    "created_at": "w.created_at",
    "updated_at": "w.updated_at",
}

# ---------------------------------------------------------------------------
# SQL constants — WorkspaceRepository
# ---------------------------------------------------------------------------

_INSERT_WORKSPACE_SQL = """
    INSERT INTO control.workspaces (
        workspace_id,
        tenant_id,
        workspace_name,
        workspace_slug,
        description,
        default_timezone,
        status,
        status_reason,
        created_at,
        updated_at,
        created_by,
        updated_by,
        version
    ) VALUES (
        CAST(:workspace_id  AS UUID),
        CAST(:tenant_id     AS UUID),
        :workspace_name,
        :workspace_slug,
        :description,
        :default_timezone,
        CAST(:status        AS control.workspace_status_enum),
        :status_reason,
        :created_at,
        :updated_at,
        CAST(:created_by    AS UUID),
        CAST(:updated_by    AS UUID),
        :version
    )
    RETURNING
        workspace_id::text,
        tenant_id::text,
        workspace_name,
        workspace_name_lower,
        workspace_slug,
        description,
        default_timezone,
        status::text,
        status_reason,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text,
        version
"""

_FIND_BY_ID_BASE_SQL = """
    SELECT
        workspace_id::text,
        tenant_id::text,
        workspace_name,
        workspace_name_lower,
        workspace_slug,
        description,
        default_timezone,
        status::text,
        status_reason,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text,
        version
    FROM control.workspaces w
    WHERE w.workspace_id = CAST(:workspace_id AS UUID)
      AND w.tenant_id    = CAST(:tenant_id    AS UUID)
"""

# No-tenant-filter variant — for Platform Operator reads (P08)
_FIND_BY_ID_ANY_TENANT_SQL = """
    SELECT
        workspace_id::text,
        tenant_id::text,
        workspace_name,
        workspace_name_lower,
        workspace_slug,
        description,
        default_timezone,
        status::text,
        status_reason,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text,
        version
    FROM control.workspaces w
    WHERE w.workspace_id = CAST(:workspace_id AS UUID)
"""

# ---------------------------------------------------------------------------
# SQL constants — AuditLogRepository
# ---------------------------------------------------------------------------

_AUDIT_SELECT_COLS = """
        al.log_id::text,
        al.tenant_id::text,
        al.workspace_id::text,
        al.action_type,
        al.actor_id::text,
        al.actor_role,
        al.previous_data,
        al.new_data,
        al.occurred_at,
        al.request_id::text,
        al.source_ip
"""

_UPDATE_WORKSPACE_SQL = """
    UPDATE control.workspaces
    SET
        workspace_name       = :workspace_name,
        workspace_slug       = :workspace_slug,
        description          = :description,
        default_timezone     = :default_timezone,
        status               = CAST(:status AS control.workspace_status_enum),
        status_reason        = :status_reason,
        updated_at           = :updated_at,
        updated_by           = CAST(:updated_by AS UUID),
        version              = :version
    WHERE workspace_id = CAST(:workspace_id AS UUID)
      AND tenant_id    = CAST(:tenant_id    AS UUID)
    RETURNING
        workspace_id::text,
        tenant_id::text,
        workspace_name,
        workspace_name_lower,
        workspace_slug,
        description,
        default_timezone,
        status::text,
        status_reason,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text,
        version
"""

_COUNT_ACTIVE_SQL = """
    SELECT COUNT(*) AS cnt
    FROM control.workspaces
    WHERE tenant_id = CAST(:tenant_id AS UUID)
      AND status    = 'active'
"""

_BULK_ARCHIVE_BY_TENANT_SQL = """
    UPDATE control.workspaces
    SET
        status        = 'archived',
        status_reason = :status_reason,
        updated_at    = :updated_at,
        updated_by    = CAST(:updated_by AS UUID),
        version       = version + 1
    WHERE tenant_id = CAST(:tenant_id AS UUID)
      AND status    != 'archived'
    RETURNING workspace_id::text
"""

_BULK_SUSPEND_BY_TENANT_SQL = """
    UPDATE control.workspaces
    SET
        status        = 'suspended',
        status_reason = :status_reason,
        updated_at    = :updated_at,
        updated_by    = CAST(:updated_by AS UUID),
        version       = version + 1
    WHERE tenant_id = CAST(:tenant_id AS UUID)
      AND status    = 'active'
    RETURNING workspace_id::text
"""

_BULK_ACTIVATE_BY_TENANT_SQL = """
    UPDATE control.workspaces
    SET
        status        = 'active',
        status_reason = NULL,
        updated_at    = :updated_at,
        updated_by    = CAST(:updated_by AS UUID),
        version       = version + 1
    WHERE tenant_id = CAST(:tenant_id AS UUID)
      AND status    = 'suspended'
    RETURNING workspace_id::text
"""

# ---------------------------------------------------------------------------
# SQL constants — AuditLogWriter
# ---------------------------------------------------------------------------

_INSERT_AUDIT_LOG_SQL = """
    INSERT INTO control.workspace_audit_logs (
        log_id,
        tenant_id,
        workspace_id,
        action_type,
        actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        request_id,
        source_ip
    ) VALUES (
        CAST(:log_id       AS UUID),
        CAST(:tenant_id    AS UUID),
        CAST(:workspace_id AS UUID),
        :action_type,
        CAST(:actor_id     AS UUID),
        :actor_role,
        CAST(:previous_data AS JSONB),
        CAST(:new_data      AS JSONB),
        :occurred_at,
        CAST(:request_id   AS UUID),
        :source_ip
    )
    RETURNING log_id::text
"""

# ---------------------------------------------------------------------------
# SQL constants — TenantRepository
# ---------------------------------------------------------------------------

_FIND_TENANT_BY_ID_SQL = """
    SELECT
        tenant_id::text,
        status::text
    FROM control.tenants
    WHERE tenant_id = CAST(:tenant_id AS UUID)
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _escape_ilike(term: str) -> str:
    """
    Escape ILIKE metacharacters (%, _, \\) in *term* so that the string is
    matched literally.  The escaped value is then wrapped in % for a
    contains search.
    """
    # Escape backslash first to avoid double-escaping
    term = term.replace("\\", "\\\\")
    term = term.replace("%", "\\%")
    term = term.replace("_", "\\_")
    return f"%{term}%"


def _row_to_workspace(row) -> Workspace:
    """Convert a SQLAlchemy ``Row`` from a workspaces query to a ``Workspace``."""
    return Workspace(
        workspace_id=uuid.UUID(row.workspace_id),
        tenant_id=uuid.UUID(row.tenant_id),
        workspace_name=row.workspace_name,
        workspace_name_lower=row.workspace_name_lower,
        workspace_slug=row.workspace_slug,
        description=row.description,
        default_timezone=row.default_timezone,
        status=WorkspaceStatus(row.status),
        status_reason=row.status_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=uuid.UUID(row.created_by),
        updated_by=uuid.UUID(row.updated_by),
        version=row.version,
    )


def _row_to_audit_log(row) -> WorkspaceAuditLog:
    """Convert a SQLAlchemy ``Row`` from an audit log query to a ``WorkspaceAuditLog``."""
    return WorkspaceAuditLog(
        log_id=uuid.UUID(row.log_id),
        tenant_id=uuid.UUID(row.tenant_id),
        workspace_id=uuid.UUID(row.workspace_id),
        action_type=row.action_type,
        actor_id=uuid.UUID(row.actor_id),
        actor_role=row.actor_role,
        previous_data=row.previous_data,  # psycopg2 auto-decodes JSONB → dict | None
        new_data=row.new_data,  # psycopg2 auto-decodes JSONB → dict
        occurred_at=row.occurred_at,
        request_id=uuid.UUID(row.request_id) if row.request_id else None,
        source_ip=row.source_ip,
    )


def _strip_audit_keys(data: dict | None) -> str | None:
    """
    Remove internal keys (``workspace_name_lower``, ``version``) from an
    audit payload dict and return a JSON string suitable for a CAST(:x AS JSONB)
    parameter.  Returns ``None`` (which binds to SQL NULL) when *data* is None.
    """
    if data is None:
        return None
    cleaned = {k: v for k, v in data.items() if k not in _AUDIT_STRIPPED_KEYS}
    # Serialise UUID and datetime objects to strings for JSON
    return json.dumps(cleaned, default=str)


# ---------------------------------------------------------------------------
# WorkspaceRepository
# ---------------------------------------------------------------------------


class WorkspaceRepository:
    """
    All persistence operations for ``control.workspaces``.

    Methods are stateless; the SQLAlchemy ``Session`` is passed per call so
    that the service layer controls transaction boundaries.
    """

    # ------------------------------------------------------------------
    # insert_workspace
    # ------------------------------------------------------------------

    def insert_workspace(self, db: Session, workspace: Workspace) -> Workspace:
        """
        Insert a new workspace row.

        * Generates a UUID v4 ``workspace_id``.
        * Sets ``version = 0``, ``created_at = updated_at = utcnow()``.
        * Catches unique-constraint violations and raises ``DuplicateNameError``
          or ``DuplicateSlugError`` by inspecting the constraint name.

        Returns the inserted ``Workspace`` with all fields populated from the
        RETURNING clause.

        Raises
        ------
        DuplicateNameError
            When ``uq_workspaces_name_lower_per_tenant`` fires.
        DuplicateSlugError
            When ``uq_workspaces_slug_per_tenant`` fires.
        """
        from psycopg2.errors import (
            UniqueViolation,  # local import; psycopg2 optional at module level
        )

        now = datetime.now(UTC)
        new_id = uuid.uuid4()

        params = {
            "workspace_id": str(new_id),
            "tenant_id": str(workspace.tenant_id),
            "workspace_name": workspace.workspace_name,
            "workspace_slug": workspace.workspace_slug,
            "description": workspace.description,
            "default_timezone": workspace.default_timezone,
            "status": workspace.status.value,
            "status_reason": workspace.status_reason,
            "created_at": now,
            "updated_at": now,
            "created_by": str(workspace.created_by),
            "updated_by": str(workspace.updated_by),
            "version": 0,
        }

        try:
            result = db.execute(text(_INSERT_WORKSPACE_SQL), params)
            row = result.fetchone()
        except Exception as exc:
            # Unwrap SQLAlchemy wrapper to reach the psycopg2 cause
            cause = getattr(exc, "__cause__", None) or exc
            if isinstance(cause, UniqueViolation):
                constraint = _extract_constraint_name(str(cause))
                if constraint == _CONSTRAINT_DUPLICATE_NAME:
                    raise DuplicateNameError(
                        f"Workspace name already exists within tenant {workspace.tenant_id}"
                    ) from exc
                if constraint == _CONSTRAINT_DUPLICATE_SLUG:
                    raise DuplicateSlugError(
                        f"Workspace slug already exists within tenant {workspace.tenant_id}"
                    ) from exc
                # Unknown unique violation — re-raise as-is
            raise

        return _row_to_workspace(row)

    # ------------------------------------------------------------------
    # find_by_id
    # ------------------------------------------------------------------

    def find_by_id(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID | None = None,
        *,
        for_update: bool = False,
    ) -> Workspace:
        """
        Fetch a single workspace row by primary key.

        When ``tenant_id`` is provided (non-None), cross-tenant isolation is
        enforced via ``AND tenant_id = :tenant_id``; a ``workspace_id``
        belonging to another tenant returns zero rows and raises
        ``WorkspaceNotFoundError``.

        When ``tenant_id`` is None (Platform Operator path — F003), the
        tenant filter is omitted and the workspace is fetched regardless of
        tenant ownership.

        Parameters
        ----------
        tenant_id:
            Tenant scope for the query.  Pass None for Platform Operator
            reads that must cross tenant boundaries.
        for_update:
            When ``True``, appends ``FOR UPDATE`` to the SELECT so that the
            row is locked for the remainder of the current transaction.

        Raises
        ------
        WorkspaceNotFoundError
            When zero rows are returned.
        """
        if tenant_id is None:
            sql = _FIND_BY_ID_ANY_TENANT_SQL
            if for_update:
                sql = sql + "\nFOR UPDATE"
            params = {"workspace_id": str(workspace_id)}
        else:
            sql = _FIND_BY_ID_BASE_SQL
            if for_update:
                sql = sql + "\nFOR UPDATE"
            params = {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)}

        result = db.execute(text(sql), params)
        row = result.fetchone()
        if row is None:
            raise WorkspaceNotFoundError(
                f"Workspace {workspace_id} not found"
                + (f" in tenant {tenant_id}" if tenant_id is not None else "")
            )
        return _row_to_workspace(row)

    # ------------------------------------------------------------------
    # find_by_id_any_tenant  (Platform Operator reads — P08)
    # ------------------------------------------------------------------

    def find_by_id_any_tenant(
        self,
        db: Session,
        workspace_id: uuid.UUID,
    ) -> Workspace:
        """
        Fetch a workspace row by primary key with no tenant filter.

        Used exclusively by Platform Admin/Viewer read paths that are
        authorised to access workspaces across all Tenants (TDD §5.4, P08).

        Raises
        ------
        WorkspaceNotFoundError
            When zero rows are returned.
        """
        result = db.execute(
            text(_FIND_BY_ID_ANY_TENANT_SQL),
            {"workspace_id": str(workspace_id)},
        )
        row = result.fetchone()
        if row is None:
            raise WorkspaceNotFoundError(f"Workspace {workspace_id} not found")
        return _row_to_workspace(row)

    # ------------------------------------------------------------------
    # update_workspace
    # ------------------------------------------------------------------

    def update_workspace(self, db: Session, workspace: Workspace) -> Workspace:
        """
        Update all mutable fields of an existing workspace row.

        ``workspace.version`` should already have been incremented by the
        service layer before calling this method.

        Returns the updated ``Workspace`` populated from the RETURNING clause.

        Raises
        ------
        WorkspaceNotFoundError
            When the UPDATE returns zero rows (workspace deleted concurrently,
            or cross-tenant guard fired).
        """
        params = {
            "workspace_id": str(workspace.workspace_id),
            "tenant_id": str(workspace.tenant_id),
            "workspace_name": workspace.workspace_name,
            "workspace_slug": workspace.workspace_slug,
            "description": workspace.description,
            "default_timezone": workspace.default_timezone,
            "status": workspace.status.value,
            "status_reason": workspace.status_reason,
            "updated_at": workspace.updated_at,
            "updated_by": str(workspace.updated_by),
            "version": workspace.version,
        }

        result = db.execute(text(_UPDATE_WORKSPACE_SQL), params)
        row = result.fetchone()
        if row is None:
            raise WorkspaceNotFoundError(
                f"Workspace {workspace.workspace_id} not found in tenant "
                f"{workspace.tenant_id} during update"
            )
        return _row_to_workspace(row)

    # ------------------------------------------------------------------
    # list_workspaces
    # ------------------------------------------------------------------

    def list_workspaces(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        *,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 25,
        restrict_to_user_id: uuid.UUID | None = None,
    ) -> tuple[list[Workspace], int]:
        """
        Return a paginated list of workspaces for *tenant_id*.

        Parameters
        ----------
        include_archived:
            When ``False`` (default), only ``active`` rows are returned.
        q:
            Search string applied as ILIKE against both ``workspace_name``
            and ``workspace_slug``.  Metacharacters are escaped.
            Whitespace-only *q* after strip is treated as absent.
        sort_by:
            Must be a key in ``_SORT_COLUMN_ALLOWLIST``; validated at call
            site by the service layer before reaching the repository.
        sort_dir:
            ``'asc'`` or ``'desc'``; validated at call site.

        Returns
        -------
        (workspaces, total_count) where ``total_count`` is the unfiltered
        count matching all WHERE predicates (ignoring LIMIT/OFFSET).

        Raises
        ------
        ValueError
            If *sort_by* is not in the allowlist (programmer error; the
            service layer should have validated this first).
        """
        # Validate sort_by against compile-time allowlist (A-12)
        if sort_by not in _SORT_COLUMN_ALLOWLIST:
            raise ValueError(
                f"sort_by '{sort_by}' is not in the allowlist: {list(_SORT_COLUMN_ALLOWLIST)}"
            )
        safe_sort_col = _SORT_COLUMN_ALLOWLIST[sort_by]

        # Validate sort_dir against compile-time allowlist
        if sort_dir not in ("asc", "desc"):
            raise ValueError(f"sort_dir must be 'asc' or 'desc', got '{sort_dir}'")
        safe_sort_dir = sort_dir  # validated; safe to interpolate

        # Build WHERE predicates and params
        params: dict = {"tenant_id": str(tenant_id)}
        where_clauses = ["w.tenant_id = CAST(:tenant_id AS UUID)"]

        if not include_archived:
            where_clauses.append("w.status = 'active'")

        # BUG: non-operator users should only see workspaces where they hold a
        # role assignment. Platform operators and tenant admins bypass this.
        if restrict_to_user_id is not None:
            params["restrict_user_id"] = str(restrict_to_user_id)
            where_clauses.append(
                "EXISTS (SELECT 1 FROM control.workspace_role_assignments wra "
                "WHERE wra.workspace_id = w.workspace_id "
                "AND wra.user_id = CAST(:restrict_user_id AS UUID))"
            )

        # Apply ILIKE search after escaping metacharacters
        effective_q = (q or "").strip()
        if effective_q:
            params["q_pattern"] = _escape_ilike(effective_q)
            where_clauses.append(
                "(w.workspace_name ILIKE :q_pattern ESCAPE '\\'"
                " OR w.workspace_slug ILIKE :q_pattern ESCAPE '\\')"
            )

        where_sql = " AND ".join(where_clauses)

        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        # Single query: data page + total count via window function (TDD §11.4)
        sql = f"""
            SELECT
                w.workspace_id::text,
                w.tenant_id::text,
                w.workspace_name,
                w.workspace_name_lower,
                w.workspace_slug,
                w.description,
                w.default_timezone,
                w.status::text,
                w.status_reason,
                w.created_at,
                w.updated_at,
                w.created_by::text,
                w.updated_by::text,
                w.version,
                COUNT(*) OVER () AS total_count
            FROM control.workspaces w
            WHERE {where_sql}
            ORDER BY {safe_sort_col} {safe_sort_dir}
            LIMIT :limit OFFSET :offset
        """  # noqa: S608 — only safe_sort_col/dir (allowlist-validated) interpolated

        rows = db.execute(text(sql), params).fetchall()

        if not rows:
            # No rows returned — need a separate count to distinguish
            # "zero results" from "page beyond last page"
            count_sql = f"SELECT COUNT(*) AS cnt FROM control.workspaces w WHERE {where_sql}"
            count_result = db.execute(
                text(count_sql),
                {k: v for k, v in params.items() if k not in ("limit", "offset")},
            ).fetchone()
            total = count_result.cnt if count_result else 0
            return [], total

        total = rows[0].total_count
        workspaces = [_row_to_workspace(r) for r in rows]
        return workspaces, total

    # ------------------------------------------------------------------
    # count_active_workspaces
    # ------------------------------------------------------------------

    def count_active_workspaces(self, db: Session, tenant_id: uuid.UUID) -> int:
        """
        Return the count of ``status = 'active'`` rows for *tenant_id*.

        Used inside the archival transaction to detect the last-workspace
        condition (TDD §5.2 Flow C step 6).
        """
        result = db.execute(text(_COUNT_ACTIVE_SQL), {"tenant_id": str(tenant_id)})
        row = result.fetchone()
        return row.cnt if row else 0

    # ------------------------------------------------------------------
    # bulk_archive_by_tenant
    # ------------------------------------------------------------------

    def bulk_archive_by_tenant(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        status_reason: str,
        updated_by: uuid.UUID,
        now: datetime,
    ) -> list:
        """Archive every non-archived workspace that belongs to *tenant_id*.

        Executes a single UPDATE … RETURNING so the operation is atomic within
        the caller's transaction.  Returns a list of workspace_id strings for
        the rows that were updated (may be empty if all workspaces were already
        archived).

        The caller is responsible for committing the transaction.
        """
        result = db.execute(
            text(_BULK_ARCHIVE_BY_TENANT_SQL),
            {
                "tenant_id": str(tenant_id),
                "status_reason": status_reason,
                "updated_at": now,
                "updated_by": str(updated_by),
            },
        )
        return [row.workspace_id for row in result.fetchall()]

    # ------------------------------------------------------------------
    # bulk_suspend_by_tenant
    # ------------------------------------------------------------------

    def bulk_suspend_by_tenant(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        status_reason: str,
        updated_by: uuid.UUID,
        now: datetime,
    ) -> list:
        """Suspend every active workspace that belongs to *tenant_id*.

        Cascade-suspend triggered when the parent tenant transitions to
        ``suspended``.  Only ``status='active'`` rows are touched; archived
        and already-suspended workspaces are left as-is.

        Returns a list of workspace_id strings for the rows that were updated.
        The caller is responsible for committing the transaction.
        """
        result = db.execute(
            text(_BULK_SUSPEND_BY_TENANT_SQL),
            {
                "tenant_id": str(tenant_id),
                "status_reason": status_reason,
                "updated_at": now,
                "updated_by": str(updated_by),
            },
        )
        return [row.workspace_id for row in result.fetchall()]

    # ------------------------------------------------------------------
    # bulk_activate_by_tenant
    # ------------------------------------------------------------------

    def bulk_activate_by_tenant(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        updated_by: uuid.UUID,
        now: datetime,
    ) -> list:
        """Reactivate every suspended workspace that belongs to *tenant_id*.

        Cascade-activate triggered when a previously-suspended tenant
        transitions back to ``active``.  Only ``status='suspended'`` rows are
        touched; archived workspaces remain archived.

        Returns a list of workspace_id strings for the rows that were updated.
        The caller is responsible for committing the transaction.
        """
        result = db.execute(
            text(_BULK_ACTIVATE_BY_TENANT_SQL),
            {
                "tenant_id": str(tenant_id),
                "updated_at": now,
                "updated_by": str(updated_by),
            },
        )
        return [row.workspace_id for row in result.fetchall()]


# ---------------------------------------------------------------------------
# AuditLogWriter
# ---------------------------------------------------------------------------


class AuditLogWriter:
    """
    Append-only writer for ``control.workspace_audit_logs``.

    Never issues UPDATE or DELETE (TDD §9.3 / §5.1).
    Strips ``workspace_name_lower`` and ``version`` from ``new_data`` and
    ``previous_data`` before writing.

    Raises
    ------
    AuditWriteFailedError
        On any database exception during the INSERT.
    """

    def write(self, db: Session, entry: WorkspaceAuditLog) -> None:
        """
        Insert one audit log row.

        Parameters
        ----------
        db:
            Active SQLAlchemy session; the INSERT participates in an existing
            transaction when called from the service layer.
        entry:
            Domain model instance.  ``log_id`` may be ``None``; it is set
            to a new UUID v4 inside this method.
        """
        log_id = entry.log_id or uuid.uuid4()

        params = {
            "log_id": str(log_id),
            "tenant_id": str(entry.tenant_id),
            "workspace_id": str(entry.workspace_id),
            "action_type": entry.action_type,
            "actor_id": str(entry.actor_id),
            "actor_role": entry.actor_role,
            "previous_data": _strip_audit_keys(entry.previous_data),
            "new_data": _strip_audit_keys(entry.new_data),
            "occurred_at": entry.occurred_at,
            "request_id": str(entry.request_id) if entry.request_id else None,
            "source_ip": entry.source_ip,
        }

        try:
            db.execute(text(_INSERT_AUDIT_LOG_SQL), params)
        except Exception as exc:
            logger.error(
                "AuditLogWriter failed for workspace_id=%s action_type=%s: %s",
                entry.workspace_id,
                entry.action_type,
                exc,
            )
            raise AuditWriteFailedError(
                f"Failed to write audit log for workspace {entry.workspace_id}"
            ) from exc


# ---------------------------------------------------------------------------
# AuditLogRepository (read-only — P08)
# ---------------------------------------------------------------------------

# Valid action_type values per TDD §3.1.2
VALID_AUDIT_ACTION_TYPES: frozenset = frozenset(
    {
        "workspace_created",
        "workspace_metadata_updated",
        "workspace_archived",
        "workspace_restored",
        "workspace_settings_updated",  # F003
    }
)


class AuditLogRepository:
    """
    Read-only access to ``control.workspace_audit_logs`` for the list endpoint.

    Never issues UPDATE or DELETE (TDD §9.3).  All SELECT queries include
    ``ORDER BY occurred_at DESC`` per TDD §4.8.

    ``tenant_id`` filtering is applied when the caller provides a value;
    Platform Operators pass ``tenant_id=None`` to skip tenant scoping and
    rely solely on ``workspace_id`` for isolation.
    """

    def list_audit_logs(
        self,
        db: Session,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID | None,
        *,
        action_type: str | None = None,
        actor_id: uuid.UUID | None = None,
        from_date=None,
        to_date=None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[WorkspaceAuditLog], int]:
        """
        Return a paginated list of audit log entries for *workspace_id*.

        Parameters
        ----------
        workspace_id:
            Scope to this workspace.
        tenant_id:
            When provided, adds ``AND tenant_id = :tenant_id`` for
            cross-tenant isolation (WA use case).  Pass ``None`` for
            Platform Operators (all-tenant access).
        action_type:
            Filter by exact ``action_type`` value.
        actor_id:
            Filter by exact ``actor_id`` UUID.
        from_date:
            Lower bound on ``occurred_at`` (inclusive).
        to_date:
            Upper bound on ``occurred_at`` (inclusive).
        page / page_size:
            Pagination; page is 1-based.

        Returns
        -------
        (entries, total_count)
        """
        params: dict = {"workspace_id": str(workspace_id)}
        where_clauses = ["al.workspace_id = CAST(:workspace_id AS UUID)"]

        if tenant_id is not None:
            params["tenant_id"] = str(tenant_id)
            where_clauses.append("al.tenant_id = CAST(:tenant_id AS UUID)")

        if action_type is not None:
            params["action_type"] = action_type
            where_clauses.append("al.action_type = :action_type")

        if actor_id is not None:
            params["actor_id"] = str(actor_id)
            where_clauses.append("al.actor_id = CAST(:actor_id AS UUID)")

        if from_date is not None:
            params["from_date"] = from_date
            where_clauses.append("al.occurred_at >= :from_date")

        if to_date is not None:
            params["to_date"] = to_date
            where_clauses.append("al.occurred_at <= :to_date")

        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        sql = f"""
            SELECT
                {_AUDIT_SELECT_COLS},
                COUNT(*) OVER () AS total_count
            FROM control.workspace_audit_logs al
            WHERE {where_sql}
            ORDER BY al.occurred_at DESC
            LIMIT :limit OFFSET :offset
        """  # noqa: S608 — no user-supplied identifiers interpolated; WHERE built from compile-time strings

        rows = db.execute(text(sql), params).fetchall()

        if not rows:
            count_sql = (
                f"SELECT COUNT(*) AS cnt FROM control.workspace_audit_logs al WHERE {where_sql}"
            )
            count_result = db.execute(
                text(count_sql),
                {k: v for k, v in params.items() if k not in ("limit", "offset")},
            ).fetchone()
            total = count_result.cnt if count_result else 0
            return [], total

        total = rows[0].total_count
        entries = [_row_to_audit_log(r) for r in rows]
        return entries, total


# ---------------------------------------------------------------------------
# TenantRepository (read-only)
# ---------------------------------------------------------------------------


class TenantRepository:
    """
    Read-only access to ``control.tenants``.

    Only the ``tenant_id`` and ``status`` columns are consumed by the
    Workspace service layer; the full tenant row is not needed here.

    Raises
    ------
    TenantNotFoundError
        When the tenant row is absent.
    """

    def find_tenant_by_id(self, db: Session, tenant_id: uuid.UUID) -> dict:
        """
        Return a minimal dict ``{"tenant_id": UUID, "status": str}`` for
        the given *tenant_id*.

        Non-locking SELECT — no ``FOR UPDATE`` (TDD §5.2 Flow A note).

        Raises
        ------
        TenantNotFoundError
            When zero rows are returned.
        """
        result = db.execute(text(_FIND_TENANT_BY_ID_SQL), {"tenant_id": str(tenant_id)})
        row = result.fetchone()
        if row is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        return {
            "tenant_id": uuid.UUID(row.tenant_id),
            "status": row.status,
        }


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------


def _extract_constraint_name(pg_error_message: str) -> str | None:
    """
    Extract the constraint name from a psycopg2 ``UniqueViolation`` error
    message string.

    psycopg2 includes the constraint name in the ``pgcode``/``pgerror``
    message in a format like:
        'unique constraint "uq_workspaces_name_lower_per_tenant"'

    Returns ``None`` if the name cannot be parsed.
    """
    import re

    match = re.search(r'unique constraint "([^"]+)"', pg_error_message, re.IGNORECASE)
    if match:
        return match.group(1)
    return None
