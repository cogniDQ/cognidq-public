"""
F004 — Data Source domain models
==================================

Plain Python dataclasses used by every layer from repository to controller.
No database, HTTP, or I/O dependencies.

Design notes
------------
* All UUID fields are ``uuid.UUID`` objects; the repository casts DB strings
  back to uuid.UUID at the boundary.
* Optional fields that default to ``None`` come after mandatory fields.
* ``DataSourceStatus`` and ``TestStatus`` are str enums so that JSON
  serialisation works without a custom encoder.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class DataSourceStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class TestStatus(str, enum.Enum):
    untested = "untested"
    reachable = "reachable"
    unreachable = "unreachable"
    test_failed = "test_failed"


class ConnectionMode(str, enum.Enum):
    direct = "direct"
    agent = "agent"


class Environment(str, enum.Enum):
    development = "development"
    staging = "staging"
    production = "production"


SUPPORTED_SOURCE_TYPES = frozenset(
    {
        # Relational databases (legacy F004)
        "postgresql",
        "mysql",
        "mssql",
        "oracle",
        # Cloud DWHs (legacy F004 + extensions)
        "snowflake",
        "bigquery",
        "redshift",
        "synapse",
        # File-based connectors (F130 catalog)
        "csv",
        "excel",
        "json",
        "parquet",
        # Object storage / lakehouse (F130 catalog)
        "s3",
        "adls_gen2",
        "gcs",
        "databricks",
        "iceberg",
        "trino",
        # Metadata / BI (F130 catalog)
        "dbt_manifest",
        "hive_metastore",
        "powerbi",
    }
)

JDBC_SOURCE_TYPES = frozenset({"mysql", "mssql", "oracle"})

BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS = frozenset(
    {
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
    }
)

IMMUTABLE_FIELDS = frozenset({"source_type"})


# ─────────────────────────────────────────────────────────────────────────────
# Domain models
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DataSource:
    """
    Domain model for a row in ``control.data_sources``.

    ``data_source_id`` is ``None`` until the repository assigns it on INSERT.
    ``credential_reference`` is the opaque UUID FK to data_source_credentials;
    it is safe to return in API responses (the actual encrypted payload is
    never exposed to callers).
    """

    workspace_id: UUID
    tenant_id: UUID
    source_name: str
    source_type: str
    connection_mode: str
    environment: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    # fields with defaults
    data_source_id: UUID | None = None
    description: str | None = None
    credential_reference: UUID | None = None
    status: DataSourceStatus = DataSourceStatus.active
    last_test_status: TestStatus = TestStatus.untested
    last_tested_at: datetime | None = None
    updated_by: UUID | None = None
    archived_at: datetime | None = None
    archived_by: UUID | None = None


@dataclass(slots=True)
class DataSourceCredential:
    """
    Domain model for a row in ``control.data_source_credentials``.

    ``credential_id`` is ``None`` until the repository assigns it on INSERT.
    ``encrypted_payload`` is the raw bytes from the BYTEA column; the
    service layer is responsible for decrypting it.
    """

    data_source_id: UUID
    source_type: str
    encrypted_payload: bytes
    created_by: UUID
    created_at: datetime

    credential_id: UUID | None = None
    superseded_at: datetime | None = None


@dataclass(slots=True)
class DataSourceAuditEvent:
    """
    Lightweight audit record for data source operations.
    Written by the service layer using a fire-and-forget pattern after commit.
    """

    workspace_id: UUID
    tenant_id: UUID
    data_source_id: UUID
    action_type: str
    actor_id: UUID
    actor_role: str
    occurred_at: datetime
