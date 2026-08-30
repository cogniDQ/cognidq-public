# Enterprise edition

This document describes features that are **not** part of the open-source
core. They are placeholders for a future commercial / managed edition and
are listed here so adopters know what to expect — and what not to expect
— from the OSS repository.

> Nothing in this document is a sales commitment. Features and timing
> may change.

---

## Why an enterprise edition?

The OSS core gives you a self-hostable, working data quality platform.
But large organisations typically also need:

- enterprise authentication and identity governance,
- formal support with SLAs,
- a managed cloud option,
- features that only make sense at scale (advanced audit, evidence
  vaulting, customer-side execution agents, etc.).

Building, certifying, and supporting those features takes ongoing
engineering investment. To keep the OSS core healthy and free, we plan
to fund it through an enterprise edition.

---

## Planned enterprise capabilities

### Identity & access

- **SAML 2.0** SSO
- **OIDC** SSO with major IdPs (Okta, Auth0, Azure AD, Google
  Workspace)
- **SCIM 2.0** user/group provisioning
- Just-in-time user provisioning
- Group-to-role mapping

### Multi-tenancy & SaaS administration

- Hierarchical org/business-unit modelling beyond
  platform/tenant/workspace
- Per-tenant resource quotas with hard limits and billing hooks
- Tenant-level data residency controls
- Bulk tenant lifecycle automation (create / suspend / archive)
- Cross-tenant aggregate dashboards for platform admins

### Audit & compliance

- Long-retention, tamper-evident audit log export (S3-compatible
  WORM, signed bundles)
- Compliance evidence packs (SOC 2, ISO 27001, GDPR DSR)
- Detailed access logs for evidence and failed-row data

### Evidence vault

- Customer-managed keys (CMK / BYOK)
- Field-level encryption for failed-row samples
- Approval workflow to unmask evidence (steward + tenant admin
  co-sign)
- Tokenisation of sensitive identifiers

### Customer-side execution agent

- A lightweight agent the customer runs inside their network
- Pulls signed rule packages from the control plane
- Executes against the customer's databases / Spark / warehouse
- Returns only metrics + evidence pointers — no raw data ever
  leaves the customer's network

### Managed cloud

- Hosted CogniDQ with SLAs
- Dedicated tenancy and BYO-cloud options
- Operational support: backups, upgrades, monitoring, on-call

### Premium connectors

- Production-grade Snowflake, Databricks, BigQuery, Redshift,
  Synapse, MS SQL, Oracle connectors with vendor-backed support
- Pushdown optimisations specific to each warehouse
- Streaming/CDC inputs

### AI features

- Natural-language rule builder with curated guardrails
- Lineage-aware rule suggestions
- Anomaly detection on metric time series
- Automatic incident grouping and root-cause hints
- KQI/KPI extraction

### Support

- Defined response/resolution SLAs
- Named technical account manager
- Architecture reviews
- Security & compliance questionnaires answered

---

## What is in this OSS repository today

See [open-source-strategy.md](open-source-strategy.md) for the exact
feature classification (Core / Enterprise / Experimental) and which
feature flags gate the experimental items.

The default Docker Compose stack ships **only the Core tier**.
Experimental features are off by default. Enterprise features are not in
this repository at all.

---

## Interested in the enterprise edition?

The enterprise edition does not yet exist as a shipping product. If you
are evaluating CogniDQ for an organisation that needs the capabilities
listed above, please open a GitHub Discussion or contact the maintainers
through the channels listed in [SUPPORT.md](../SUPPORT.md). Your input
shapes priorities.
