"""
F004 — Data Source repository layer
=====================================

Provides:
* ``DataSourceRepository`` — CRUD operations against ``control.data_sources``

Design notes
------------
* All SQL is parameterised via SQLAlchemy ``text()`` with named bind params.
  String interpolation into SQL text is NEVER used for user data.
* Every query includes ``AND workspace_id = :workspace_id`` for cross-tenant
  isolation (TDD §12.4).
* ``SELECT FOR UPDATE`` is applied in ``find_by_id`` when ``for_update=True``
  enabling optimistic locking in mutation flows.
* ``count_active_datasets`` gracefully handles a missing ``control.datasets``
  table (F005 not yet built) by catching UndefinedTable and returning 0.
* The UNIQUE index ``uq_data_source_name_workspace`` uses ``lower(source_name)``
  — on IntegrityError the repository raises ``DuplicateSourceNameError``.
"""

from __future__ import annotations

import builtins
import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.data_sources.models import (
    DataSource,
    DataSourceStatus,
    TestStatus,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class DataSourceNotFoundError(Exception):
    """Raised when no data source with the given ID exists in the workspace."""


class DuplicateSourceNameError(Exception):
    """Raised when source_name (case-insensitive) already exists in workspace."""


class DataSourceArchivedError(Exception):
    """Raised when a mutating operation is attempted on an archived data source."""


# ─────────────────────────────────────────────────────────────────────────────
# SQL constants
# ─────────────────────────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT INTO control.data_sources (
    data_source_id, workspace_id, tenant_id,
    source_name, source_type, connection_mode, environment,
    description, credential_reference,
    status, last_test_status,
    created_at, updated_at, created_by
) VALUES (
    :data_source_id, :workspace_id, :tenant_id,
    :source_name, :source_type, :connection_mode, :environment,
    :description, :credential_reference,
    'active', 'untested',
    :now, :now, :created_by
)
RETURNING data_source_id, created_at, updated_at
"""

_SELECT_BY_ID_SQL = """
SELECT
    data_source_id, workspace_id, tenant_id,
    source_name, source_type, connection_mode, environment,
    description, credential_reference,
    status, last_test_status, last_tested_at,
    created_at, updated_at, created_by, updated_by,
    archived_at, archived_by
FROM control.data_sources
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND (
        workspace_id = CAST(:workspace_id AS UUID)
        OR (
            workspace_id IS NULL
            AND data_source_id IN (
                SELECT connection_id
                FROM control.workspace_connection_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
            )
        )
  )
"""

_LIST_SQL = """
SELECT
    data_source_id, workspace_id, tenant_id,
    source_name, source_type, connection_mode, environment,
    description, credential_reference,
    status, last_test_status, last_tested_at,
    created_at, updated_at, created_by, updated_by,
    archived_at, archived_by
FROM control.data_sources
WHERE tenant_id = CAST(:tenant_id AS UUID)
  AND (
        workspace_id = CAST(:workspace_id AS UUID)
        OR (
            workspace_id IS NULL
            AND data_source_id IN (
                SELECT connection_id
                FROM control.workspace_connection_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
            )
        )
  )
  AND (:status_filter IS NULL OR status = :status_filter)
  AND (:source_type_filter IS NULL OR source_type = :source_type_filter)
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset
"""

_COUNT_SQL = """
SELECT COUNT(*)
FROM control.data_sources
WHERE tenant_id = CAST(:tenant_id AS UUID)
  AND (
        workspace_id = CAST(:workspace_id AS UUID)
        OR (
            workspace_id IS NULL
            AND data_source_id IN (
                SELECT connection_id
                FROM control.workspace_connection_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
            )
        )
  )
  AND (:status_filter IS NULL OR status = :status_filter)
  AND (:source_type_filter IS NULL OR source_type = :source_type_filter)
"""

_UPDATE_METADATA_SQL = """
UPDATE control.data_sources
SET
    source_name          = COALESCE(:source_name,      source_name),
    connection_mode      = COALESCE(:connection_mode,  connection_mode),
    environment          = COALESCE(:environment,      environment),
    description          = COALESCE(:description,      description),
    updated_at           = :now,
    updated_by           = :updated_by
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND workspace_id   = CAST(:workspace_id   AS UUID)
RETURNING updated_at
"""

_UPDATE_CREDENTIAL_REF_SQL = """
UPDATE control.data_sources
SET
    credential_reference = CAST(:credential_reference AS UUID),
    last_test_status     = 'untested',
    last_tested_at       = NULL,
    updated_at           = :now,
    updated_by           = :updated_by
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND (
        workspace_id = CAST(:workspace_id AS UUID)
        OR (
            workspace_id IS NULL
            AND data_source_id IN (
                SELECT connection_id
                FROM control.workspace_connection_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
            )
        )
  )
RETURNING updated_at
"""

_UPDATE_TEST_STATUS_SQL = """
UPDATE control.data_sources
SET
    last_test_status = :last_test_status,
    last_tested_at   = :last_tested_at,
    updated_at       = :now
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND (
        workspace_id = CAST(:workspace_id AS UUID)
        OR (
            workspace_id IS NULL
            AND data_source_id IN (
                SELECT connection_id
                FROM control.workspace_connection_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
            )
        )
  )
"""

_ARCHIVE_SQL = """
UPDATE control.data_sources
SET
    status      = 'archived',
    archived_at = :now,
    archived_by = :archived_by,
    updated_at  = :now,
    updated_by  = :archived_by
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND workspace_id   = CAST(:workspace_id   AS UUID)
  AND status         = 'active'
RETURNING updated_at
"""

_RESTORE_SQL = """
UPDATE control.data_sources
SET
    status      = 'active',
    archived_at = NULL,
    archived_by = NULL,
    updated_at  = :now,
    updated_by  = :restored_by
WHERE data_source_id = CAST(:data_source_id AS UUID)
  AND workspace_id   = CAST(:workspace_id   AS UUID)
  AND status         = 'archived'
RETURNING updated_at
"""

_CONSTRAINT_DUPLICATE_NAME = "uq_data_source_name_workspace"


# ─────────────────────────────────────────────────────────────────────────────
# Row → domain model
# ─────────────────────────────────────────────────────────────────────────────


def _row_to_data_source(row) -> DataSource:
    return DataSource(
        data_source_id=row[0],
        workspace_id=row[1],
        tenant_id=row[2],
        source_name=row[3],
        source_type=row[4],
        connection_mode=row[5],
        environment=row[6],
        description=row[7],
        credential_reference=row[8],
        status=DataSourceStatus(row[9]),
        last_test_status=TestStatus(row[10]),
        last_tested_at=row[11],
        created_at=row[12],
        updated_at=row[13],
        created_by=row[14],
        updated_by=row[15],
        archived_at=row[16],
        archived_by=row[17],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────────


class DataSourceRepository:
    """
    All SQL operations against ``control.data_sources``.

    Every public method accepts a SQLAlchemy ``Session`` as its first
    argument so the service layer can wrap multiple ops in one transaction.
    """

    # ── create ──────────────────────────────────────────────────────────────

    def create(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        source_name: str,
        source_type: str,
        connection_mode: str,
        environment: str,
        created_by: UUID,
        description: str | None = None,
        credential_reference: UUID | None = None,
    ) -> DataSource:
        """Insert a new data source row and return the resulting domain model."""
        now = datetime.now(UTC)
        ds_id = uuid.uuid4()
        try:
            result = db.execute(
                text(_INSERT_SQL),
                {
                    "data_source_id": str(ds_id),
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                    "source_name": source_name,
                    "source_type": source_type,
                    "connection_mode": connection_mode,
                    "environment": environment,
                    "description": description,
                    "credential_reference": str(credential_reference)
                    if credential_reference
                    else None,
                    "now": now,
                    "created_by": str(created_by),
                },
            )
            row = result.fetchone()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            if orig and _CONSTRAINT_DUPLICATE_NAME in str(orig):
                raise DuplicateSourceNameError(
                    f"A data source named '{source_name}' already exists in this workspace."
                ) from exc
            raise

        return DataSource(
            data_source_id=row[0],
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            source_name=source_name,
            source_type=source_type,
            connection_mode=connection_mode,
            environment=environment,
            description=description,
            credential_reference=credential_reference,
            status=DataSourceStatus.active,
            last_test_status=TestStatus.untested,
            created_at=row[1],
            updated_at=row[2],
            created_by=created_by,
        )

    # ── read ────────────────────────────────────────────────────────────────

    def find_by_id(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        for_update: bool = False,
    ) -> DataSource:
        sql = _SELECT_BY_ID_SQL
        if for_update:
            sql += " FOR UPDATE"
        result = db.execute(
            text(sql),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
            },
        )
        row = result.fetchone()
        if row is None:
            raise DataSourceNotFoundError(
                f"Data source {data_source_id} not found in workspace {workspace_id}."
            )
        return _row_to_data_source(row)

    def list(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        status_filter: str | None = None,
        source_type_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[builtins.list[DataSource], int]:
        """Return (items, total_count) for pagination."""
        params = {
            "workspace_id": str(workspace_id),
            "tenant_id": str(tenant_id),
            "status_filter": status_filter,
            "source_type_filter": source_type_filter,
            "limit": limit,
            "offset": offset,
        }
        result = db.execute(text(_LIST_SQL), params)
        items = [_row_to_data_source(row) for row in result.fetchall()]

        count_result = db.execute(
            text(_COUNT_SQL),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        total = count_result.scalar()
        return items, total

    # ── update ──────────────────────────────────────────────────────────────

    def update_metadata(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        updated_by: UUID,
        source_name: str | None = None,
        connection_mode: str | None = None,
        environment: str | None = None,
        description: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        db.execute(
            text(_UPDATE_METADATA_SQL),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
                "source_name": source_name,
                "connection_mode": connection_mode,
                "environment": environment,
                "description": description,
                "now": now,
                "updated_by": str(updated_by),
            },
        )

    def update_credential_reference(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        credential_reference: UUID,
        updated_by: UUID,
    ) -> None:
        now = datetime.now(UTC)
        db.execute(
            text(_UPDATE_CREDENTIAL_REF_SQL),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
                "credential_reference": str(credential_reference),
                "now": now,
                "updated_by": str(updated_by),
            },
        )

    def update_test_status(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        last_test_status: str,
        last_tested_at: datetime,
    ) -> None:
        now = datetime.now(UTC)
        db.execute(
            text(_UPDATE_TEST_STATUS_SQL),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
                "last_test_status": last_test_status,
                "last_tested_at": last_tested_at,
                "now": now,
            },
        )

    # ── archive / restore ───────────────────────────────────────────────────

    def archive(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        archived_by: UUID,
    ) -> None:
        now = datetime.now(UTC)
        result = db.execute(
            text(_ARCHIVE_SQL),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
                "now": now,
                "archived_by": str(archived_by),
            },
        )
        if result.rowcount == 0:
            # Either not found or already archived
            ds = self.find_by_id(db, data_source_id=data_source_id, workspace_id=workspace_id)
            if ds.status == DataSourceStatus.archived:
                raise DataSourceArchivedError(f"Data source {data_source_id} is already archived.")
            raise DataSourceNotFoundError(
                f"Data source {data_source_id} not found in workspace {workspace_id}."
            )

    def restore(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        workspace_id: UUID,
        restored_by: UUID,
    ) -> None:
        now = datetime.now(UTC)
        result = db.execute(
            text(_RESTORE_SQL),
            {
                "data_source_id": str(data_source_id),
                "workspace_id": str(workspace_id),
                "now": now,
                "restored_by": str(restored_by),
            },
        )
        if result.rowcount == 0:
            ds = self.find_by_id(db, data_source_id=data_source_id, workspace_id=workspace_id)
            if ds.status == DataSourceStatus.active:
                raise Exception(f"Data source {data_source_id} is already active.")
            raise DataSourceNotFoundError(
                f"Data source {data_source_id} not found in workspace {workspace_id}."
            )

    # ── helpers ─────────────────────────────────────────────────────────────

    def count_active_datasets(
        self,
        db: Session,
        *,
        data_source_id: UUID,
    ) -> int:
        """
        Count active datasets referencing this data source.
        Returns 0 if control.datasets table does not yet exist (F005 pending).
        Uses a savepoint so that a missing-table error doesn't abort the outer transaction.
        """
        sp = db.begin_nested()
        try:
            result = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM control.datasets
                    WHERE data_source_id = CAST(:data_source_id AS UUID)
                      AND status = 'active'
                    """
                ),
                {"data_source_id": str(data_source_id)},
            )
            count = result.scalar() or 0
            sp.commit()
            return count
        except Exception as exc:
            sp.rollback()
            # Handle missing table gracefully (F005 not yet created)
            if "datasets" in str(exc).lower() or "undefined" in str(exc).lower():
                logger.debug(
                    "control.datasets table not found (F005 pending) — returning 0 for dataset count"
                )
                return 0
            raise
