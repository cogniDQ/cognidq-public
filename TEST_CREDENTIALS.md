# Test Credentials Reference

> **Scope:** Local `docker-compose` stack only. NOT for production.

---

## App User Accounts

Login: `POST http://localhost:8000/api/v1/auth/login`  
Body: `{ "email": "...", "password": "..." }`

Dev-mode role switching (`X-Dev-Active-Role` header / RoleSwitcher dropdown)
has been removed. To exercise a role, log in as the corresponding test
account below.

### RBAC QA accounts — also the Demo Workspace (tenant `rbac-qa`, workspace `demo-workspace`)

This is the **only** workspace a fresh install seeds. It doubles as the
per-role RBAC test fixture and the pre-loaded product demo: `make seed`
(`scripts/seed_demo_data.py`) populates it with a live connection,
datasets, glossary terms, DQ rules, a flow, and one real flow execution
(see [Key Seed Data IDs](#key-seed-data-ids)) — the demo content any new
client connecting to it will already see.

| Role | Email | Password | platform_role | Workspace role |
|---|---|---|---|---|
| Platform Admin | `qa.platformadmin@dq.test` | `change-me-strong-password` | `platform_admin` | — |
| Platform Viewer | `qa.platformviewer@dq.test` | `change-me-strong-password` | `platform_viewer` | — |
| Tenant Admin | `qa.tenantadmin@rbac-qa.test` | `change-me-strong-password` | `tenant_admin` | — |
| Workspace Administrator | `qa.wsadmin@rbac-qa.test` | `change-me-strong-password` | *(null)* | `workspace_administrator` |
| Data Engineer | `qa.dataengineer@rbac-qa.test` | `change-me-strong-password` | *(null)* | `data_engineer` |
| Data Steward | `qa.datasteward@rbac-qa.test` | `change-me-strong-password` | *(null)* | `data_steward` |
| Business Analyst | `qa.analyst@rbac-qa.test` | `change-me-strong-password` | *(null)* | `business_analyst` |
| Governance Viewer | `qa.viewer@rbac-qa.test` | `change-me-strong-password` | *(null)* | `governance_viewer` |

> `qa.platformadmin@dq.test` does **not** see this workspace's content by
> default — platform admins need a tenant-admin-issued support access
> grant (requested from `qa.tenantadmin@rbac-qa.test`). Log in as the
> tenant admin or data steward above to browse the demo content directly.

Key IDs:
- Tenant: `33333333-3333-4333-8333-333333333333`
- Workspace: `44444444-4444-4444-8444-444444444444`

Tenant + users seeded by migration `052_seed_rbac_qa_users.sql`; the
workspace is renamed to "Demo Workspace" by
`0005_consolidate_into_rbac_qa.py` on fresh DBs. To (re)seed users on
an existing DB, run `python qa_seed_rbac_users.py` from the project root.
To (re)seed the demo content, run `python scripts/seed_demo_data.py` (or
`make seed`).

### Legacy / onboarding accounts (existing tenant `acme-qa`)

| Role | Email | Password | platform_role |
|---|---|---|---|
| Owner Platform Admin | `admin@example.com` | `change-me-strong-password` | `platform_admin` |
| Customer Owner / Tenant Admin | `qa.owner@acme-qa.test` | `change-me-strong-password` | *(null)* |
| Cross-tenant Outsider | `qa.outsider@other-qa.test` | `change-me-strong-password` | *(null)* |

---

## App Endpoints

| Service | URL |
|---|---|
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/docs |
| OpenAPI JSON | http://localhost:8000/api/openapi.json |
| Frontend | http://localhost:5173 |

---

## Databases (Data Sources)

| DB | Host | Port | Database | Username | Password |
|---|---|---|---|---|---|
| PostgreSQL (app DB) | localhost | 5436 | `dataquality_db` | `postgres` | `postgres` |
| PostgreSQL (test DB) | localhost | 5435 | `dq_test` | `testuser` | `testpassword` |
| MySQL (test) | localhost | 3307 | `dq_test` | `testuser` | `testpassword` |
| MySQL (test root) | localhost | 3307 | `dq_test` | `root` | `rootpassword` |
| MSSQL (test) | localhost | 1434 | — | `sa` | `Test@1234` |
| Oracle XE (test) | localhost | 1522 | service: `XEPDB1` | `system` | `testpassword` |
| Oracle XE (test user) | localhost | 1522 | service: `XEPDB1` | `testuser` | `testpassword` |

---

## Object Storage (MinIO)

| | Value |
|---|---|
| API endpoint | http://localhost:9000 |
| Console | http://localhost:9001 |
| Access key | `minioadmin` |
| Secret key | `minioadmin123` |
| Bucket | `dq-data-assets` |

---

## Monitoring & Infrastructure

| Service | URL | Username | Password |
|---|---|---|---|
| Grafana | http://localhost:3000 | `admin` | `admin` |
| Prometheus | http://localhost:9090 | — | *(none)* |
| Spark Master UI | http://localhost:8080 | — | *(none)* |
| Spark History | http://localhost:18080 | — | *(none)* |
| Redis | localhost:6379 | — | *(none)* |

Spark submit URL: `spark://localhost:7077`

---

## Key Seed Data IDs

A fresh install has exactly one workspace — the RBAC QA / Demo Workspace
above. These are its seeded IDs plus the demo content `make seed` adds.

| Object | ID |
|---|---|
| RBAC QA Tenant | `33333333-3333-4333-8333-333333333333` |
| Demo Workspace (= RBAC QA Workspace) | `44444444-4444-4444-8444-444444444444` |
| Archived E2E Tenant | `11111111-1111-4111-8111-111111111111` |
| E2E Workspace | `22222222-2222-4222-8222-222222222222` |
