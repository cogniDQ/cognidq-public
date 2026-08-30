# CogniDQ

> An open-source data quality control plane.
> Connect data, author rules, run them on a schedule, triage failures,
> and prove quality over time.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 20+](https://img.shields.io/badge/node-20+-339933.svg)](https://nodejs.org/)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](ROADMAP.md)

CogniDQ is a multi-tenant control plane for data quality. It is **not**
a streaming engine, **not** a metadata catalog, and **not** a writeback
tool — it is the place where you decide what "good data" means in your
organisation, run those checks against your data sources, and act on
failures.

> **Status: v0.1.0-alpha.** Core flows (rules, executions, issues,
> incidents, evidence, RBAC) are stable. The surrounding surface area
> is moving fast. See [ROADMAP.md](ROADMAP.md) and
> [docs/known-limitations.md](docs/known-limitations.md).

---

## Table of contents

- [Features](#features)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Features

- **Rules-first.** A rich library of rule types out of the box —
  completeness, uniqueness, validity, regex, accepted values, range,
  comparison, consistency. Each rule is versioned and explainable.
  See [docs/rule-types.md](docs/rule-types.md).
- **Execute where it makes sense.** SQL pushdown for small datasets,
  Apache Spark for large ones — chosen automatically per rule.
- **Multi-tenant by design.** Three-level hierarchy of platform,
  tenant, workspace. Strong isolation; per-workspace authoring.
  See [docs/tenant-workspace-model.md](docs/tenant-workspace-model.md).
- **RBAC with seven built-in roles.** Platform admin, tenant admin,
  workspace administrator, data engineer, data steward, business
  analyst, governance viewer. See [docs/rbac.md](docs/rbac.md).
- **Issues + incidents.** Failures auto-create issues; group related
  issues into incidents. See [docs/issues.md](docs/issues.md) and
  [docs/incidents.md](docs/incidents.md).
- **Evidence.** Each failed run stores a sample of failing rows so
  triage is grounded in real data. See [docs/evidence.md](docs/evidence.md).
- **Schedulable.** Cron or interval schedules per rule, run by Celery
  Beat + a worker pool.
- **Apache-2.0 licensed.** Open core; explicit list of features held
  back for the commercial edition is published in
  [docs/enterprise-edition.md](docs/enterprise-edition.md).

## Quick start

```bash
git clone https://github.com/aiexplainedhub/cognidq.git
cd cognidq

# Create env files (root .env is read by Docker Compose for variable interpolation)
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Edit .env: fill in OPENAI_API_KEY, MINIO_ROOT_PASSWORD, GF_SECURITY_ADMIN_PASSWORD,
# SECRET_KEY, JWT_SECRET_KEY and generate two distinct Fernet keys:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste them into DATASOURCE_ENCRYPTION_KEY and CREDENTIAL_ENCRYPTION_KEY in .env
# (and copy the same values to backend/.env).

docker compose up -d
docker compose exec backend python scripts/run_migrations.py
docker compose exec backend python scripts/seed_demo_data.py
```

Open <http://localhost:5173> and sign in:

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `change-me-strong-password` | platform admin |
| `steward@example.com` | `change-me-strong-password` | data steward |
| `viewer@example.com` | `change-me-strong-password` | governance viewer |

> **Demo passwords are weak by design.** They exist to make the demo
> painless. Never use them outside your local laptop. See
> [docs/production-hardening.md](docs/production-hardening.md).

Full instructions: [docs/getting-started.md](docs/getting-started.md).
First-rule walk-through: [docs/first-check.md](docs/first-check.md).

### Useful commands

```bash
make help          # all developer tasks
make migrate       # apply migrations
make seed          # load demo data
make logs          # tail backend + worker
make test          # run all tests
make secret-scan   # gitleaks on the working tree
make reset         # DESTRUCTIVE: wipe local volumes
```

## Architecture

CogniDQ is a FastAPI backend, a React frontend, a Celery worker pool
with Beat for scheduling, Postgres for state, Redis for the queue,
MinIO for evidence storage, and an Apache Spark cluster for large-data
execution.

```text
              ┌──────────────┐
              │  React UI    │
              │  (Vite, TS)  │
              └──────┬───────┘
                     │ REST / JWT
              ┌──────▼───────┐     ┌─────────────┐
              │  FastAPI     │────▶│ PostgreSQL  │
              │  backend     │     └─────────────┘
              └──────┬───────┘     ┌─────────────┐
                     │ enqueue ────▶│   Redis    │
                     │              └─────────────┘
              ┌──────▼───────┐     ┌─────────────┐
              │  Celery      │────▶│  MinIO/S3  │ (evidence)
              │  worker(s)   │     └─────────────┘
              └──────┬───────┘     ┌─────────────┐
                     │ submit ─────▶│   Spark    │ (large datasets)
                     │              └─────────────┘
              ┌──────▼───────┐
              │  Source DBs  │ (read-only)
              └──────────────┘
```

Full architecture incl. sequence diagrams: [docs/architecture.md](docs/architecture.md).

## Documentation

User-facing docs live in [`docs/`](docs/):

- [Getting started](docs/getting-started.md) — install + run
- [First check](docs/first-check.md) — author and run your first rule
- [Architecture](docs/architecture.md) — what each component does
- [Rule engine](docs/rule-engine.md), [Rule types](docs/rule-types.md)
- [Connectors](docs/connectors.md), [Datasets](docs/datasets.md)
- [RBAC](docs/rbac.md), [Tenant / workspace model](docs/tenant-workspace-model.md)
- [Issues](docs/issues.md), [Incidents](docs/incidents.md), [Evidence](docs/evidence.md)
- [API reference](docs/api-reference.md)
- [Configuration](docs/configuration.md)
- [Database](docs/database.md)
- [Observability](docs/observability.md)
- [Deployment](docs/deployment.md)
- [Production hardening](docs/production-hardening.md) — read before exposing
- [Demo walkthrough](docs/demo-walkthrough.md)
- [Testing](docs/testing.md)
- [Repository structure](docs/repository-structure.md)
- [Open-source strategy](docs/open-source-strategy.md) — Core / Experimental / Enterprise tiers
- [Enterprise edition](docs/enterprise-edition.md) — what is *not* in this repo
- [Known limitations](docs/known-limitations.md)
- [Publishing to a fresh repo](docs/publishing-to-fresh-repo.md) — maintainer how-to

## Roadmap

See [ROADMAP.md](ROADMAP.md). Headlines:

- **v0.1.0-alpha** (current target): everything in this README is
  reachable from a fresh clone in under 10 minutes.
- **v0.2.0**: Helm chart, dashboard pre-aggregation, audit-search UI,
  rule import/export UI, custom-SQL rules out of experimental.
- **v0.3.0**: graduate beta connectors (MySQL, MSSQL, Oracle), service
  accounts, dark mode.
- **v1.0.0**: stable API contract, published images, first signed
  release.

## Contributing

We welcome contributions — bug reports, feature requests, docs, code.
Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

If you are unsure whether something fits, please open an
[issue](https://github.com/aiexplainedhub/cognidq/issues) or a
[discussion](https://github.com/aiexplainedhub/cognidq/discussions)
first.

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you are expected to uphold it.

## Security

Found a vulnerability? **Do not open a public issue.** Report it
privately via [GitHub Security Advisories](https://github.com/aiexplainedhub/cognidq/security/advisories/new),
following [SECURITY.md](SECURITY.md).

The default compose configuration is **not safe for production
exposure**. Apply the [production hardening](docs/production-hardening.md)
checklist before any internet-facing deployment.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The project is open core: the OSS edition under Apache-2.0 is the
canonical platform; a commercial edition (managed cloud, advanced
multi-tenant, SSO/SCIM) is built on top of it. The split is documented
in [docs/open-source-strategy.md](docs/open-source-strategy.md) and
[docs/enterprise-edition.md](docs/enterprise-edition.md).
