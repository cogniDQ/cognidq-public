BEGIN;

-- ── CREATE TENANT ─────────────────────────────────────────────────────────────
INSERT INTO control.tenants (
    tenant_id, tenant_name, tenant_slug, status, region, plan,
    created_by, updated_by, created_at, updated_at
) VALUES (
    '8062ed84-5660-4470-833c-f748ed0a7481',
    'Default Tenant',
    'default-tenant',
    'active',
    'eu-west',
    'enterprise',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    now(), now()
);

-- ── ASSIGN TENANT TO USER ─────────────────────────────────────────────────────
UPDATE public.users
SET tenant_id = '8062ed84-5660-4470-833c-f748ed0a7481'
WHERE id = '63cae557-c3bc-4442-8592-58205e772aa6';

-- ── CREATE DEFAULT WORKSPACE ──────────────────────────────────────────────────
INSERT INTO control.workspaces (
    workspace_id, tenant_id, workspace_name, workspace_name_lower,
    workspace_slug, status, created_by, updated_by, created_at, updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000020',
    '8062ed84-5660-4470-833c-f748ed0a7481',
    'Default Workspace',
    'default workspace',
    'default-workspace',
    'active',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    now(), now()
);

-- ── ASSIGN USER AS workspace_administrator IN THE WORKSPACE ───────────────────
INSERT INTO control.workspace_role_assignments (
    workspace_id, user_id, role_name, granted_by, granted_at
) VALUES (
    '00000000-0000-0000-0000-000000000020',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    'workspace_administrator',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    now()
);

COMMIT;

-- Verify
SELECT 'Tenant: ' || tenant_name || ' (' || status || ')' FROM control.tenants;
SELECT 'User tenant_id set: ' || tenant_id FROM public.users WHERE id = '63cae557-c3bc-4442-8592-58205e772aa6';
SELECT 'Workspace: ' || workspace_name || ' (' || status || ')' FROM control.workspaces;
SELECT 'Workspace role: ' || role_name FROM control.workspace_role_assignments;
