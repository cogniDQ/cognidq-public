"""
F130 — TenantConnectionRepository
===================================
Raw SQL repository for tenant-scoped data source (Connection) operations.

All queries are scoped to tenant_id to enforce cross-tenant isolation.
Credentials are never selected.
"""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.connections.errors import (
    CONNECTION_IN_USE,
    CONNECTION_NOT_FOUND,
    DUPLICATE_CONNECTION_NAME,
    IMMUTABLE_FIELD,
    INVALID_WORKSPACE,
    ConnectionAPIError,
)

logger = logging.getLogger(__name__)

# Columns returned in list/get; credentials are never included.
_CONNECTION_COLS = """
    ds.data_source_id,
    ds.tenant_id,
    ds.workspace_id,
    ds.source_name,
    ds.source_type,
    ds.connection_mode,
    ds.environment,
    ds.description,
    ds.status,
    ds.credential_reference,
    ds.created_at,
    ds.updated_at,
    ds.created_by,
    ds.updated_by
"""

_IMMUTABLE_FIELDS = frozenset({"source_type", "connection_mode"})


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


class TenantConnectionRepository:
    # ─────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────

    def list_by_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status_filter: str | None = None,
        workspace_id_filter: UUID | None = None,
    ) -> tuple[list[dict], int]:
        """Return paginated connections scoped to tenant_id."""
        where_clauses = ["ds.tenant_id = CAST(:tenant_id AS UUID)"]
        params: dict[str, Any] = {"tenant_id": str(tenant_id)}

        if search:
            where_clauses.append("ds.source_name ILIKE :search")
            params["search"] = f"%{search}%"

        if status_filter:
            where_clauses.append("ds.status = :status_filter")
            params["status_filter"] = status_filter

        if workspace_id_filter:
            where_clauses.append(
                "EXISTS ("
                "  SELECT 1 FROM control.workspace_connection_assignments wca"
                "  WHERE wca.connection_id = ds.data_source_id"
                "    AND wca.workspace_id = CAST(:wid_filter AS UUID)"
                ")"
            )
            params["wid_filter"] = str(workspace_id_filter)

        where_sql = " AND ".join(where_clauses)

        count_row = db.execute(
            text(f"SELECT COUNT(*) FROM control.data_sources ds WHERE {where_sql}"),
            params,
        ).fetchone()
        total = count_row[0] if count_row else 0

        offset = (page - 1) * page_size
        rows = db.execute(
            text(
                f"SELECT {_CONNECTION_COLS} "
                f"FROM control.data_sources ds "
                f"WHERE {where_sql} "
                f"ORDER BY ds.source_name ASC "
                f"LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

        return [_row_to_dict(r) for r in rows], total

    def get_by_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> dict | None:
        """Return a single connection or None."""
        row = db.execute(
            text(
                f"SELECT {_CONNECTION_COLS} "
                f"FROM control.data_sources ds "
                f"WHERE ds.tenant_id = CAST(:tenant_id AS UUID) "
                f"  AND ds.data_source_id = CAST(:connection_id AS UUID)"
            ),
            {"tenant_id": str(tenant_id), "connection_id": str(connection_id)},
        ).fetchone()
        return _row_to_dict(row) if row else None

    # ─────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────

    def create(
        self,
        db: Session,
        tenant_id: UUID,
        payload: dict,
        actor_id: UUID,
    ) -> dict:
        """Insert a tenant-owned connection row.

        ``workspace_id`` is left NULL — the connection is owned by the tenant
        and access is controlled through workspace_connection_assignments.
        Credentials and assignments are persisted separately by the service.
        """
        import uuid as _uuid
        from datetime import datetime

        new_id = _uuid.uuid4()
        now = datetime.now(UTC)
        try:
            db.execute(
                text(
                    "INSERT INTO control.data_sources ("
                    "  data_source_id, tenant_id, workspace_id, source_name,"
                    "  source_type, connection_mode, environment, description,"
                    "  status, last_test_status,"
                    "  created_at, updated_at, created_by, updated_by"
                    ") VALUES ("
                    "  CAST(:id AS UUID), CAST(:tenant_id AS UUID), NULL,"
                    "  :source_name, :source_type, :connection_mode,"
                    "  :environment, :description, 'active', 'untested',"
                    "  :now, :now,"
                    "  CAST(:actor_id AS UUID), CAST(:actor_id AS UUID)"
                    ")"
                ),
                {
                    "id": str(new_id),
                    "tenant_id": str(tenant_id),
                    "source_name": payload["source_name"],
                    "source_type": payload["source_type"],
                    "connection_mode": payload["connection_mode"],
                    "environment": payload["environment"],
                    "description": payload.get("description"),
                    "now": now,
                    "actor_id": str(actor_id),
                },
            )
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            exc_str = str(exc.orig or exc).lower()
            if "source_name" in exc_str or "unique" in exc_str:
                raise ConnectionAPIError(
                    status_code=status.HTTP_409_CONFLICT,
                    code=DUPLICATE_CONNECTION_NAME,
                    message=f"A connection named '{payload['source_name']}' already exists for this tenant.",
                )
            raise

        created = self.get_by_tenant(db, tenant_id, new_id)
        return created  # type: ignore[return-value]

    def set_credential_reference(
        self,
        db: Session,
        connection_id: UUID,
        credential_id: UUID,
        actor_id: UUID,
    ) -> None:
        from datetime import datetime

        db.execute(
            text(
                "UPDATE control.data_sources "
                "SET credential_reference = CAST(:cred_id AS UUID), "
                "    updated_at = :now, "
                "    updated_by = CAST(:actor_id AS UUID) "
                "WHERE data_source_id = CAST(:cid AS UUID)"
            ),
            {
                "cred_id": str(credential_id),
                "cid": str(connection_id),
                "now": datetime.now(UTC),
                "actor_id": str(actor_id),
            },
        )
        db.flush()

    def update(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
        patch: dict,
        actor_id: UUID,
    ) -> dict:
        """Patch mutable fields on an existing connection."""
        from datetime import datetime

        for field_name in _IMMUTABLE_FIELDS:
            if field_name in patch:
                raise ConnectionAPIError(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code=IMMUTABLE_FIELD,
                    message=f"Field '{field_name}' cannot be changed after creation.",
                    fields=[field_name],
                )

        existing = self.get_by_tenant(db, tenant_id, connection_id)
        if existing is None:
            raise ConnectionAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code=CONNECTION_NOT_FOUND,
                message="Connection not found.",
            )

        allowed = {"source_name", "environment", "description", "status"}
        set_clauses = []
        params: dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "connection_id": str(connection_id),
            "updated_at": datetime.now(UTC),
            "actor_id": str(actor_id),
        }

        for key, val in patch.items():
            if key in allowed:
                set_clauses.append(f"{key} = :{key}")
                params[key] = val

        if not set_clauses:
            return existing

        set_clauses.append("updated_at = :updated_at")
        set_clauses.append("updated_by = CAST(:actor_id AS UUID)")

        try:
            db.execute(
                text(
                    f"UPDATE control.data_sources "
                    f"SET {', '.join(set_clauses)} "
                    f"WHERE tenant_id = CAST(:tenant_id AS UUID) "
                    f"  AND data_source_id = CAST(:connection_id AS UUID)"
                ),
                params,
            )
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            exc_str = str(exc.orig or exc).lower()
            if "source_name" in exc_str or "unique" in exc_str:
                raise ConnectionAPIError(
                    status_code=status.HTTP_409_CONFLICT,
                    code=DUPLICATE_CONNECTION_NAME,
                    message="A connection with that name already exists for this tenant.",
                )
            raise

        return self.get_by_tenant(db, tenant_id, connection_id)  # type: ignore[return-value]

    def delete(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> None:
        """Delete a connection.  Raises CONNECTION_IN_USE if datasets reference it."""
        existing = self.get_by_tenant(db, tenant_id, connection_id)
        if existing is None:
            raise ConnectionAPIError(
                status_code=status.HTTP_404_NOT_FOUND,
                code=CONNECTION_NOT_FOUND,
                message="Connection not found.",
            )

        # Check for dataset references
        ref_count_row = db.execute(
            text(
                "SELECT COUNT(*) FROM control.datasets "
                "WHERE data_source_id = CAST(:connection_id AS UUID)"
            ),
            {"connection_id": str(connection_id)},
        ).fetchone()
        if ref_count_row and ref_count_row[0] > 0:
            raise ConnectionAPIError(
                status_code=status.HTTP_409_CONFLICT,
                code=CONNECTION_IN_USE,
                message="Connection is referenced by one or more datasets and cannot be deleted.",
            )

        db.execute(
            text(
                "DELETE FROM control.data_sources "
                "WHERE tenant_id = CAST(:tenant_id AS UUID) "
                "  AND data_source_id = CAST(:connection_id AS UUID)"
            ),
            {"tenant_id": str(tenant_id), "connection_id": str(connection_id)},
        )
        db.flush()

    # ─────────────────────────────────────────────
    # Workspace assignments
    # ─────────────────────────────────────────────

    def get_assignments(
        self,
        db: Session,
        connection_id: UUID,
    ) -> list[dict]:
        rows = db.execute(
            text(
                "SELECT connection_id, workspace_id, assigned_at, assigned_by "
                "FROM control.workspace_connection_assignments "
                "WHERE connection_id = CAST(:connection_id AS UUID) "
                "ORDER BY assigned_at ASC"
            ),
            {"connection_id": str(connection_id)},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def replace_assignments(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
        workspace_ids: list[UUID],
        actor_id: UUID,
    ) -> list[dict]:
        """Replace all workspace assignments for a connection.

        Validates each workspace_id belongs to the same tenant before writing.
        """
        from datetime import datetime

        # Validate workspaces belong to tenant
        for wid in workspace_ids:
            row = db.execute(
                text(
                    "SELECT 1 FROM control.workspaces "
                    "WHERE workspace_id = CAST(:wid AS UUID) "
                    "  AND tenant_id = CAST(:tenant_id AS UUID)"
                ),
                {"wid": str(wid), "tenant_id": str(tenant_id)},
            ).fetchone()
            if row is None:
                raise ConnectionAPIError(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code=INVALID_WORKSPACE,
                    message=f"Workspace {wid} does not belong to tenant {tenant_id}.",
                    fields=[str(wid)],
                )

        now = datetime.now(UTC)

        # Delete existing
        db.execute(
            text(
                "DELETE FROM control.workspace_connection_assignments "
                "WHERE connection_id = CAST(:connection_id AS UUID)"
            ),
            {"connection_id": str(connection_id)},
        )

        # Insert new
        for wid in workspace_ids:
            db.execute(
                text(
                    "INSERT INTO control.workspace_connection_assignments "
                    "(connection_id, workspace_id, assigned_at, assigned_by) "
                    "VALUES (CAST(:cid AS UUID), CAST(:wid AS UUID), :now, CAST(:actor_id AS UUID))"
                ),
                {
                    "cid": str(connection_id),
                    "wid": str(wid),
                    "now": now,
                    "actor_id": str(actor_id),
                },
            )

        db.flush()
        return self.get_assignments(db, connection_id)
