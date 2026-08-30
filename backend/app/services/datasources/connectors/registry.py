"""
F-CONN-CORE — Connector Registry, Capabilities, and Credential Schema.

This is the single source of truth describing every connector the platform
supports: its category, priority, lifecycle status, declarative credential
schema, and capability flags. The frontend connector catalog and credential
form renderer are driven by this data; new connectors plug in by registering
a ``ConnectorSpec`` here.

Status semantics (spec §8):
    READY              fully implemented + tested with real local or external data
    INTEGRATION_READY  configuration/UI/abstraction exist; needs real credentials
    MOCKED             local-only mock; never production
    DEFERRED           not implemented yet; reason recorded
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class ConnectorCategory(str, Enum):
    DATABASE = "database"
    WAREHOUSE = "warehouse"
    LAKEHOUSE = "lakehouse"
    FILE = "file"
    OBJECT_STORAGE = "object_storage"
    QUERY_ENGINE = "query_engine"
    METADATA_CATALOG = "metadata_catalog"
    BI_EXPORTED = "bi_exported"


class ConnectorPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"


class ConnectorStatus(str, Enum):
    READY = "ready"
    INTEGRATION_READY = "integration_ready"
    MOCKED = "mocked"
    DEFERRED = "deferred"


class CredentialFieldType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    SECRET = "secret"
    SELECT = "select"
    BOOLEAN = "boolean"
    JSON = "json"
    MULTILINE = "multiline"


# ─────────────────────────────────────────────────────────────────────────────
# Schema dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CredentialField:
    """One field in a connector's credential schema (spec §10.3)."""

    name: str
    type: CredentialFieldType
    label: str
    required: bool = True
    default: object | None = None
    options: list[str] | None = None  # only for SELECT
    placeholder: str | None = None
    help_text: str | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "name": self.name,
            "type": self.type.value,
            "label": self.label,
            "required": self.required,
        }
        if self.default is not None:
            d["default"] = self.default
        if self.options is not None:
            d["options"] = list(self.options)
        if self.placeholder is not None:
            d["placeholder"] = self.placeholder
        if self.help_text is not None:
            d["help_text"] = self.help_text
        return d


@dataclass(frozen=True)
class ConnectorCapabilities:
    """Per-connector feature flags (spec §8 example payload)."""

    supports_connection_test: bool = False
    supports_metadata_discovery: bool = False
    supports_schema_discovery: bool = False
    supports_table_discovery: bool = False
    supports_file_discovery: bool = False
    supports_dataset_preview: bool = False
    supports_check_execution: bool = False
    supports_sampling: bool = False
    supports_pushdown_sql: bool = False
    supports_parquet: bool = False
    requires_external_credentials: bool = False
    local_test_available: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "supports_connection_test": self.supports_connection_test,
            "supports_metadata_discovery": self.supports_metadata_discovery,
            "supports_schema_discovery": self.supports_schema_discovery,
            "supports_table_discovery": self.supports_table_discovery,
            "supports_file_discovery": self.supports_file_discovery,
            "supports_dataset_preview": self.supports_dataset_preview,
            "supports_check_execution": self.supports_check_execution,
            "supports_sampling": self.supports_sampling,
            "supports_pushdown_sql": self.supports_pushdown_sql,
            "supports_parquet": self.supports_parquet,
            "requires_external_credentials": self.requires_external_credentials,
            "local_test_available": self.local_test_available,
        }


@dataclass(frozen=True)
class ConnectorSpec:
    """Full registry entry for a connector (spec §10.1)."""

    type: str  # canonical id, e.g. "postgresql"
    display_name: str
    category: ConnectorCategory
    priority: ConnectorPriority
    status: ConnectorStatus
    description: str
    credential_schema: list[CredentialField] = field(default_factory=list)
    capabilities: ConnectorCapabilities = field(default_factory=ConnectorCapabilities)
    docs_url: str | None = None
    icon: str | None = None  # logical icon id, frontend maps it
    deferred_reason: str | None = None  # required when status == DEFERRED

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "type": self.type,
            "display_name": self.display_name,
            "category": self.category.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "description": self.description,
            "credential_schema": [f.to_dict() for f in self.credential_schema],
            "capabilities": self.capabilities.to_dict(),
        }
        if self.docs_url:
            d["docs_url"] = self.docs_url
        if self.icon:
            d["icon"] = self.icon
        if self.deferred_reason:
            d["deferred_reason"] = self.deferred_reason
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────


class ConnectorRegistry:
    """In-process registry of all known connectors.

    The catalog is populated at import time from :func:`_default_specs`. New
    connectors plug in by either:
      - editing :func:`_default_specs` (preferred for built-ins), or
      - calling :meth:`register` from an extension's import-time bootstrap.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ConnectorSpec] = {}

    def register(self, spec: ConnectorSpec) -> None:
        if spec.type in self._specs:
            raise ValueError(f"Connector type already registered: {spec.type}")
        if spec.status == ConnectorStatus.DEFERRED and not spec.deferred_reason:
            raise ValueError(f"Connector {spec.type!r} is DEFERRED but has no deferred_reason")
        self._specs[spec.type] = spec

    def get(self, connector_type: str) -> ConnectorSpec | None:
        return self._specs.get(connector_type)

    def list(
        self,
        *,
        category: ConnectorCategory | None = None,
        priority: ConnectorPriority | None = None,
        status: ConnectorStatus | None = None,
        local_only: bool | None = None,
    ) -> builtins.list[ConnectorSpec]:
        out: list[ConnectorSpec] = []
        for spec in self._specs.values():
            if category is not None and spec.category != category:
                continue
            if priority is not None and spec.priority != priority:
                continue
            if status is not None and spec.status != status:
                continue
            if local_only is True and not spec.capabilities.local_test_available:
                continue
            if local_only is False and spec.capabilities.local_test_available:
                continue
            out.append(spec)
        return out

    def types(self) -> builtins.list[str]:
        return list(self._specs.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Default specs (spec §7.1, §7.2, §9)
# ─────────────────────────────────────────────────────────────────────────────


def _jdbc_credential_schema(default_port: int) -> list[CredentialField]:
    return [
        CredentialField("host", CredentialFieldType.STRING, "Host"),
        CredentialField("port", CredentialFieldType.NUMBER, "Port", default=default_port),
        CredentialField("database", CredentialFieldType.STRING, "Database"),
        CredentialField("username", CredentialFieldType.STRING, "Username"),
        CredentialField("password", CredentialFieldType.SECRET, "Password"),
        CredentialField(
            "ssl_mode",
            CredentialFieldType.SELECT,
            "SSL Mode",
            required=False,
            options=["disable", "require", "verify-ca", "verify-full"],
        ),
    ]


def _default_specs() -> list[ConnectorSpec]:
    specs: list[ConnectorSpec] = []

    # ── P0 Local-Ready ────────────────────────────────────────────────────
    specs.append(
        ConnectorSpec(
            type="postgresql",
            display_name="PostgreSQL",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.READY,
            description="Open-source relational database. Local Docker testing supported.",
            credential_schema=_jdbc_credential_schema(default_port=5432),
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                local_test_available=True,
            ),
            icon="postgresql",
        )
    )
    specs.append(
        ConnectorSpec(
            type="mysql",
            display_name="MySQL",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Open-source relational database.",
            credential_schema=_jdbc_credential_schema(default_port=3306),
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                local_test_available=True,
            ),
            icon="mysql",
        )
    )
    specs.append(
        ConnectorSpec(
            type="mssql",
            display_name="Microsoft SQL Server",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Microsoft SQL Server. Local Docker container available.",
            credential_schema=_jdbc_credential_schema(default_port=1433),
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                local_test_available=True,
            ),
            icon="mssql",
        )
    )
    specs.append(
        ConnectorSpec(
            type="csv",
            display_name="CSV File",
            category=ConnectorCategory.FILE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.READY,
            description="Comma-separated value files uploaded by the user.",
            credential_schema=[
                CredentialField(
                    "file_path",
                    CredentialFieldType.STRING,
                    "File path",
                    placeholder="/uploads/customers.csv",
                    help_text="Absolute path or path relative to the upload directory.",
                ),
                CredentialField(
                    "delimiter",
                    CredentialFieldType.STRING,
                    "Delimiter",
                    required=False,
                    default=",",
                    help_text="Field delimiter character (default ',').",
                ),
                CredentialField(
                    "encoding",
                    CredentialFieldType.STRING,
                    "Encoding",
                    required=False,
                    default="utf-8",
                ),
                CredentialField(
                    "has_header",
                    CredentialFieldType.BOOLEAN,
                    "First row is a header",
                    required=False,
                    default=True,
                ),
                CredentialField(
                    "quote_char",
                    CredentialFieldType.STRING,
                    "Quote character",
                    required=False,
                    default='"',
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_file_discovery=True,
                local_test_available=True,
            ),
            icon="file-csv",
        )
    )
    specs.append(
        ConnectorSpec(
            type="excel",
            display_name="Excel File",
            category=ConnectorCategory.FILE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.READY,
            description="Microsoft Excel (.xlsx) workbooks. Each sheet becomes a table.",
            credential_schema=[
                CredentialField(
                    "file_path",
                    CredentialFieldType.STRING,
                    "File path",
                    placeholder="/uploads/orders.xlsx",
                    help_text="Absolute path or relative to UPLOAD_DIR.",
                ),
                CredentialField(
                    "has_header",
                    CredentialFieldType.BOOLEAN,
                    "First row is header",
                    required=False,
                    default=True,
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_file_discovery=True,
                local_test_available=True,
            ),
            icon="file-excel",
        )
    )
    specs.append(
        ConnectorSpec(
            type="parquet",
            display_name="Parquet File",
            category=ConnectorCategory.FILE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.READY,
            description="Apache Parquet columnar files.",
            credential_schema=[
                CredentialField(
                    "file_path",
                    CredentialFieldType.STRING,
                    "File path",
                    placeholder="/uploads/events.parquet",
                    help_text="Absolute path or relative to UPLOAD_DIR.",
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_file_discovery=True,
                supports_parquet=True,
                local_test_available=True,
            ),
            icon="file-parquet",
        )
    )
    specs.append(
        ConnectorSpec(
            type="s3",
            display_name="Amazon S3 / MinIO",
            category=ConnectorCategory.OBJECT_STORAGE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.READY,
            description=(
                "Amazon S3 and S3-compatible object stores (MinIO). Browse buckets "
                "for CSV / Parquet / JSON objects."
            ),
            credential_schema=[
                CredentialField(
                    "endpoint_url",
                    CredentialFieldType.STRING,
                    "Endpoint URL",
                    required=False,
                    placeholder="https://s3.amazonaws.com or http://minio:9000",
                ),
                CredentialField("region", CredentialFieldType.STRING, "Region", required=False),
                CredentialField("bucket", CredentialFieldType.STRING, "Bucket"),
                CredentialField("access_key_id", CredentialFieldType.STRING, "Access Key ID"),
                CredentialField(
                    "secret_access_key", CredentialFieldType.SECRET, "Secret Access Key"
                ),
                CredentialField(
                    "secure",
                    CredentialFieldType.BOOLEAN,
                    "Use HTTPS",
                    required=False,
                    default=True,
                ),
                CredentialField(
                    "prefix",
                    CredentialFieldType.STRING,
                    "Object prefix",
                    required=False,
                    placeholder="datasets/",
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_file_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_parquet=True,
                local_test_available=True,
            ),
            icon="s3",
        )
    )

    # ── P0 Cloud / Integration-Ready ──────────────────────────────────────
    specs.append(
        ConnectorSpec(
            type="snowflake",
            display_name="Snowflake",
            category=ConnectorCategory.WAREHOUSE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Snowflake cloud data warehouse.",
            credential_schema=[
                CredentialField("account", CredentialFieldType.STRING, "Account Identifier"),
                CredentialField("warehouse", CredentialFieldType.STRING, "Warehouse"),
                CredentialField("database", CredentialFieldType.STRING, "Database"),
                CredentialField("schema", CredentialFieldType.STRING, "Schema", required=False),
                CredentialField("role", CredentialFieldType.STRING, "Role", required=False),
                CredentialField("username", CredentialFieldType.STRING, "Username"),
                CredentialField("password", CredentialFieldType.SECRET, "Password"),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                requires_external_credentials=True,
            ),
            icon="snowflake",
        )
    )
    specs.append(
        ConnectorSpec(
            type="bigquery",
            display_name="Google BigQuery",
            category=ConnectorCategory.WAREHOUSE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Google Cloud BigQuery data warehouse.",
            credential_schema=[
                CredentialField("project_id", CredentialFieldType.STRING, "Project ID"),
                CredentialField(
                    "dataset", CredentialFieldType.STRING, "Default Dataset", required=False
                ),
                CredentialField(
                    "service_account_json",
                    CredentialFieldType.JSON,
                    "Service Account JSON",
                    help_text="Paste the contents of a service account key file.",
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                requires_external_credentials=True,
            ),
            icon="bigquery",
        )
    )
    specs.append(
        ConnectorSpec(
            type="databricks",
            display_name="Databricks SQL / Unity Catalog",
            category=ConnectorCategory.LAKEHOUSE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Databricks SQL warehouse via Unity Catalog.",
            credential_schema=[
                CredentialField("server_hostname", CredentialFieldType.STRING, "Server Hostname"),
                CredentialField("http_path", CredentialFieldType.STRING, "HTTP Path"),
                CredentialField("access_token", CredentialFieldType.SECRET, "Access Token"),
                CredentialField("catalog", CredentialFieldType.STRING, "Catalog", required=False),
                CredentialField("schema", CredentialFieldType.STRING, "Schema", required=False),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                requires_external_credentials=True,
            ),
            icon="databricks",
        )
    )
    specs.append(
        ConnectorSpec(
            type="adls_gen2",
            display_name="Azure Data Lake Storage Gen2",
            category=ConnectorCategory.OBJECT_STORAGE,
            priority=ConnectorPriority.P0,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Azure Data Lake Storage Gen2 (CSV / Parquet objects).",
            credential_schema=[
                CredentialField("storage_account", CredentialFieldType.STRING, "Storage Account"),
                CredentialField("container", CredentialFieldType.STRING, "Container"),
                CredentialField("access_key", CredentialFieldType.SECRET, "Access Key"),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_file_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_parquet=True,
                requires_external_credentials=True,
            ),
            icon="azure",
        )
    )

    # ── P1 ────────────────────────────────────────────────────────────────
    specs.append(
        ConnectorSpec(
            type="oracle",
            display_name="Oracle Database",
            category=ConnectorCategory.DATABASE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Oracle Database. Local Docker container available.",
            credential_schema=[
                CredentialField("host", CredentialFieldType.STRING, "Host"),
                CredentialField("port", CredentialFieldType.NUMBER, "Port", default=1521),
                CredentialField("service_name", CredentialFieldType.STRING, "Service Name"),
                CredentialField("username", CredentialFieldType.STRING, "Username"),
                CredentialField("password", CredentialFieldType.SECRET, "Password"),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                local_test_available=True,
            ),
            icon="oracle",
        )
    )
    specs.append(
        ConnectorSpec(
            type="redshift",
            display_name="Amazon Redshift",
            category=ConnectorCategory.WAREHOUSE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Amazon Redshift cloud data warehouse.",
            credential_schema=_jdbc_credential_schema(default_port=5439),
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                requires_external_credentials=True,
            ),
            icon="redshift",
        )
    )
    specs.append(
        ConnectorSpec(
            type="synapse",
            display_name="Azure Synapse",
            category=ConnectorCategory.WAREHOUSE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Azure Synapse Analytics dedicated SQL pool.",
            credential_schema=_jdbc_credential_schema(default_port=1433),
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
                requires_external_credentials=True,
            ),
            icon="synapse",
        )
    )
    specs.append(
        ConnectorSpec(
            type="iceberg",
            display_name="Apache Iceberg",
            category=ConnectorCategory.LAKEHOUSE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.DEFERRED,
            description="Apache Iceberg table format (via REST or Glue catalog).",
            credential_schema=[],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_parquet=True,
            ),
            icon="iceberg",
            deferred_reason="Implemented in F-CONN-P1.",
        )
    )
    specs.append(
        ConnectorSpec(
            type="hive_metastore",
            display_name="Hive Metastore",
            category=ConnectorCategory.METADATA_CATALOG,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.DEFERRED,
            description="Hive Metastore for big-data table metadata.",
            credential_schema=[],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
            ),
            icon="hive",
            deferred_reason="Implemented in F-CONN-P1.",
        )
    )
    specs.append(
        ConnectorSpec(
            type="trino",
            display_name="Trino / Starburst",
            category=ConnectorCategory.QUERY_ENGINE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.DEFERRED,
            description="Trino distributed SQL query engine (Starburst).",
            credential_schema=[
                CredentialField("host", CredentialFieldType.STRING, "Host"),
                CredentialField("port", CredentialFieldType.NUMBER, "Port", default=8080),
                CredentialField("catalog", CredentialFieldType.STRING, "Catalog"),
                CredentialField("schema", CredentialFieldType.STRING, "Schema", required=False),
                CredentialField("username", CredentialFieldType.STRING, "Username"),
                CredentialField("password", CredentialFieldType.SECRET, "Password", required=False),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_table_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_pushdown_sql=True,
            ),
            icon="trino",
            deferred_reason="Implemented in F-CONN-P1.",
        )
    )
    specs.append(
        ConnectorSpec(
            type="gcs",
            display_name="Google Cloud Storage",
            category=ConnectorCategory.OBJECT_STORAGE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.INTEGRATION_READY,
            description="Google Cloud Storage (CSV / Parquet objects).",
            credential_schema=[
                CredentialField("project_id", CredentialFieldType.STRING, "Project ID"),
                CredentialField("bucket", CredentialFieldType.STRING, "Bucket"),
                CredentialField(
                    "service_account_json",
                    CredentialFieldType.JSON,
                    "Service Account JSON",
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_connection_test=True,
                supports_metadata_discovery=True,
                supports_file_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_parquet=True,
                requires_external_credentials=True,
            ),
            icon="gcs",
        )
    )
    specs.append(
        ConnectorSpec(
            type="json",
            display_name="JSON / NDJSON File",
            category=ConnectorCategory.FILE,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.READY,
            description="JSON and newline-delimited JSON files.",
            credential_schema=[
                CredentialField(
                    "file_path",
                    CredentialFieldType.STRING,
                    "File path",
                    placeholder="/uploads/events.ndjson",
                    help_text="Absolute path or relative to UPLOAD_DIR.",
                ),
                CredentialField(
                    "encoding",
                    CredentialFieldType.STRING,
                    "Encoding",
                    required=False,
                    default="utf-8",
                ),
                CredentialField(
                    "json_format",
                    CredentialFieldType.SELECT,
                    "Format",
                    required=False,
                    default="auto",
                    options=["auto", "ndjson", "array", "object"],
                ),
            ],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                supports_schema_discovery=True,
                supports_dataset_preview=True,
                supports_check_execution=True,
                supports_sampling=True,
                supports_file_discovery=True,
                local_test_available=True,
            ),
            icon="file-json",
        )
    )
    specs.append(
        ConnectorSpec(
            type="dbt_manifest",
            display_name="dbt Manifest",
            category=ConnectorCategory.METADATA_CATALOG,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.DEFERRED,
            description="Ingest dbt project metadata from a manifest.json file.",
            credential_schema=[],
            capabilities=ConnectorCapabilities(
                supports_metadata_discovery=True,
                local_test_available=True,
            ),
            icon="dbt",
            deferred_reason="Implemented in F-CONN-P1.",
        )
    )
    specs.append(
        ConnectorSpec(
            type="powerbi",
            display_name="Power BI Exported Datasets",
            category=ConnectorCategory.BI_EXPORTED,
            priority=ConnectorPriority.P1,
            status=ConnectorStatus.DEFERRED,
            description="Power BI semantic model / exported dataset (feasibility review).",
            credential_schema=[],
            capabilities=ConnectorCapabilities(),
            icon="powerbi",
            deferred_reason="Feasibility review pending — see spec §7.2.",
        )
    )

    return specs


# Module-level singleton, populated at import time.
registry = ConnectorRegistry()
for _spec in _default_specs():
    registry.register(_spec)


__all__ = [
    "CredentialField",
    "CredentialFieldType",
    "ConnectorCapabilities",
    "ConnectorSpec",
    "ConnectorRegistry",
    "ConnectorCategory",
    "ConnectorPriority",
    "ConnectorStatus",
    "registry",
]
