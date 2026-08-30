"""
F108 — Metadata Connectors Framework Pydantic Schemas.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── enums ──


class ConnectorType(str, enum.Enum):
    GLOSSARY = "glossary"
    CATALOG = "catalog"
    LINEAGE = "lineage"
    SCHEMA = "schema"
    BI = "bi"
    ETL = "etl"


class SyncMode(str, enum.Enum):
    REAL_TIME = "real_time"
    SCHEDULED = "scheduled"
    FULL = "full"
    HYBRID = "hybrid"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# ── CRUD schemas ──


class ConnectorConfigCreate(BaseModel):
    connector_type: ConnectorType
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    connection_config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: SyncMode = SyncMode.HYBRID
    sync_schedule: str | None = None
    is_active: bool = True
    trust_priority: int = Field(default=50, ge=1, le=100)


class ConnectorConfigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    connection_config: dict[str, Any] | None = None
    sync_mode: SyncMode | None = None
    sync_schedule: str | None = None
    is_active: bool | None = None
    trust_priority: int | None = Field(None, ge=1, le=100)


class ConnectorConfigResponse(BaseModel):
    id: str
    workspace_id: str
    connector_type: str
    name: str
    description: str | None = None
    connection_config: dict[str, Any] = Field(default_factory=dict)
    sync_mode: str
    sync_schedule: str | None = None
    is_active: bool
    trust_priority: int
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SyncHistoryResponse(BaseModel):
    id: str
    connector_config_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    assets_created: int = 0
    assets_updated: int = 0
    terms_created: int = 0
    terms_updated: int = 0
    error: str | None = None

    class Config:
        from_attributes = True


class ConnectorListResponse(BaseModel):
    items: list[ConnectorConfigResponse] = Field(default_factory=list)
    total: int = 0


class ConnectorTestResult(BaseModel):
    success: bool
    message: str
    details: dict[str, Any] | None = None
