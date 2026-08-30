# Production hardening

> The default `docker-compose.yml` is for **local development and demos
> only**. It is not production-ready. This document lists the changes
> you must make before exposing CogniDQ to a real user.

If you are evaluating CogniDQ in a sandbox VM, you can ignore most of
this. If you are about to put it on the internet or onto a corporate
network with real datasets, read every section.

---

## 1. Secrets and keys

### 1.1 Generate fresh encryption keys

The default `backend/.env.example` ships with placeholder values for
`DATASOURCE_ENCRYPTION_KEY` and `CREDENTIAL_ENCRYPTION_KEY`. They are
**not** valid keys. Generate real ones locally and never commit them:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run that twice and put the two distinct keys into `backend/.env` (or
your secret manager).

If you ever copy-pasted the previously-leaked key (redacted here;
it begins with `vspbBrS-`), treat it as compromised
and re-encrypt all data sources under a new key.

### 1.2 Rotate every default password

The Compose stack ships with obviously-fake demo defaults:

| Service | Default | What to do |
|---|---|---|
| `db` (Postgres) | `postgres` / `postgres` | Replace with strong unique value, or use an external managed Postgres |
| `dq-testdb` | `testuser` / `testpassword` | Remove the test DB service entirely in prod |
| `dq-mysql`, `dq-mssql`, `dq-oracle` | various | Remove these test databases in prod |
| `minio` | `minioadmin` / `minioadmin` | Replace with strong values, or use S3 / Azure Blob / GCS instead |
| `flower` basic auth | must be set via `FLOWER_BASIC_AUTH` (no insecure default) | Replace with a strong value |
| `grafana` admin | `admin` / configurable | Replace and restrict access |

Use a secret manager (Vault, AWS Secrets Manager, GCP Secret Manager,
Azure Key Vault, Doppler, 1Password Secrets Automation) and inject
secrets via the environment. Never commit a `.env` file.

### 1.3 JWT signing key

`JWT_SECRET_KEY` must be a high-entropy random value:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Rotating it invalidates all current sessions.

---

## 2. Disable demo seed users

The `qa_seed_users.py` and similar seed scripts create well-known
accounts (`admin@example.com` etc.) with weak passwords for local
testing. These accounts must **never** exist in a production database.

- Do not run `qa_seed_users.py` against production.
- Audit your `users` table for any account whose email ends in
  `.test`, `.example`, `example.com`, or matches the `qa.*` pattern.
- Delete or disable them:

```sql
UPDATE users SET status = 'disabled' WHERE email LIKE '%.test'
   OR email LIKE '%@example.com'
   OR email LIKE 'qa.%';
```

---

## 3. Network exposure

Default Compose ports are bound to all interfaces. In production:

- Put the frontend and API behind a TLS-terminating reverse proxy
  (Caddy, Nginx, Traefik, AWS ALB, GCP HTTPS LB, Cloudflare, etc.).
- Do **not** expose Postgres, Redis, MinIO, Spark, Flower, or Grafana
  to the public internet.
- Bind internal services to a private network only:
  ```yaml
  ports: []   # remove the port mapping
  ```
- Use a firewall / security group to restrict ingress to the proxy.

### 3.1 HTTPS

Terminate TLS at the proxy. Force HTTP → HTTPS redirects. Use a real
certificate (Let's Encrypt is fine).

### 3.2 CORS

Set `BACKEND_CORS_ORIGINS` to the **exact** frontend origin(s). Do not
use `*` in production.

### 3.3 Rate limiting

`RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_PER_HOUR` are configurable in
`.env`. Tune them to your expected traffic and put a stronger rate
limiter at the proxy layer for unauthenticated routes (login, registration).

---

## 4. Database

- Use an **external, managed** PostgreSQL instance (RDS, Cloud SQL,
  Azure Database) rather than the bundled container in production.
- Enable automated backups with point-in-time recovery and a tested
  restore procedure.
- Restrict `POSTGRES_USER` to least-privilege per role
  (read-only for analytic queries, owner only for migrations).
- Enable TLS for connections and verify the server certificate.
- Tune `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` for your load.

### 4.1 Migrations

Run migrations on deploy, not on container start:

```bash
docker compose run --rm backend alembic upgrade head
```

Never auto-migrate in production.

---

## 5. Object storage (evidence)

For production:

- Use S3 / GCS / Azure Blob instead of the bundled MinIO.
- Set `MINIO_SECURE=true` (or use the cloud provider's TLS).
- Enable bucket-level encryption (SSE-S3 or KMS).
- Configure object retention / lifecycle rules per
  workspace policy.
- Restrict bucket access to the backend / worker IAM principal only.

Failed-row evidence may contain sensitive data. See §8.

---

## 6. Workers and scheduling

- Run multiple `worker` replicas behind a fair queue.
- Run exactly **one** `beat` replica (Celery Beat is not designed for
  HA; use a leader-election lock or a dedicated host).
- Persist `celerybeat-schedule` to a stable volume; do **not** commit it.
- Put Flower behind authentication and the proxy. Do not expose port
  5555 publicly.

---

## 7. Spark

- Do not use the bundled `spark-master` container in production. Use a
  managed Spark service (AWS EMR, Databricks, GCP Dataproc, Azure
  Synapse) and configure CogniDQ to submit jobs there.
- If you must self-manage Spark, isolate it on a private network,
  enable encryption-in-transit, and apply per-tenant resource quotas.
- Set `ENABLE_CLUSTER_MODE=true` only when the cluster is sized for
  your expected concurrency.

---

## 8. Sensitive data: failed-row evidence

When a rule fails, CogniDQ may store a sample of failing rows as
**evidence**. These rows can contain PII, financial data, or
trade-secret information.

Recommendations:

- Configure per-workspace masking / hashing of sensitive fields **before**
  rows are written to evidence storage.
- Set short retention (e.g. 7–30 days) on the evidence bucket.
- Restrict evidence-read permission to a small set of roles.
- Audit every read of evidence and alert on anomalies.
- For high-sensitivity environments, store **only references**
  (primary keys) rather than the full row, and resolve them at view
  time against the source system. (Evidence vault / unmasking workflow
  is on the enterprise roadmap.)

---

## 9. Logging

- Set `LOG_LEVEL=INFO` (not `DEBUG`) in production.
- Ship logs to a central log store (Loki, ELK, Datadog, Splunk) and
  retain for at least 30–90 days for incident response.
- Make sure logs do **not** contain raw passwords, JWTs, or evidence
  rows. The codebase tries to redact these but additions can regress;
  audit your custom code.
- Rotate / delete `backend/logs/*.log` mounts in production.

---

## 10. Monitoring

Health endpoints:

- `GET /health` — liveness; `200` means the process is alive.
- `GET /ready` — readiness; verifies DB / Redis / object storage.
- `GET /metrics` — Prometheus exposition (if enabled).

Wire these into your orchestrator's health checks (k8s probes, ALB
target group health checks, Compose `healthcheck`).

Set up alerts on:

- `/ready` failing for more than 1–2 minutes
- worker queue length growing without bound
- rule execution error rate over a threshold
- unusual rate of failed login attempts

---

## 11. Authentication and SSO

The OSS core ships with local password login. For corporate
deployments you typically want SSO. Today there are two paths:

1. Put CogniDQ behind an authenticating reverse proxy
   (oauth2-proxy, Cloudflare Access, AWS ALB OIDC, Pomerium) and
   pre-provision users by email.
2. Wait for the planned enterprise edition, which will include
   first-class SAML / OIDC / SCIM. See
   [docs/enterprise-edition.md](enterprise-edition.md).

Either way, **disable self-registration** in production:

```env
ALLOW_PUBLIC_REGISTRATION=false
```

(The default is already `false`.)

---

## 12. Backups and disaster recovery

- Postgres: daily snapshots, weekly full backups, tested restore at
  least quarterly.
- Object storage: enable bucket versioning + cross-region replication
  for evidence and uploaded datasets.
- Redis: it is acceptable to lose Redis state on restart (it holds
  Celery queue + cache). Make sure persistence is **off** (default) in
  production unless you have a specific reason.
- Document your restore runbook.

---

## 13. Upgrade procedure

- Pin to specific image tags, not `latest`.
- Test upgrades on a staging environment with a recent prod data
  snapshot.
- Read CHANGELOG release notes before upgrading.
- Migrations are backwards-compatible **within a minor release**;
  major release upgrades may require a downtime window.

---

## 14. Production checklist

Run through this before you take a CogniDQ deployment live.

- [ ] All default passwords rotated.
- [ ] `DATASOURCE_ENCRYPTION_KEY` and `CREDENTIAL_ENCRYPTION_KEY`
      generated locally and stored in a secret manager.
- [ ] `JWT_SECRET_KEY` rotated; not the example value.
- [ ] Demo seed users disabled / deleted.
- [ ] Frontend + API behind a TLS reverse proxy with HSTS.
- [ ] CORS limited to known origins.
- [ ] Postgres external, with backups + encryption at rest + TLS.
- [ ] Object storage external (S3/GCS/Azure Blob), encrypted.
- [ ] Redis not exposed to the internet.
- [ ] Spark either external or isolated on a private network.
- [ ] Flower / Grafana behind auth and not publicly exposed.
- [ ] Failed-row evidence retention + masking configured per workspace.
- [ ] `LOG_LEVEL=INFO`; logs shipped to central store; no secret leakage.
- [ ] Alerts wired on `/ready`, queue depth, error rate.
- [ ] Image tags pinned.
- [ ] Backup + restore runbook tested.
- [ ] `ALLOW_PUBLIC_REGISTRATION=false`.

If you check every box, you are not yet "secure" — you are *no longer
trivially insecure*. Continue with normal good practice: vulnerability
scanning, dependency updates, audit log review, periodic
penetration tests.
