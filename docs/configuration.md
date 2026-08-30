# Configuration

CogniDQ is configured via environment variables. The canonical
references are:

- `backend/.env.example` — every backend variable with a comment and a
  safe default.
- `frontend/.env.example` — every frontend (Vite) variable.

This page summarises the **most important** ones for running and
operating CogniDQ. For the full list and inline guidance, read the
example files.

---

## Where config comes from

- **Local dev:** `backend/.env` and `frontend/.env` (gitignored).
- **Containers:** environment variables passed at runtime
  (`docker compose`, Kubernetes, etc.).
- **Process start:** `backend/app/core/config.py` parses values into a
  Pydantic settings object once, at import time. Changing an env var
  requires a restart.

Precedence: process environment > `.env` file > Pydantic defaults.

## Required (no safe defaults)

These have placeholders in `.env.example`. The app refuses to start
until you set them to real values.

| Variable | Notes |
|---|---|
| `JWT_SECRET_KEY` | Long random string. Rotating invalidates active sessions. |
| `DATASOURCE_ENCRYPTION_KEY` | Fernet key for connection passwords. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `CREDENTIAL_ENCRYPTION_KEY` | Second Fernet key for other secrets. |
| `MINIO_ROOT_PASSWORD` | Object storage admin password. |

## Database & queue

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | postgres on compose | `postgresql://user:pass@host:5432/db`. |
| `REDIS_URL` | redis on compose | `redis://host:6379/0`. |
| `DB_POOL_SIZE` | 10 | SQLAlchemy pool. |
| `DB_MAX_OVERFLOW` | 20 | Burst capacity. |

## Object storage

| Variable | Default | Notes |
|---|---|---|
| `MINIO_ENDPOINT` | `minio:9000` | host:port (no scheme). |
| `MINIO_ROOT_USER` | `minioadmin` | replace in production. |
| `MINIO_ROOT_PASSWORD` | placeholder | required. |
| `MINIO_BUCKET_NAME` | `dq-data-assets` | created on first start. |
| `MINIO_USE_SSL` | `false` | flip to true behind a TLS-terminating proxy. |

If you use AWS S3 instead of MinIO, set `MINIO_ENDPOINT=s3.amazonaws.com`,
`MINIO_USE_SSL=true`, and provide IAM credentials via standard AWS env
vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).

## Auth

| Variable | Default | Notes |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | JWT lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | refresh-token lifetime. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173` | comma-separated; lock to your frontend in production. |
| `PASSWORD_MIN_LENGTH` | 12 | for new local accounts. |

## Feature flags

CogniDQ uses `ENABLE_*` flags to gate experimental features. See
[open-source-strategy.md](open-source-strategy.md) for the full
classification.

| Flag | Default | Effect when off |
|---|---|---|
| `ENABLE_COMPLEX_FLOW_BUILDER` | `false` | Hide LangGraph-style multi-step flow builder; rules still work. |
| `ENABLE_OPENMETADATA_INTEGRATION` | `false` | Hide catalog import. |
| `ENABLE_KQI` | `false` | Hide Key Quality Indicator dashboards. |
| `ENABLE_CUSTOM_SQL_RULES` | `false` | Disallow `custom_sql` rule type. |

Default to *off* in production. Turn on in dev to evaluate.

## Mail (notifications)

| Variable | Default | Notes |
|---|---|---|
| `MAIL_BACKEND` | `console` | `console` logs emails to stdout; `smtp` for real delivery. |
| `MAIL_HOST` | — | SMTP host. |
| `MAIL_PORT` | `587` | SMTP port. |
| `MAIL_USERNAME` | — | SMTP user. |
| `MAIL_PASSWORD` | — | SMTP password. |
| `MAIL_FROM` | `noreply@cognidq.local` | sender address. |
| `MAIL_USE_TLS` | `true` | required for production. |

## Spark / execution

| Variable | Default | Notes |
|---|---|---|
| `DEPLOYMENT_MODE` | `docker-compose` | also: `kubernetes`, `aws-emr`, `azure-databricks`, `gcp-dataproc`. |
| `SPARK_MASTER_URL` | `spark://spark-master:7077` | adjust per deployment. |
| `SPARK_AUTO_THRESHOLD` | `50000` | rows above which the engine routes to Spark. |
| `MAX_EXECUTION_TIME_SECONDS` | `600` | per-rule cap. |
| `QUERY_TIMEOUT_SECONDS` | `60` | SQL query cap. |
| `MAX_ROWS_RETURNED` | `1000` | preview / sample bounds. |

## Evidence & retention

| Variable | Default | Notes |
|---|---|---|
| `EVIDENCE_SAMPLE_SIZE` | `100` | rows per failed execution. |
| `EVIDENCE_RETENTION_DAYS` | `90` | sweep deletes older objects. |
| `ISSUE_AUTO_CLOSE_DAYS` | `7` | auto-close after this long resolved. |
| `AUDIT_RETENTION_DAYS` | `365` | minimum recommended for governance. |

## Observability

| Variable | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`. |
| `LOG_FORMAT` | `json` | also: `text` for local readability. |
| `OTEL_ENABLED` | `false` | toggle OpenTelemetry. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | when OTEL is on. |
| `OTEL_SERVICE_NAME` | `cognidq-backend` | distinguish services in your tracing UI. |

## Frontend

`frontend/.env.example`:

| Variable | Notes |
|---|---|
| `VITE_API_URL` | Empty in dev (uses Vite proxy); set to your public API URL at build time in prod. |
| `VITE_APP_NAME` | Default "CogniDQ"; override for white-label demos. |
| `VITE_ENABLE_DEV_TOOLS` | Default false; turn on to mount React Query devtools etc. |

Vite reads env vars at **build time**; rebuild the frontend image to
change them in prod.

## Validating your configuration

The Makefile target:

```bash
make secret-scan
```

…runs gitleaks on the working tree. Use it before pushing to make sure
your `.env` (which should be gitignored) hasn't accidentally been
committed.

For correctness:

```bash
docker compose config --quiet
docker compose exec backend python -c "from app.core.config import settings; print(settings.model_dump_json(indent=2, exclude={'JWT_SECRET_KEY', 'DATASOURCE_ENCRYPTION_KEY', 'CREDENTIAL_ENCRYPTION_KEY', 'MINIO_ROOT_PASSWORD'}))"
```

This dumps the resolved settings (with secrets redacted) so you can
sanity-check the values the app actually saw.
