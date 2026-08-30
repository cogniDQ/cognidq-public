INSERT INTO control.tenants (
    tenant_id, tenant_name, tenant_slug, status, region, plan,
    created_by, updated_by, version, created_at, updated_at
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'E2E Enterprise Tenant',
    'e2e-enterprise-tenant',
    'active',
    'eu-west',
    'starter',
    '33333333-3333-4333-8333-333333333333',
    '33333333-3333-4333-8333-333333333333',
    0,
    NOW(),
    NOW()
)
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO control.workspaces (
    workspace_id, tenant_id, workspace_name, workspace_name_lower,
    workspace_slug, description, default_timezone, status, status_reason,
    created_at, updated_at, created_by, updated_by, version
)
VALUES (
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111',
    'E2E Enterprise Workspace',
    'e2e enterprise workspace',
    'e2e-enterprise-workspace',
    'Workspace for real glossary/rule-builder E2E validation',
    'UTC',
    'active',
    NULL,
    NOW(),
    NOW(),
    '33333333-3333-4333-8333-333333333333',
    '33333333-3333-4333-8333-333333333333',
    0
)
ON CONFLICT (workspace_id) DO NOTHING;

INSERT INTO users (
    id, email, full_name, status, email_verified, tenant_id, created_at, updated_at
)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    'e2e.user@enterprise.test',
    'E2E Enterprise User',
    'active',
    TRUE,
    '11111111-1111-4111-8111-111111111111',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO control.workspace_role_assignments (
    id, workspace_id, user_id, role_name, granted_by, granted_at
)
VALUES (
    '77777777-7777-4777-8777-777777777777',
    '22222222-2222-4222-8222-222222222222',
    '33333333-3333-4333-8333-333333333333',
    'workspace_administrator',
    '33333333-3333-4333-8333-333333333333',
    NOW()
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO control.data_sources (
    data_source_id, workspace_id, tenant_id,
    source_name, source_type, connection_mode, environment,
    status, last_test_status,
    created_at, updated_at, created_by, updated_by
)
VALUES (
    '44444444-4444-4444-8444-444444444444',
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111',
    'DQ Test PostgreSQL Enterprise Source',
    'postgresql',
    'direct',
    'staging',
    'active',
    'untested',
    NOW(),
    NOW(),
    '33333333-3333-4333-8333-333333333333',
    '33333333-3333-4333-8333-333333333333'
)
ON CONFLICT (data_source_id) DO NOTHING;
