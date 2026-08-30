-- Migration: Add default organization, domain, and team
-- Created: 2026-01-13

-- Create default organization
INSERT INTO organizations (id, name, slug, status, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Default Organization',
    'default-org',
    'active',
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Create default domain
INSERT INTO domains (id, organization_id, name, description, slug, is_active, metadata, created_by, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000002'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Default Domain',
    'Default domain for initial setup',
    'default-domain',
    true,
    '{}',
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Create default team
INSERT INTO teams (id, domain_id, organization_id, name, description, slug, is_active, metadata, created_by, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000003'::uuid,
    '00000000-0000-0000-0000-000000000002'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Default Team',
    'Default team for initial setup',
    'default-team',
    true,
    '{}',
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Add the default admin user to the default organization as owner
INSERT INTO organization_members (organization_id, user_id, role, status, invited_at, joined_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    'owner',
    'active',
    NOW(),
    NOW()
) ON CONFLICT (organization_id, user_id) DO UPDATE 
SET role = 'owner', status = 'active';

-- Add the default admin user to the default team as owner
INSERT INTO team_members (team_id, user_id, role, joined_at)
VALUES (
    '00000000-0000-0000-0000-000000000003'::uuid,
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    'owner',
    NOW()
) ON CONFLICT (team_id, user_id) DO NOTHING;

-- Create a default Admin role for the organization
INSERT INTO roles (id, organization_id, name, description, is_system, scope, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000010'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Admin',
    'Administrator with full access',
    false,
    'organization',
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Assign all permissions to the Admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT 
    '00000000-0000-0000-0000-000000000010'::uuid,
    id
FROM permissions
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign Admin role to Ahmed at organization level
INSERT INTO user_role_assignments (
    user_id, 
    role_id, 
    organization_id, 
    domain_id, 
    team_id, 
    assigned_by, 
    assigned_at
)
VALUES (
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    '00000000-0000-0000-0000-000000000010'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    NULL,
    NULL,
    '63cae557-c3bc-4442-8592-58205e772aa6'::uuid,
    NOW()
) ON CONFLICT DO NOTHING;

-- Add comments
COMMENT ON TABLE organizations IS 'Organizations table with default organization';
COMMENT ON TABLE domains IS 'Domains table with default domain';
COMMENT ON TABLE teams IS 'Teams table with default team';
