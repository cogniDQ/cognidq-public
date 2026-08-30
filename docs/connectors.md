# Connectors

A **connector** lets CogniDQ read from a data source so it can run
quality rules against it. This page lists what is supported and what is
experimental.

For the dataset model itself (registration, schema inference, browsing),
see [datasets.md](datasets.md).

---

## Supported connectors (v0.1.0-alpha)

| Connector | Status | Notes |
|---|---|---|
| **PostgreSQL** | stable | Primary connector. Tested in CI and exercised by demo data. |
| **CSV upload** | stable | For ad-hoc datasets. Files stored in MinIO. |
| **Local sample datasets** | stable | The seeded `customers` / `orders` / `payments` datasets. |
| MySQL | beta | Connector code exists; smoke-tested in `dq-mysql` compose service; no CI coverage yet. |
| Microsoft SQL Server | beta | Same. Demo container `dq-mssql`. |
| Oracle | beta | Same. Demo container `dq-oracle`. |
| Snowflake | experimental | Code path present; not exercised. Treat as preview. |
| Databricks (SQL warehouse) | experimental | Same. |
| Google BigQuery | experimental | Same. |
| Amazon Redshift | experimental | Same. |
| Apache Spark on object storage (CSV/parquet in MinIO/S3) | experimental | Works on the demo dataset; not in CI. |
| OpenMetadata (read-only metadata import) | experimental | Behind `ENABLE_OPENMETADATA_INTEGRATION`. |

The graduation criteria from beta → stable are in
[CONTRIBUTING.md](../CONTRIBUTING.md): tests, docs, an example dataset,
and a smoke run in CI.

## Read-only by design

All connectors are **read-only**. The connector layer:

- opens the connection with the lowest privileges the underlying engine
  allows (`SET TRANSACTION READ ONLY` on Postgres, equivalent options
  elsewhere);
- never executes DDL or DML;
- never persists data back into the source system.

Custom rule paths that *would* allow arbitrary SQL (`custom_sql`) are
gated behind a feature flag and the connector still enforces read-only.

## Connection objects

A **connection** is the credential bag that connectors use:

```jsonc
{
  "id": "conn_01HXYZ",
  "workspace_id": "ws_demo",
  "type": "postgresql",
  "name": "Analytics replica (read-only)",
  "host": "analytics-replica.internal",
  "port": 5432,
  "database": "analytics",
  "username": "dq_reader",
  "password_encrypted": "<fernet-blob>",
  "ssl_mode": "require",
  "extra": {}
}
```

- Passwords are encrypted at rest with `CREDENTIAL_ENCRYPTION_KEY`.
- Connections are scoped to a workspace.
- Multiple datasets can share one connection.

### Testing a connection

The UI exposes a "Test connection" button that:

1. opens a connection,
2. runs `SELECT 1` (or the connector-equivalent),
3. closes the connection,
4. returns success/failure with the engine error message (sanitised).

The same is exposed via `POST /api/v1/connections/{id}/test`.

## Adding a new connector

If you want to add a connector, the contract is:

1. Implement a class that extends `BaseConnector` in
   `backend/app/services/datasources/connectors/`.
2. Implement: `validate_config`, `test_connection`, `list_schemas`,
   `list_tables`, `describe_table`, `read_query`.
3. Add a unit test under
   `backend/tests/unit/services/datasources/test_<name>_connector.py`.
4. Add a docker-compose service under `dq-<name>` for local testing if
   the connector targets a database that is OSS-distributable.
5. Add an integration test (skipped by default unless the compose
   service is healthy).
6. Update this document and add a row to the table.

PRs welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Connector configuration reference

Each connector accepts the standard fields plus connector-specific
extras. Common fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `host` | string | yes | hostname or IP |
| `port` | int | no | default per connector |
| `database` | string | yes | database / catalog name |
| `username` | string | yes | low-privilege account |
| `password` | secret | yes (or auth=keyfile/iam) | encrypted at rest |
| `ssl_mode` | string | no | `disable` / `require` / `verify-full` |
| `extra` | object | no | connector-specific tweaks |

Connector-specific notes are in the per-connector docs (TBD per
connector graduation).
