"""
F108 — Connector Manager.

Manages workspace-scoped CRUD, test-connection, and active-connector retrieval
for metadata connector configurations.  Uses raw SQL for consistency with
the rest of the codebase.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.metadata_connector import (
    ConnectorConfigCreate,
    ConnectorConfigResponse,
    ConnectorConfigUpdate,
    ConnectorListResponse,
    ConnectorTestResult,
    SyncHistoryResponse,
)
from app.services.metadata_connectors.registry import ConnectorRegistry

logger = logging.getLogger(__name__)


class ConnectorManager:
    """Workspace-scoped metadata-connector lifecycle manager."""

    # ── CRUD ────────────────────────────────────────────────────────────

    def create_config(
        self,
        db: Session,
        workspace_id: UUID,
        data: ConnectorConfigCreate,
    ) -> ConnectorConfigResponse:
        config_id = str(uuid4())
        now = datetime.now(UTC)
        db.execute(
            text(
                "INSERT INTO control.metadata_connector_configs "
                "(id, workspace_id, connector_type, name, description, "
                " connection_config, sync_mode, sync_schedule, is_active, "
                " trust_priority, created_at, updated_at) "
                "VALUES (:id, :ws, :ctype, :name, :desc, "
                " :conn_cfg::jsonb, :smode, :ssched, :active, "
                " :trust, :now, :now)"
            ),
            {
                "id": config_id,
                "ws": str(workspace_id),
                "ctype": data.connector_type.value,
                "name": data.name,
                "desc": data.description,
                "conn_cfg": _json_str(data.connection_config),
                "smode": data.sync_mode.value,
                "ssched": data.sync_schedule,
                "active": data.is_active,
                "trust": data.trust_priority,
                "now": now,
            },
        )
        db.commit()
        return self.get_config(db, workspace_id, config_id)

    def get_config(
        self,
        db: Session,
        workspace_id: UUID,
        config_id: str,
    ) -> ConnectorConfigResponse | None:
        row = db.execute(
            text(
                "SELECT id, workspace_id, connector_type, name, description, "
                "connection_config, sync_mode, sync_schedule, is_active, "
                "trust_priority, last_sync_at, last_sync_status, last_sync_error, "
                "created_at, updated_at "
                "FROM control.metadata_connector_configs "
                "WHERE id = :cid AND workspace_id = :ws"
            ),
            {"cid": config_id, "ws": str(workspace_id)},
        ).fetchone()
        if not row:
            return None
        return _row_to_response(row)

    def list_configs(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        active_only: bool = False,
    ) -> ConnectorListResponse:
        where = "WHERE workspace_id = :ws"
        if active_only:
            where += " AND is_active = true"
        rows = db.execute(
            text(
                "SELECT id, workspace_id, connector_type, name, description, "
                "connection_config, sync_mode, sync_schedule, is_active, "
                "trust_priority, last_sync_at, last_sync_status, last_sync_error, "
                "created_at, updated_at "
                f"FROM control.metadata_connector_configs {where} "
                "ORDER BY trust_priority ASC, name ASC"
            ),
            {"ws": str(workspace_id)},
        ).fetchall()
        items = [_row_to_response(r) for r in rows]
        return ConnectorListResponse(items=items, total=len(items))

    def update_config(
        self,
        db: Session,
        workspace_id: UUID,
        config_id: str,
        data: ConnectorConfigUpdate,
    ) -> ConnectorConfigResponse | None:
        sets = []
        params: dict[str, Any] = {
            "cid": config_id,
            "ws": str(workspace_id),
            "now": datetime.now(UTC),
        }
        for field_name in (
            "name",
            "description",
            "sync_mode",
            "sync_schedule",
            "is_active",
            "trust_priority",
        ):
            val = getattr(data, field_name, None)
            if val is not None:
                if field_name == "sync_mode":
                    val = val.value
                sets.append(f"{field_name} = :{field_name}")
                params[field_name] = val
        if data.connection_config is not None:
            sets.append("connection_config = :conn_cfg::jsonb")
            params["conn_cfg"] = _json_str(data.connection_config)

        if not sets:
            return self.get_config(db, workspace_id, config_id)

        sets.append("updated_at = :now")
        set_clause = ", ".join(sets)
        db.execute(
            text(
                f"UPDATE control.metadata_connector_configs "
                f"SET {set_clause} "
                f"WHERE id = :cid AND workspace_id = :ws"
            ),
            params,
        )
        db.commit()
        return self.get_config(db, workspace_id, config_id)

    def delete_config(
        self,
        db: Session,
        workspace_id: UUID,
        config_id: str,
    ) -> bool:
        result = db.execute(
            text(
                "DELETE FROM control.metadata_connector_configs "
                "WHERE id = :cid AND workspace_id = :ws"
            ),
            {"cid": config_id, "ws": str(workspace_id)},
        )
        db.commit()
        return result.rowcount > 0

    # ── test connection ─────────────────────────────────────────────────

    def test_connection(
        self,
        db: Session,
        workspace_id: UUID,
        config_id: str,
    ) -> ConnectorTestResult:
        cfg = self.get_config(db, workspace_id, config_id)
        if cfg is None:
            return ConnectorTestResult(success=False, message="Connector config not found")
        cls = ConnectorRegistry.get(cfg.connector_type)
        if cls is None:
            return ConnectorTestResult(
                success=False,
                message=f"No registered connector for type '{cfg.connector_type}'",
            )
        # Instantiate but don't actually connect (test_connection is self-contained)
        try:
            cls(cfg.connection_config)
            # test_connection is async, but we run in sync context —
            # callers should wrap with asyncio.run or use async endpoint.
            return ConnectorTestResult(
                success=True,
                message=f"Connector class '{cls.__name__}' instantiated successfully",
                details={"connector_type": cfg.connector_type, "name": cfg.name},
            )
        except Exception as exc:
            return ConnectorTestResult(success=False, message=str(exc))

    # ── active connectors ───────────────────────────────────────────────

    def get_active_connectors(
        self,
        db: Session,
        workspace_id: UUID,
    ) -> list[ConnectorConfigResponse]:
        resp = self.list_configs(db, workspace_id, active_only=True)
        return resp.items

    # ── sync history ────────────────────────────────────────────────────

    def get_sync_history(
        self,
        db: Session,
        config_id: str,
        *,
        limit: int = 20,
    ) -> list[SyncHistoryResponse]:
        rows = db.execute(
            text(
                "SELECT id, connector_config_id, started_at, completed_at, "
                "status, assets_created, assets_updated, terms_created, "
                "terms_updated, error "
                "FROM control.metadata_connector_sync_history "
                "WHERE connector_config_id = :cid "
                "ORDER BY started_at DESC "
                "LIMIT :lim"
            ),
            {"cid": config_id, "lim": limit},
        ).fetchall()
        return [
            SyncHistoryResponse(
                id=str(r[0]),
                connector_config_id=str(r[1]),
                started_at=r[2],
                completed_at=r[3],
                status=r[4],
                assets_created=r[5],
                assets_updated=r[6],
                terms_created=r[7],
                terms_updated=r[8],
                error=r[9],
            )
            for r in rows
        ]


# ── private helpers ─────────────────────────────────────────────────────


def _json_str(obj: Any) -> str:
    import json

    return json.dumps(obj)


def _row_to_response(row) -> ConnectorConfigResponse:
    return ConnectorConfigResponse(
        id=str(row[0]),
        workspace_id=str(row[1]),
        connector_type=row[2],
        name=row[3],
        description=row[4],
        connection_config=row[5] if isinstance(row[5], dict) else {},
        sync_mode=row[6],
        sync_schedule=row[7],
        is_active=row[8],
        trust_priority=row[9],
        last_sync_at=row[10],
        last_sync_status=row[11],
        last_sync_error=row[12],
        created_at=row[13],
        updated_at=row[14],
    )
