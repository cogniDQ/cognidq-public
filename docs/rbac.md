# RBAC: roles and permissions

CogniDQ uses **role-based access control with multi-tenant scoping**.
Permissions are checked at every API endpoint via FastAPI dependencies;
the frontend additionally hides UI elements the user cannot use, but
the backend is always the source of truth.

For the tenant / workspace data model, see
[tenant-workspace-model.md](tenant-workspace-model.md).

---

## Built-in roles

There are seven built-in roles, scoped at three levels:

| Scope | Role | Purpose |
|---|---|---|
| Platform | `platform_admin` | Manages tenants, global settings, system-wide config. |
| Tenant | `tenant_admin` | Manages workspaces and membership inside one tenant. |
| Workspace | `workspace_administrator` | Owns a workspace; adds members; configures workspace settings. |
| Workspace | `data_engineer` | Manages connections and datasets; can author rules. |
| Workspace | `data_steward` | Authors rules; triages issues; runs executions. |
| Workspace | `business_analyst` | Reads dashboards and rule results; cannot edit rules. |
| Workspace | `governance_viewer` | Read-only across the workspace; intended for compliance/audit. |

## What each role can do

### `platform_admin`

- Create / suspend / delete **tenants**.
- Set global config (encryption keys policy, default feature flags).
- Read all audit logs.
- **Cannot** read evidence inside a tenant by default; that is governed
  by tenant policy. (Some deployments grant evidence read; this is a
  policy decision, not a code grant.)

### `tenant_admin`

- Create / archive **workspaces** in their tenant.
- Invite users to the tenant.
- Assign workspace roles to tenant members.
- Read tenant-level audit logs.
- **Cannot** modify other tenants.

### `workspace_administrator`

- Manage workspace settings.
- Add / remove workspace members and assign workspace roles.
- All capabilities of `data_engineer` + `data_steward`.

### `data_engineer`

- Create / edit / delete **connections** in the workspace.
- Create / edit / archive **datasets**.
- Create / edit / delete **rules** (any version).
- Run executions on demand and configure schedules.
- Read all rule executions, issues, incidents.

### `data_steward`

- Create / edit **rules** they author or that the workspace admin
  delegated.
- Run executions on demand.
- Triage **issues**: assign, comment, change status, group into
  incidents.
- Read connections and datasets but **cannot** edit them.
- Read evidence.

### `business_analyst`

- Read rules, executions, dashboards, issues, incidents.
- Comment on issues.
- **Cannot** edit rules, datasets, or connections.
- Cannot run executions on demand.

### `governance_viewer`

- Read everything in the workspace including audit events.
- Read evidence (subject to sensitivity-tag masking).
- Cannot create, edit, run, or comment.

---

## Permission matrix (selected)

Rows are operations, columns are roles. ✓ = allowed, ✗ = denied,
**ws-admin** = `workspace_administrator`, **eng** = `data_engineer`,
**stew** = `data_steward`, **ba** = `business_analyst`,
**gov** = `governance_viewer`.

| Operation | platform_admin | tenant_admin | ws-admin | eng | stew | ba | gov |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| List tenants | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Create tenant | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Create workspace in tenant | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Invite user to tenant | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Assign workspace role | ✓ | ✓ | ✓ (own ws) | ✗ | ✗ | ✗ | ✗ |
| Create / edit connection | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Create / edit dataset | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Create / edit rule | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Run rule on demand | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Read execution / dashboard | ✓ | ✓ (read) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Triage / close issue | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ |
| Comment on issue | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Read evidence | ✓ (policy) | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ (masked) |
| Read audit events | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |

This matrix is the canonical reference; the backend implements it in
`backend/app/core/permissions.py` (or equivalent module).

## Where permissions are enforced

- **Backend HTTP layer:** every endpoint declares the role(s) it
  requires via a FastAPI dependency.
- **Service layer:** services receive a "principal" (user + active
  scope) and re-check authorization for cross-aggregate operations.
- **Workspace scoping:** every query that returns workspace-owned data
  filters by the active workspace id; there is no global "list all
  rules" path that bypasses this.
- **Frontend:** uses the user's profile (`/api/v1/auth/me`) to hide
  buttons, but never to grant.

## Switching scope

A user may belong to multiple tenants and multiple workspaces inside a
tenant. The active scope is part of the JWT claims and is changed via
`POST /api/v1/auth/switch-scope`. The new JWT replaces the old one.
Active scope is not implicit; the frontend renders a tenant + workspace
picker.

## Custom roles

Custom (workspace-defined) roles are **not** part of the OSS edition.
The role table is hardcoded; the user-role assignment is dynamic. If
custom roles are important to you, see
[enterprise-edition.md](enterprise-edition.md) or open a discussion.

## Audit trail

Every privilege-relevant operation writes an audit event:

- who (user id + scope at time of action)
- what (operation name, e.g. `rule.update`)
- on what (resource type + id)
- result (success / denied / errored)
- when (UTC timestamp)
- request id

Audit events are append-only at the application level. The DB layer is
not append-only by default; production deployments should harden this
at the storage layer (see [production-hardening.md](production-hardening.md)).

## Service accounts

There is no first-class "service account" object yet. The pragmatic
substitute is a regular user with a long-lived API token (created via
the **Account → tokens** screen). API tokens inherit the user's roles.
Proper service accounts are tracked on the [roadmap](../ROADMAP.md).
