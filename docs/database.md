# Database

CogniDQ stores all metadata (tenants, workspaces, users, roles,
datasets, connections, rules, executions, issues, incidents, audit
events) in **PostgreSQL**.

For the architecture context see [architecture.md](architecture.md).
For binary artifacts (failed-row evidence, uploads), see
[evidence.md](evidence.md).

---

## Supported versions

PostgreSQL 14, 15, 16. The local stack ships with 15 in
`docker-compose.yml`. There is no plan to support pre-14 versions.

## Schema management

Schema is managed by **Alembic**. Migrations live in
`backend/alembic/versions/`.

### Apply migrations

```bash
make migrate
# or:
docker compose exec backend alembic upgrade head
```

### Generate a new migration

```bash
make makemigration MSG="add foo column to bar"
# or:
docker compose exec backend alembic revision --autogenerate -m "add foo column to bar"
```

`--autogenerate` compares your SQLAlchemy models to the live DB and
proposes a migration. Always **hand-review the output** — autogenerate
is good but not infallible:

- it does not detect column renames; it sees them as drop+add. Edit
  the migration to use `op.alter_column(... new_column_name=...)`.
- it can miss server-side defaults and check constraints.
- it does not produce data migrations; if you need to backfill data,
  add an explicit `op.execute(...)` block.

### Migration discipline

- One concept per migration. Don't bundle unrelated schema changes.
- Every schema change must be backward-compatible with the previous
  release where reasonable. If a migration is breaking (column drop,
  not-null on existing column, etc.), document it in the
  [CHANGELOG](../CHANGELOG.md) under "BREAKING".
- Do not edit a migration that has been merged. Add a follow-up.
- Keep migrations idempotent within their own scope — running `upgrade`
  twice should not fail (Alembic tracks state in `alembic_version`,
  but the SQL itself should be safe).

### Downgrades

Every migration generates a `downgrade()` function. We do not test
downgrades in CI; treat them as best-effort. The supported recovery
path for a bad migration is **restore from backup**, not `downgrade`.

## Bootstrap

There are two ways to bootstrap an empty database:

1. **From migrations (recommended for production):**
   ```bash
   docker compose exec backend alembic upgrade head
   ```
   This applies the full migration sequence.

2. **From the legacy SQL bundle (`backend/scripts/init_db.sql`,
   internal):** kept for compatibility with old QA flows.
   Do not use this path for new deployments — it can drift from the
   migration sequence.

## Seed data

The seed loader populates the demo tenant, workspace, users, datasets,
and rules.

```bash
make seed
# or:
docker compose exec backend python scripts/seed_demo_data.py
```

What it creates:

- **Tenant:** *Acme Corp* (slug `acme`).
- **Workspace:** *Demo Workspace* inside *Acme Corp*.
- **Users:** `admin@example.com`, `tenant.admin@example.com`,
  `ws.admin@example.com`, `engineer@example.com`,
  `steward@example.com`, `analyst@example.com`,
  `viewer@example.com` — all with password
  `change-me-strong-password`.
- **Datasets:** `customers`, `orders`, `payments`, `products`
  (registered against the CSV files in `examples/datasets/`).
- **Rules:** the example rules in `examples/rules/`, bound to the
  registered datasets.

The loader is idempotent: re-running it skips records that already
exist by primary key / unique key. Use `make reset` (DESTRUCTIVE) if
you want a clean slate.

> Demo passwords are intentionally weak. Replace them in any non-local
> deployment. See [production-hardening.md](production-hardening.md).

## Connection settings

In production, set:

```env
DATABASE_URL=postgresql://dq_app:<strong-password>@db:5432/cognidq
DB_POOL_SIZE=10        # baseline connections
DB_MAX_OVERFLOW=20     # burst capacity
DB_POOL_TIMEOUT=30     # seconds before raising on a full pool
DB_POOL_RECYCLE=1800   # seconds before recycling a connection
```

The application user (`dq_app` above) needs:

- `CREATE / SELECT / INSERT / UPDATE / DELETE` on `public` (or whatever
  schema you put CogniDQ in).
- It does **not** need superuser. Run migrations with a higher-privilege
  account if you separate roles.

## Backups

| What | How | Cadence |
|---|---|---|
| Logical | `pg_dump --format=custom` | nightly + before upgrades |
| Physical | base backup + WAL archiving | continuous (cloud-managed) |
| Restore drill | restore into a scratch DB | quarterly |

Encryption: WAL and base backups should be encrypted at rest. The
application-level Fernet keys
(`DATASOURCE_ENCRYPTION_KEY`, `CREDENTIAL_ENCRYPTION_KEY`) must be
backed up *separately* — losing them makes encrypted credentials
unrecoverable.

## Performance & operations

- **Indexes:** all foreign keys are indexed. Query patterns on
  `executions(rule_id, started_at)` and `issues(workspace_id, status)`
  are indexed. If you add a new query path, add the corresponding
  index in the same migration.
- **Vacuum / autovacuum:** out of the box settings are fine for the
  demo. For production at scale, tune `autovacuum_vacuum_scale_factor`
  on the `executions` and `audit_events` tables, since they grow.
- **Partitioning:** not used in v0.1. Roadmap: monthly partitioning of
  `executions` and `audit_events` once we hit volumes that warrant it.
- **Long-running queries:** dashboards recompute aggregates on each
  request. If your workspace has thousands of executions per day,
  expect 1–3 s latencies; pre-aggregation lands in v0.2.

## Schema overview

Top-level entities (this is approximate; the canonical reference is
`backend/app/models/`):

```text
tenants
  └── workspaces
        ├── workspace_members → users
        ├── connections
        ├── datasets
        │     └── dataset_fields
        ├── rules
        │     └── rule_versions
        ├── executions  (rule_id, rule_version, score, status, evidence_ref)
        ├── issues  (rule_id, status, severity, assignee, incident_id)
        ├── incidents
        └── audit_events

users
  └── api_tokens
  └── tenant_memberships
```

Every workspace-owned table includes both `tenant_id` and
`workspace_id` to make cross-tenant isolation queryable at the row
level even if a future migration adopts PostgreSQL Row-Level Security.

## Direct DB access

For debugging:

```bash
make psql
# or:
docker compose exec db psql -U postgres -d dataquality_db
```

Read-only is recommended; CogniDQ does not have a UI for arbitrary SQL
on its own metadata.

## What lives outside Postgres

- **Failed-row evidence:** MinIO / S3 — see
  [evidence.md](evidence.md).
- **CSV uploads:** MinIO / S3.
- **Celery queue + beat schedule state:** Redis. Beat persists its
  schedule to a small file (`celerybeat-schedule`) that lives only on
  the beat container's writable volume.
- **Worker logs:** stdout. The DB does not store logs.

## Limits

- Single-region only. Multi-region replication is out of scope for
  v0.1.
- No row-level security at the DB layer by default; isolation is
  enforced in the app. High-trust deployments should consider
  schema-per-tenant or PostgreSQL RLS — see
  [tenant-workspace-model.md](tenant-workspace-model.md).
- The audit table is append-only at the application layer; there is
  no DB-enforced append-only constraint by default.
