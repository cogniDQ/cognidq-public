-- 027b_seed_default_workspace.sql
-- ----------------------------------------------------------------------
-- Seed the default tenant and workspace referenced by migration 028's
-- ``00000000-0000-0000-0000-000000000020`` workspace_id mapping. Required
-- so that the FK constraints added at the end of 028 succeed on a fresh DB.
--
-- Idempotent: ``ON CONFLICT DO NOTHING`` on the primary keys.
-- ----------------------------------------------------------------------

-- Default tenant (region/plan must satisfy the enum values created by 006).
INSERT INTO control.tenants (
    tenant_id, tenant_name, tenant_slug, status,
    region, plan, created_at, updated_at,
    created_by, updated_by, version
)
VALUES (
    '8062ed84-5660-4470-833c-f748ed0a7481',
    'Default Tenant',
    'default-tenant',
    'active',
    'eu-west',
    'enterprise',
    NOW(), NOW(),
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    0
)
ON CONFLICT (tenant_id) DO NOTHING;

-- Default workspace bound to that tenant. The workspace_id matches the
-- target id used by 028's UPDATE statements.
INSERT INTO control.workspaces (
    workspace_id, tenant_id, workspace_name, workspace_name_lower,
    workspace_slug, default_timezone, status,
    created_at, updated_at, created_by, updated_by, version
)
VALUES (
    '00000000-0000-0000-0000-000000000020',
    '8062ed84-5660-4470-833c-f748ed0a7481',
    'Default Workspace',
    'default workspace',
    'default-workspace',
    'UTC',
    'active',
    NOW(), NOW(),
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    0
)
ON CONFLICT (workspace_id) DO NOTHING;
