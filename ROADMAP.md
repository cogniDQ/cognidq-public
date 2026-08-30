# Roadmap

A realistic, dated-by-milestone view of where CogniDQ is going. Items
are grouped by release; within a release they are ordered by priority.

> Roadmap is a public planning artifact, not a contract. Items can move
> between releases as we learn from real usage.

---

## v0.1.0-alpha — first public release

**Theme:** "It runs locally and the core flow works."

This is the initial open-source release. Everything in this milestone is
in the [Core tier](docs/open-source-strategy.md).

- [x] Apache-2.0 license + community files (CONTRIBUTING, SECURITY,
      SUPPORT, CODE_OF_CONDUCT)
- [x] Secret + internal-reference audit
- [x] One-command Docker Compose local stack
      (frontend, backend, worker, beat, flower, postgres, redis, minio,
      spark master/workers, history server)
- [x] Auth with built-in roles + workspace/tenant model
- [x] Dataset registration: CSV upload + PostgreSQL connection
- [x] Rule types: completeness, uniqueness, validity, consistency,
      accepted-values, regex, range, comparison
- [x] On-demand and scheduled execution (Celery Beat)
- [x] Issue + incident lifecycle
- [x] Evidence references for failed rows
- [x] Workspace dashboard with health summary
- [ ] Demo data + walkthrough
- [ ] Backend test scaffolding + RBAC tests
- [ ] Frontend test scaffolding (Vitest + Playwright smoke)
- [ ] CI: lint + test + build + secret scan
- [ ] Public docs site at `docs/`

**Known limitations** are documented in
[docs/known-limitations.md](docs/known-limitations.md).

---

## v0.2.0

**Theme:** "Production-aware defaults."

- Hardened Docker Compose (`infra/docker-compose.prod.yml`) with TLS
  reverse proxy, external Postgres template, and stricter defaults
- More rule types: freshness, schema-drift, custom-SQL (sandboxed),
  cross-dataset comparison
- Better evidence handling: configurable retention, masking presets,
  exportable audit log
- Background job observability via `/metrics` (Prometheus exposition)
- First-class connector tests for PostgreSQL + MySQL
- Rule import/export (JSON/YAML)
- Frontend: improved rule builder UX, dashboard polish, light mode
- Docs: deployment guide, troubleshooting, API reference auto-generated
  from OpenAPI

---

## v0.3.0

**Theme:** "Catalog + lineage integration."

- OpenMetadata read integration: pull dataset metadata, suggest rules
  based on column types
- Lineage-aware rule suggestions (read-only metadata, no writes)
- Improved dashboards: per-domain health, SLA-style targets
- Rule templates and a small standard library
- Notification connectors: webhook, Slack, MS Teams, email (SMTP)
- More mature scheduling (cron-style + dependency-based)

---

## v1.0.0

**Theme:** "Production-ready and stable."

- Stable, versioned API (no breaking changes without deprecation)
- Documented data model with backwards-compatible migrations
- Full RBAC test matrix
- Documented backup / restore / upgrade procedures
- A reference Kubernetes deployment (Helm chart) maintained by the
  community
- Performance benchmarks against representative datasets
- Comprehensive end-to-end Playwright suite
- First production reference customers

---

## Beyond 1.0 (directional, not committed)

- More connectors (Snowflake, BigQuery, Databricks, Redshift, MS SQL,
  Oracle) graduating from Experimental to Core where there are tests
- Rule authoring API + SDK for programmatic rule definitions
- Plugin system for custom rule types
- Anomaly detection on metric time series (Core or Enterprise depending
  on complexity of the model)
- Improved natural-language rule builder if and only if it can meet a
  reliability bar

The following items are likely **not** going into the OSS core; they
belong to the future commercial / enterprise edition described in
[docs/enterprise-edition.md](docs/enterprise-edition.md):

- SAML / OIDC / SCIM
- Customer-managed keys, evidence vault with approval flows
- Customer-side execution agents
- Managed cloud
- Dedicated support, SLAs, and professional services

---

## How items get on the roadmap

- Open a [Feature request](https://github.com/aiexplainedhub/cognidq/issues/new?template=feature_request.md).
- Discuss the use case publicly.
- Maintainers move items between milestones based on:
  1. Number of independent users asking for it.
  2. Whether someone is willing to implement it.
  3. Whether it pulls weight in the Core tier vs. better belonging in
     the Enterprise tier.

If a milestone deadline matters to you, say so on the issue. We are not
running a vote, but we listen.
