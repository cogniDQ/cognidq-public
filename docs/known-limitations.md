# Known limitations (v0.1.0-alpha)

This page is the honest list of things CogniDQ does not yet do well in
the alpha. We publish it so users can decide whether to adopt now or
wait.

For the trajectory of fixes, see [../ROADMAP.md](../ROADMAP.md).

---

## Stability

- **Alpha quality.** The rule engine, rule types, and core RBAC are
  stable; surface area outside that may break between minor releases.
- **No deprecation policy yet.** Until v0.2, we may rename API fields
  or change response shapes between releases. After v0.2, additive-only
  changes on `/api/v1` will be the contract.
- **No semver yet.** v0.x releases are pre-1.0; expect minor bumps to
  carry breaking changes occasionally, with notes in the
  [CHANGELOG](../CHANGELOG.md).

## Connectors

- Only **PostgreSQL** is exercised in CI.
- MySQL, MSSQL, Oracle work in code paths that are not regression-tested.
- Snowflake, BigQuery, Databricks, Redshift, and Spark-on-object-storage
  are **experimental**: code path exists, expect bugs.
- OpenMetadata read integration is behind a feature flag.

## Rule types

- `freshness` and `custom_sql` are experimental in v0.1; off by default.
- Cross-dataset rules are limited to two datasets that share a
  connection. Joining datasets across connections is not supported.
- The engine does **not** dedupe identical concurrent executions
  triggered by both the schedule and a manual "Run now" click.

## Execution

- Spark execution is verified only against the bundled local Spark
  cluster. Managed Spark targets (EMR, Databricks, Dataproc) have code
  paths but are not regression-tested.
- There is no soft-cancel for in-flight Celery tasks; you can revoke
  via Flower but the task may still finish.

## UI

- The flow / DAG builder is **experimental** and gated by
  `ENABLE_COMPLEX_FLOW_BUILDER`. Off by default.
- KQI dashboards are gated by `ENABLE_KQI`.
- Rule import / export is API-only. A UI flow lands in v0.2.
- The audit-log UI is read-only and minimal; advanced search lands in
  v0.2.
- No dark mode.
- Internationalisation: English only; copy is not externalised.

## Auth

- Local users + JWT + personal API tokens. SAML, OIDC, SCIM are
  intentionally out of scope for OSS — see
  [docs/enterprise-edition.md](enterprise-edition.md).
- No service-account first-class object yet; use a user with a
  long-lived token as the substitute.
- Password reset is logged (console mail) by default; production
  deployments must wire SMTP.

## Multi-tenancy

- Cross-tenant isolation is enforced at the application layer. Database
  row-level security is **not** enabled by default. For high-trust
  multi-tenant deployments, additional hardening is required (separate
  schemas / databases per tenant, or PostgreSQL RLS).
- Tenant-aware rate limiting is not built in; do it at your gateway.

## Storage

- Evidence retention sweep is best-effort and not transactional with
  the execution table. A failed sweep may leave orphaned objects in
  MinIO/S3.
- No bucket lifecycle rules are configured by default — apply them at
  the cloud-storage layer.

## Observability

- `/api/v1/system/metrics` is not authenticated; protect at the
  reverse proxy.
- No bundled Grafana alert rules. Dashboards exist; alerting is yours.
- Tracing emits spans but no exemplars.

## Performance

- Backend pagination caps responses at 1 000 items per page. Some list
  endpoints do not yet paginate at all.
- Dashboard endpoints recompute aggregates on each request. For
  workspaces with thousands of executions per day, expect 1–3 s
  latencies; pre-aggregation lands in v0.2.
- The schema-inference step on very wide tables (>1 000 columns) is
  slow.

## Scale

- Verified on workspaces with ≤500 active rules and ≤1 M total
  executions in a workspace. Beyond that, you may need to tune Postgres
  (indexes are present; vacuum / autovacuum tuning is yours).
- Spark cluster sizing for genuinely large datasets (≥100 M rows) is
  outside the bundled compose stack.

## Security

- Default compose passwords are weak by design (demos). The hardening
  doc explicitly tells you to rotate them; we do not block startup if
  you don't.
- The OSS frontend does not ship a Content Security Policy by default.
- Pre-commit `gitleaks` is configured; you must `pre-commit install`
  yourself for it to run on commit.
- We have not had an external security review.

## Build / release

- No published Docker images yet. Build locally for now.
- No Helm chart yet.
- No release-binary signing yet.

---

If something on this list is a blocker for you, please open a
[GitHub issue](https://github.com/aiexplainedhub/cognidq/issues)
or a [Discussion](https://github.com/aiexplainedhub/cognidq/discussions);
that signal is what drives the roadmap.
