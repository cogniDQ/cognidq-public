# Test Data Source Credentials

The test databases are defined in `docker-compose.test.yml` (separate from the
default stack to avoid pulling ~3 GB of images on every `docker compose up`).

Start them with:

```bash
# Using Make (recommended):
make test-dbs

# Or directly with Docker Compose:
docker compose -f docker-compose.yml -f docker-compose.test.yml \
  up dq-testdb dq-mysql dq-mssql dq-oracle -d
```

Stop them with:

```bash
make test-dbs-down
```

---

## Host values

When filling credentials in the UI, the **host** depends on where the backend is running:

| Backend running… | Use host |
|---|---|
| Inside Docker (via docker-compose) | service name (e.g. `dq-testdb`) |
| Locally (uvicorn on host machine) | `localhost` |

---

## PostgreSQL

**Container:** `dq-testdb` · **Port:** `5435` (mapped from `5432`)

| Field | Value |
|---|---|
| Host | `dq-testdb` / `localhost` |
| Port | `5432` / `5435` |
| Database | `dq_test` |
| Username | `testuser` |
| Password | `testpassword` |

---

## MySQL

**Container:** `dq-mysql` · **Port:** `3307` (mapped from `3306`)

| Field | Value |
|---|---|
| Host | `dq-mysql` / `localhost` |
| Port | `3306` / `3307` |
| Database | `dq_test` |
| Username | `testuser` |
| Password | `testpassword` |

---

## SQL Server (MSSQL)

**Container:** `dq-mssql` · **Port:** `1434` (mapped from `1433`)

| Field | Value |
|---|---|
| Host | `dq-mssql` / `localhost` |
| Port | `1433` / `1434` |
| Database | `master` |
| Username | `sa` |
| Password | `Test@1234` |

> `master` is used because automatic DB creation is not configured. You can run `CREATE DATABASE dq_test;` via sqlcmd after startup if needed.

---

## Oracle

**Container:** `dq-oracle` · **Port:** `1522` (mapped from `1521`)  
**Note:** Oracle XE 21c takes ~2 minutes to fully initialize on first start.

| Field | Value |
|---|---|
| Host | `dq-oracle` / `localhost` |
| Port | `1521` / `1522` |
| Database | `XEPDB1` |
| Username | `testuser` |
| Password | `testpassword` |

> `XEPDB1` is the default pluggable database in Oracle XE 21. The `testuser` app user is created automatically in that PDB via the `APP_USER` / `APP_USER_PASSWORD` env vars.

---

## Snowflake

Snowflake is a cloud service — no local container available.

| Field | Value |
|---|---|
| Account Identifier | *(your Snowflake account identifier)* |
| Account | *(your account name)* |
| Warehouse | *(your warehouse name)* |
| Database | *(your database name)* |
| Username | *(your username)* |
| Password | *(your password)* |

---

## BigQuery

BigQuery is a cloud service — no local container available.

| Field | Value |
|---|---|
| Project ID | *(your GCP project ID)* |
| Service Account JSON | *(paste the full JSON key file content)* |
