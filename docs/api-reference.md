# API reference

CogniDQ exposes a versioned REST API at `/api/v1`. The OpenAPI document
is the canonical reference and is served by the backend itself.

| URL | What |
|---|---|
| `http://localhost:8000/api/v1/openapi.json` | OpenAPI 3.1 document |
| `http://localhost:8000/api/docs` | Swagger UI |
| `http://localhost:8000/api/redoc` | ReDoc |

This page summarises the structure and the conventions; it is **not** a
generated reference. Use the OpenAPI document for the field-level
truth.

---

## Conventions

- All endpoints are under `/api/v1`.
- Authentication is `Authorization: Bearer <jwt>` for user-issued
  tokens and `Authorization: Bearer <api-token>` for personal API
  tokens — same header, different token types.
- Request and response bodies are JSON unless explicitly noted (CSV
  exports, file uploads).
- Timestamps are ISO 8601 in UTC.
- Pagination uses `?limit=N&offset=M` and the response envelope:
  ```json
  { "items": [...], "total": 1234, "limit": 50, "offset": 0 }
  ```
- Error responses follow:
  ```json
  { "detail": [{"loc": ["body","email"], "msg": "field required", "type": "value_error.missing"}] }
  ```
  for validation errors, and:
  ```json
  { "detail": "Insufficient permissions" }
  ```
  for authorization errors.

## Auth

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/login` | exchange email + password for tokens |
| `POST` | `/auth/refresh` | rotate access token |
| `POST` | `/auth/logout` | invalidate refresh token |
| `POST` | `/auth/switch-scope` | mint a JWT for a different workspace |
| `GET` | `/auth/me` | current user, active scope, roles |
| `GET` | `/auth/api-tokens` | list personal API tokens |
| `POST` | `/auth/api-tokens` | create a personal API token |
| `DELETE` | `/auth/api-tokens/{id}` | revoke a token |

## Tenants & workspaces

| Method | Path | Purpose | Required role |
|---|---|---|---|
| `GET` | `/tenants` | list tenants user belongs to | any |
| `POST` | `/tenants` | create a tenant | `platform_admin` |
| `GET` | `/tenants/{id}` | tenant detail | tenant member |
| `GET` | `/workspaces` | list workspaces in active scope | any |
| `POST` | `/workspaces` | create a workspace | `tenant_admin` |
| `GET` | `/workspaces/{id}` | workspace detail | workspace member |
| `POST` | `/workspaces/{id}/members` | add member | `workspace_administrator` |
| `DELETE` | `/workspaces/{id}/members/{user_id}` | remove member | `workspace_administrator` |

## Connections & datasets

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/connections` | list connections in workspace |
| `POST` | `/connections` | create connection |
| `GET` | `/connections/{id}` | connection detail (no secrets) |
| `PATCH` | `/connections/{id}` | update connection |
| `DELETE` | `/connections/{id}` | archive connection |
| `POST` | `/connections/{id}/test` | test the connection |
| `GET` | `/connections/{id}/schemas` | list schemas |
| `GET` | `/connections/{id}/tables` | list tables (paginated) |
| `GET` | `/datasets` | list datasets in workspace |
| `POST` | `/datasets` | register a dataset |
| `GET` | `/datasets/{id}` | dataset detail incl. fields |
| `PATCH` | `/datasets/{id}` | update dataset metadata |
| `DELETE` | `/datasets/{id}` | archive dataset |
| `POST` | `/datasets/{id}/refresh-schema` | re-infer schema from source |
| `GET` | `/datasets/{id}/preview` | preview rows (bounded) |

## Rules & executions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/rules` | list rules in workspace |
| `POST` | `/rules` | create a rule |
| `GET` | `/rules/{id}` | rule detail (current version) |
| `PATCH` | `/rules/{id}` | update rule (creates a new version) |
| `DELETE` | `/rules/{id}` | archive rule |
| `POST` | `/rules/{id}/run` | run rule on demand |
| `PUT` | `/rules/{id}/schedule` | set schedule |
| `DELETE` | `/rules/{id}/schedule` | clear schedule |
| `GET` | `/rules/{id}/versions` | list versions |
| `GET` | `/executions` | list executions (filterable) |
| `GET` | `/executions/{id}` | execution detail |
| `GET` | `/executions/{id}/evidence` | evidence download |

## Issues & incidents

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/issues` | list issues |
| `POST` | `/issues` | create manual issue |
| `GET` | `/issues/{id}` | issue detail incl. timeline |
| `PATCH` | `/issues/{id}` | update status / severity / assignee |
| `POST` | `/issues/{id}/comments` | add comment |
| `POST` | `/issues/bulk` | bulk update |
| `GET` | `/incidents` | list incidents |
| `POST` | `/incidents` | create incident (optionally with issues) |
| `GET` | `/incidents/{id}` | incident detail incl. timeline |
| `PATCH` | `/incidents/{id}` | update incident |
| `POST` | `/incidents/{id}/issues` | attach issues |
| `DELETE` | `/incidents/{id}/issues/{issue_id}` | detach issue |

## Dashboards / metrics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/dashboards/workspace` | top-level KPIs for the active workspace |
| `GET` | `/dashboards/rules-trend` | pass-rate trend over time |
| `GET` | `/dashboards/issues-trend` | open-issue trend |

These endpoints are stable but the response shapes are likely to evolve
in v0.2; treat as semi-stable.

## Audit & system

| Method | Path | Purpose | Required role |
|---|---|---|---|
| `GET` | `/audit` | read audit events for the active scope | `governance_viewer`, `tenant_admin`, `platform_admin` |
| `GET` | `/system/health` | liveness | none |
| `GET` | `/system/ready` | readiness (DB, Redis, MinIO) | none |
| `GET` | `/system/metrics` | Prometheus metrics | none (lock down via reverse proxy) |
| `GET` | `/system/version` | version + git commit | any |

## Versioning policy

- Breaking changes on the `v1` API: avoided when possible; when
  necessary, a `v2` namespace is added in parallel and `v1` is
  deprecated for at least one minor release.
- Additive changes (new fields, new optional query params): allowed on
  `v1` without a major bump.
- Field removals: never on `v1`.

## Examples

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"steward@example.com","password":"change-me-strong-password"}'
```

```jsonc
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Create a rule

```bash
curl -X POST http://localhost:8000/api/v1/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id": "ds_customers",
    "name": "customers.email is not null",
    "type": "completeness",
    "config": { "column": "email" },
    "threshold": { "operator": "gte", "score": 0.99 },
    "severity": "medium"
  }'
```

### Run a rule

```bash
curl -X POST http://localhost:8000/api/v1/rules/rule_01HXYZ/run \
  -H "Authorization: Bearer $TOKEN"
```

```jsonc
{ "execution_id": "exec_01HXYZ", "status": "pending" }
```

### Read execution

```bash
curl http://localhost:8000/api/v1/executions/exec_01HXYZ \
  -H "Authorization: Bearer $TOKEN"
```

For the full schema, generate a client from the OpenAPI document:

```bash
# Python
pip install openapi-python-client
openapi-python-client generate --url http://localhost:8000/api/v1/openapi.json

# TypeScript
npx openapi-typescript http://localhost:8000/api/v1/openapi.json -o ./api-types.ts
```
