# Product scope

CogniDQ is an **open-source data quality control plane** for modern data
teams. It helps engineers, stewards, and analysts define data quality
rules, run checks against their datasets, find failed records, manage
issues and incidents, and monitor data quality over time.

This document describes what the product is, what it is not, and who it
is built for.

---

## 1. What CogniDQ is

CogniDQ is a self-hosted application composed of:

- a **frontend** (React + Vite) for rule authoring, dataset browsing,
  execution review, and dashboarding;
- a **backend API** (FastAPI) for users, tenants, workspaces, datasets,
  rules, executions, issues, incidents, and evidence;
- a **worker** (Celery + Redis) for asynchronous rule execution;
- an **execution engine** that runs checks via SQL pushdown or Apache
  Spark, depending on dataset size;
- **PostgreSQL** for metadata storage and **MinIO** (S3-compatible) for
  evidence/object storage in the local stack.

The full local stack is bootstrapped with a single `docker compose up -d`.

## 2. What CogniDQ does

The open-source core supports the following workflows.

### Rule authoring
- Built-in rule types: completeness, uniqueness, validity, consistency,
  accepted-values, regex, range, and comparison checks.
- Rule configuration via the UI or directly via API.
- Per-rule thresholds, severities, and ownership metadata.

### Dataset registration
- CSV uploads and local sample datasets.
- PostgreSQL connections (read-only by design).
- Schema browsing and field-level metadata.

### Execution
- Trigger checks on demand or on a schedule (Celery Beat).
- SQL pushdown for small/medium datasets; Spark for large datasets.
- Per-execution status, score, failed-row count, and timing.

### Issue and incident tracking
- Auto-create an *issue* when a rule fails.
- Group related issues into an *incident* with severity and assignment.
- Timeline of state changes per issue/incident.

### Evidence
- Store references to failed rows (sample subset by default) in the
  configured object store.
- Configurable retention and masking.

### Dashboards
- Workspace-level health summary: pass/fail counts, score trend, top
  failing rules, recent incidents.
- Rule-level execution history.

### Multi-tenant administration
- Platform / tenant / workspace hierarchy.
- Built-in roles: platform admin, tenant admin, workspace administrator,
  data engineer, data steward, business analyst, governance viewer.
- Permissions enforced at every API endpoint.

## 3. Who CogniDQ is for

- **Data engineers** who need an end-to-end DQ control plane without
  stitching together dbt tests, custom scripts, and dashboards.
- **Data stewards** who own quality KPIs and need an issue/incident
  workflow.
- **Platform / governance teams** who want a self-hosted, OSS, auditable
  alternative to closed SaaS DQ products.
- **Engineering teams evaluating** a DQ product before committing to a
  paid one.

## 4. Who CogniDQ is **not** for (today)

- Teams who want a fully-managed SaaS — the OSS edition is self-hosted.
  See [enterprise-edition.md](enterprise-edition.md).
- Teams who need certified production deployments out of the box — the
  Docker Compose stack is for local development and demos. Production
  deployment requires the hardening steps in
  [production-hardening.md](production-hardening.md).
- Teams who require enterprise SSO/SAML/OIDC, customer-side execution
  agents, advanced lineage-aware suggestions, or a managed cloud — those
  are roadmap items and/or commercial-edition concerns.

## 5. Non-goals

CogniDQ does **not** aim to be:

- An ETL/ELT tool. Use Airflow, dbt, Dagster, etc. and call CogniDQ from
  them.
- A generic data catalog. We integrate with catalogs (OpenMetadata,
  experimental) but do not replace them.
- A BI dashboarding product. Our dashboards are scoped to data quality
  metrics; for general BI, plug your warehouse into the BI tool of your
  choice.
- A real-time streaming-quality engine. Execution is batch (scheduled or
  on-demand) for now.

## 6. Distribution model

CogniDQ uses an **open-core** model. The contents of this repository are
the open-source core, available under Apache-2.0. See
[open-source-strategy.md](open-source-strategy.md) for what is included
and what is reserved for the future commercial edition.
