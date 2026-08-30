"""
F130 — TenantConnectionService
================================
Thin orchestration layer over TenantConnectionRepository.
Delegates test-connection to the existing DataSourceService.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import status
from sqlalchemy.orm import Session

from app.services.connections.errors import ConnectionAPIError
from app.services.connections.repository import TenantConnectionRepository

_repo = TenantConnectionRepository()
logger = logging.getLogger(__name__)


class TenantConnectionService:
    def list_connections(
        self,
        db: Session,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status_filter: str | None = None,
        workspace_id_filter: UUID | None = None,
    ) -> tuple[list[dict], int]:
        return _repo.list_by_tenant(
            db, tenant_id, page, page_size, search, status_filter, workspace_id_filter
        )

    def get_connection(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> dict | None:
        return _repo.get_by_tenant(db, tenant_id, connection_id)

    def create_connection(
        self,
        db: Session,
        tenant_id: UUID,
        payload: dict,
        actor_id: UUID,
    ) -> dict:
        """Create a tenant-owned connection.

        Optional payload keys:
            credentials: Dict[str, Any] — encrypted and stored when present.
            workspace_ids: List[UUID]   — workspaces granted access.

        All writes happen in a single transaction. Validation reuses the
        existing data_sources validators so error shape stays consistent.
        """
        from app.services.data_sources import credential_service as cred_svc
        from app.services.data_sources.credential_repository import (
            CredentialRepository,
        )
        from app.services.data_sources.validation import validate_create_payload

        credentials = payload.get("credentials")
        workspace_ids: list[UUID] = list(payload.get("workspace_ids") or [])

        # ── Validate via shared data_sources validator ───────────────────────
        validation_payload = {
            "source_name": payload.get("source_name"),
            "source_type": payload.get("source_type"),
            "connection_mode": payload.get("connection_mode"),
            "environment": payload.get("environment"),
            "description": payload.get("description"),
            "credentials": credentials or {},
        }
        result = validate_create_payload(validation_payload)
        if result.errors:
            raise ConnectionAPIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Connection payload failed validation.",
                fields=result.errors,
            )

        # ── Validate workspace_ids belong to tenant (pre-flight) ─────────────
        from sqlalchemy import text

        for wid in workspace_ids:
            row = db.execute(
                text(
                    "SELECT 1 FROM control.workspaces "
                    "WHERE workspace_id = CAST(:wid AS UUID) "
                    "  AND tenant_id    = CAST(:tenant_id AS UUID)"
                ),
                {"wid": str(wid), "tenant_id": str(tenant_id)},
            ).fetchone()
            if row is None:
                raise ConnectionAPIError(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="INVALID_WORKSPACE",
                    message=f"Workspace {wid} does not belong to tenant {tenant_id}.",
                    fields=[str(wid)],
                )

        try:
            # 1. INSERT data_sources row (workspace_id NULL, no credential ref).
            connection = _repo.create(db, tenant_id, payload, actor_id)
            connection_id = (
                UUID(connection["data_source_id"])
                if isinstance(connection["data_source_id"], str)
                else connection["data_source_id"]
            )

            # 2. Encrypt and store credentials (when provided).
            if credentials:
                encrypted = cred_svc.encrypt(credentials)
                credential = CredentialRepository().create(
                    db,
                    data_source_id=connection_id,
                    source_type=payload["source_type"],
                    encrypted_payload=encrypted,
                    created_by=actor_id,
                )
                _repo.set_credential_reference(
                    db, connection_id, credential.credential_id, actor_id
                )

            # 3. Persist workspace assignments inside the same transaction.
            if workspace_ids:
                _repo.replace_assignments(db, tenant_id, connection_id, workspace_ids, actor_id)

            db.commit()
        except ConnectionAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

        return _repo.get_by_tenant(db, tenant_id, connection_id) or connection

    def update_connection(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
        patch: dict,
        actor_id: UUID,
    ) -> dict:
        result = _repo.update(db, tenant_id, connection_id, patch, actor_id)
        db.commit()
        return result

    def delete_connection(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> None:
        _repo.delete(db, tenant_id, connection_id)
        db.commit()

    def get_workspace_assignments(
        self,
        db: Session,
        connection_id: UUID,
    ) -> list[dict]:
        return _repo.get_assignments(db, connection_id)

    def replace_workspace_assignments(
        self,
        db: Session,
        tenant_id: UUID,
        connection_id: UUID,
        workspace_ids: list[UUID],
        actor_id: UUID,
    ) -> list[dict]:
        result = _repo.replace_assignments(db, tenant_id, connection_id, workspace_ids, actor_id)
        db.commit()
        return result

    def test_connection(
        self,
        source_type: str,
        connection_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Delegate to existing DataSourceService for connection testing."""
        from app.services.data_sources.service import DataSourceService

        return DataSourceService().test_connection(source_type, connection_config)
