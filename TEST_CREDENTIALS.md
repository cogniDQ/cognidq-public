# Test Credentials Reference

> **Scope:** Local `docker-compose` stack only. NOT for production.

---

## App User Accounts

Login: `POST http://localhost:8000/api/v1/auth/login`  
Body: `{ "email": "...", "password": "..." }`

Dev-mode role switching (`X-Dev-Active-Role` header / RoleSwitcher dropdown)
has been removed. To exercise a role, log in as the corresponding test
account below.

### RBAC QA accounts (tenant `rbac-qa`, workspace `rbac-qa-workspace`)

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

Key IDs:
- Tenant: `33333333-3333-4333-8333-333333333333`
- Workspace: `44444444-4444-4444-8444-444444444444`

Seeded by migration `052_seed_rbac_qa_users.sql` on fresh DBs. To (re)seed an
existing DB, run `python qa_seed_rbac_users.py` from the project root.

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

| Object | ID |
|---|---|
| Default Tenant | `8062ed84-5660-4470-833c-f748ed0a7481` |
| Archived E2E Tenant | `11111111-1111-4111-8111-111111111111` |
| Default Workspace | `00000000-0000-0000-0000-000000000020` |
| E2E Workspace | `22222222-2222-4222-8222-222222222222` |
