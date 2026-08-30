# Tenant / workspace model

CogniDQ is multi-tenant from the ground up. This page explains the
three-level hierarchy and how isolation is enforced.

For the role catalog, see [rbac.md](rbac.md).

---

## Hierarchy

```text
Platform                ← single instance per deployment
  └─ Tenant             ← organization boundary
        └─ Workspace    ← unit of authoring
              └─ … datasets, rules, executions, issues, incidents
```

### Platform

There is one platform per deployment (one running CogniDQ stack). It
holds:

- the list of tenants
- platform-wide config (default feature flags, encryption-key policy)
- platform admins

You normally never see the word "platform" in the UI; it is the implicit
top of the tree.

### Tenant

A tenant represents an organization. In single-org deployments you may
only ever have one tenant ("Acme Corp"). In hosted / multi-customer
deployments, each customer is a tenant.

A tenant has:

- a name + slug
- tenant admins
- one or more workspaces
- tenant-level audit log

Tenants are isolated: a user in tenant A cannot read tenant B unless
they are also a member of tenant B *and* explicitly switch scope.

### Workspace

A workspace is the unit of authoring. It is intentionally small:

- a team
- a domain (e.g. "finance", "marketing")
- or a project / lifecycle stage (e.g. "data-platform-prod")

A workspace owns:

- connections
- datasets
- rules and their versions
- executions
- issues, incidents, evidence
- workspace members + their roles

## Why three levels (not two, not four)

We chose three because:

- One level (just users → resources) does not work for any organisation
  bigger than a small team.
- Two levels (users → tenants → resources) collapses authoring boundaries
  inside a tenant. A 5 000-person bank wants different DQ rules per
  domain.
- Four levels (users → org → BU → team → resources) was the original
  design; we collapsed BU into "tenant" and team into "workspace"
  because most users found the extra level confusing without buying
  much.

If you need richer hierarchy (e.g. business units between tenant and
workspace), see [enterprise-edition.md](enterprise-edition.md).

## Membership and scope

A user can belong to:

- multiple tenants
- multiple workspaces inside a tenant
- with one role per scope

Concretely, the membership model is:

```text
TenantMembership(user_id, tenant_id, role)
WorkspaceMembership(user_id, workspace_id, role)
```

A user authenticates once. Their JWT carries the active tenant and
workspace. Switching scope mints a new JWT (the frontend handles this
via the scope picker).

Backend code never trusts a `tenant_id` or `workspace_id` from the
request body for *authorization*; it derives them from the JWT.

## Isolation guarantees

| Boundary | Guarantee |
|---|---|
| Cross-tenant | Strong: every workspace-owned table includes `tenant_id` or is reached via `workspace_id → tenant_id`, and queries filter on the active tenant. |
| Cross-workspace, same tenant | Strong: every workspace-owned table includes `workspace_id` and queries filter on it. There is no "list all rules" code path that bypasses this. |
| Evidence in object storage | Strong: keys are prefixed by `workspace_id`. Bucket policy in production should also enforce per-prefix access. |
| Source databases | Out of scope: source DB credentials are in the connection record, scoped to a workspace; the source DB itself is not part of CogniDQ's isolation. Use a least-privilege read-only DB account per workspace. |

In production, additionally:

- run tenant-aware rate limits at the gateway (one tenant cannot DoS
  another),
- segregate Spark queues per tenant if tenants share a cluster.

See [production-hardening.md](production-hardening.md).

## Onboarding flow

Typical setup for a new organisation:

1. Platform admin creates a tenant.
2. Platform admin invites the first tenant admin (email + a generated
   invite link).
3. Tenant admin signs in and creates one or more workspaces.
4. Tenant admin invites workspace administrators.
5. Workspace admins invite engineers, stewards, analysts.

The seed loader does all of this for you for the demo tenant.

## Deletion

- Deleting a workspace soft-archives it: rules become read-only,
  scheduled runs stop. Hard-deletion is a separate, audited operation.
- Deleting a tenant soft-archives all its workspaces.
- Hard-deleting a tenant is a platform-admin operation that prompts for
  the tenant slug as a confirmation.

Hard-deletion is intentionally a two-step path; we do not want
"oops, I dropped the prod tenant" to be one click.

## Glossary

| Term | Meaning |
|---|---|
| **Principal** | The "who" in an authorization decision: a user + their currently active tenant + workspace. |
| **Scope** | The tenant + workspace pair currently active. |
| **Resource** | Anything protected by RBAC: connection, dataset, rule, execution, issue, incident, audit event. |
| **Owner** | The user recorded as the creator of a resource. Ownership does not by itself confer extra rights; roles do. |
