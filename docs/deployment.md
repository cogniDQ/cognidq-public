# Deployment

This page collects deployment notes for CogniDQ beyond the local
laptop / `docker compose up` flow that
[getting-started.md](getting-started.md) covers.

> **Read first:** [production-hardening.md](production-hardening.md).
> The default compose configuration is **not safe for production
> exposure**. Apply the hardening checklist before any internet-facing
> deployment.

---

## Topology choices

CogniDQ is small enough to deploy in three reasonable shapes. Pick the
one that matches your operational maturity.

### A. Single VM with Docker Compose

For internal demos and small teams.

- 1 VM (8 vCPU / 16 GB RAM is comfortable for ~50 active rules).
- Docker Engine + Docker Compose v2.
- Reverse proxy (Caddy / Traefik / Nginx) terminating TLS in front of
  the frontend on `:443` and the backend on `/api`.
- Postgres, Redis, MinIO inside compose **for demos only**; for
  production move them to managed services.

### B. Kubernetes

For teams already running on Kubernetes.

- One namespace per environment.
- Deployments: `backend`, `worker`, `beat`, `frontend` (or serve from a
  CDN), optionally `flower`.
- StatefulSets / managed services: Postgres, Redis, S3-compatible
  object store.
- Ingress for the frontend and the API.
- Spark master + workers as a separate deployment, or use a managed
  Spark service (EMR, Databricks, Dataproc) — see Spark notes below.

There is no Helm chart in v0.1.0-alpha. A community Helm chart is on
the [roadmap](../ROADMAP.md).

### C. Hybrid: Kubernetes for app, managed services for state

The pragmatic option for teams with cloud-managed Postgres / Redis /
S3. Deploy the app tier on Kubernetes; point at managed state.

Recommended for v0.2 onwards.

## What needs to be configured

Independent of topology, you must set:

| Setting | Why |
|---|---|
| `JWT_SECRET_KEY` | Token signing. Long random string. |
| `DATASOURCE_ENCRYPTION_KEY` | Fernet key for connection passwords. |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for other credentials. |
| `DATABASE_URL` | Production Postgres URL. |
| `REDIS_URL` | Production Redis URL. |
| `MINIO_*` / `S3_*` | Object storage endpoint + credentials. |
| `BACKEND_CORS_ORIGINS` | Lock to your frontend origin only. |
| `MAIL_*` | Real SMTP for issue / incident notifications. |
| `ENABLE_*` feature flags | Off for experimental features. |

The full reference is in `backend/.env.example` and
[production-hardening.md](production-hardening.md).

## Build artifacts

### Backend image

```bash
docker build -t your-registry/cognidq-backend:0.1.0-alpha backend/
```

The same image runs as `backend`, `worker`, and `beat` with different
entrypoints:

- `backend`: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `worker`: `celery -A app.celery_app worker -l info`
- `beat`: `celery -A app.celery_app beat -l info`

### Frontend image / static build

```bash
cd frontend
npm ci
npm run build
# dist/ is the deployable output
```

Serve `frontend/dist` from any static host (Nginx, CDN, S3 + CloudFront,
GitHub Pages with caveats). Set `VITE_API_URL` at *build time* to the
public API URL.

## Spark

Local dev runs the bundled Spark master + 2 workers in compose. In
production, options:

- **Continue with self-managed Spark** (Kubernetes operator or
  standalone). Set `SPARK_MASTER_URL` accordingly.
- **Switch to a managed runtime**: AWS EMR (`DEPLOYMENT_MODE=aws-emr`),
  Databricks (`azure-databricks`), GCP Dataproc (`gcp-dataproc`).
  These code paths are present but exercised lightly in v0.1; expect
  rough edges and pin to `worker` images that match your Spark
  cluster's runtime.

If your dataset volumes are modest, you can disable Spark entirely with
`SPARK_AUTO_THRESHOLD=999999999` and rely on SQL pushdown only.

## Reverse proxy / TLS

Run a reverse proxy in front of:

- the frontend (static host or `frontend` container) on `:443`,
- the backend at `/api` on `:443`.

Set:

- HTTPS only (HSTS at the proxy),
- `X-Forwarded-*` and `Forwarded` headers passed through,
- a real CSP (the OSS frontend does not ship one),
- block direct access to MinIO `:9000`, Spark master `:8080`, and
  Flower `:5555` from the public internet.

Example Nginx and Caddy snippets land in v0.2; for v0.1.0-alpha use
your team's standard config.

## Backups

| What | How |
|---|---|
| Postgres | `pg_dump` nightly + WAL archiving. Test restore quarterly. |
| MinIO / S3 | bucket replication, versioning, lifecycle rules. |
| Encryption keys | stored **outside** the same KMS scope as the DB; if you lose them, encrypted credentials are unrecoverable. |
| Redis | not backed up (queue + cache only). |

## Upgrades

The supported upgrade path is:

1. read the [CHANGELOG](../CHANGELOG.md),
2. take a Postgres backup,
3. deploy the new images,
4. run `alembic upgrade head` (Makefile: `make migrate`),
5. monitor.

Migrations are designed to be backward-compatible with the previous
release where possible. Rolling restarts are safe in v0.1; rolling
schema changes are not yet a contract — plan a brief maintenance
window for schema migrations.

## Multi-region / high availability

Out of scope for v0.1. The architecture admits it (stateless app tier,
external state stores), but we have not exercised it. If you need
multi-AZ HA today, run two backend replicas behind an LB plus a single
beat (single-instance is required) and a Postgres + Redis HA pair from
your cloud provider.

## What CogniDQ does not deploy for you

- **Source databases.** CogniDQ reads them; it doesn't operate them.
- **Spark cluster.** Bundled for dev; bring your own for prod.
- **Identity provider.** OSS edition uses local users + JWT. SAML /
  OIDC / SCIM are not in this repo — see
  [enterprise-edition.md](enterprise-edition.md).
- **Catalog.** OpenMetadata read integration is experimental;
  CogniDQ does not replace a catalog.

## Checklist before going live

Use [production-hardening.md](production-hardening.md). The short
version:

- [ ] Real (not demo) Postgres, Redis, S3 endpoints.
- [ ] Strong, rotated `*_ENCRYPTION_KEY` and `JWT_SECRET_KEY`.
- [ ] Default demo users removed; real SSO or local users with strong
      passwords created.
- [ ] HTTPS only; CSP set; `BACKEND_CORS_ORIGINS` locked down.
- [ ] Backups in place and tested.
- [ ] Logs and metrics flowing into your aggregator.
- [ ] Experimental feature flags **off**.
- [ ] Audit log retention set.
