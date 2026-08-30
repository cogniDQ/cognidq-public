-- Migration 003: Domains, Teams, and RBAC
-- Adds hierarchical organization structure (Org → Domain → Team) and role-based access control

-- ============================================================================
-- DOMAINS TABLE
-- ============================================================================
-- Domains allow organizations to group teams by business units, products, or regions
CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    slug VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, slug)
);

CREATE INDEX idx_domains_org ON domains(organization_id);
CREATE INDEX idx_domains_slug ON domains(organization_id, slug);

-- ============================================================================
-- TEAMS TABLE
-- ============================================================================
-- Teams are groups of users within a domain
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    slug VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(domain_id, slug)
);

CREATE INDEX idx_teams_domain ON teams(domain_id);
CREATE INDEX idx_teams_org ON teams(organization_id);
CREATE INDEX idx_teams_slug ON teams(domain_id, slug);

-- ============================================================================
-- TEAM MEMBERS TABLE
-- ============================================================================
-- Junction table for users in teams
CREATE TABLE team_members (
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member', -- team-lead, member
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_team_members_team ON team_members(team_id);

-- ============================================================================
-- RBAC: ROLES TABLE
-- ============================================================================
-- Roles define sets of permissions that can be assigned to users, teams, or domains
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE, -- true for predefined roles (Admin, Editor, Viewer)
    scope VARCHAR(50) DEFAULT 'organization', -- organization, domain, team
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, name)
);

CREATE INDEX idx_roles_org ON roles(organization_id);
CREATE INDEX idx_roles_system ON roles(is_system);

-- ============================================================================
-- RBAC: PERMISSIONS TABLE
-- ============================================================================
-- Permissions define what actions can be performed on resources
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource VARCHAR(100) NOT NULL, -- datasources, glossary, rules, flows, teams, domains, settings
    action VARCHAR(50) NOT NULL, -- read, write, execute, delete, manage
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(resource, action)
);

-- ============================================================================
-- RBAC: ROLE PERMISSIONS TABLE
-- ============================================================================
-- Junction table linking roles to permissions
CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX idx_role_permissions_perm ON role_permissions(permission_id);

-- ============================================================================
-- RBAC: USER ROLE ASSIGNMENTS TABLE
-- ============================================================================
-- Assigns roles to users at different scopes (org, domain, team)
CREATE TABLE user_role_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain_id UUID REFERENCES domains(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id),
    assigned_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, role_id, organization_id, domain_id, team_id)
);

CREATE INDEX idx_user_roles_user ON user_role_assignments(user_id);
CREATE INDEX idx_user_roles_org ON user_role_assignments(organization_id);
CREATE INDEX idx_user_roles_domain ON user_role_assignments(domain_id);
CREATE INDEX idx_user_roles_team ON user_role_assignments(team_id);

-- ============================================================================
-- SEED DEFAULT PERMISSIONS
-- ============================================================================
INSERT INTO permissions (resource, action, description) VALUES
    -- Data Sources
    ('datasources', 'read', 'View data sources'),
    ('datasources', 'write', 'Create and edit data sources'),
    ('datasources', 'delete', 'Delete data sources'),
    ('datasources', 'execute', 'Test connections and query data'),
    
    -- Glossary
    ('glossary', 'read', 'View glossary terms'),
    ('glossary', 'write', 'Create and edit glossary terms'),
    ('glossary', 'delete', 'Delete glossary terms'),
    ('glossary', 'manage', 'Manage glossary mappings'),
    
    -- Rules
    ('rules', 'read', 'View data quality rules'),
    ('rules', 'write', 'Create and edit rules'),
    ('rules', 'execute', 'Execute rules'),
    ('rules', 'delete', 'Delete rules'),
    
    -- Flows
    ('flows', 'read', 'View DQ flows'),
    ('flows', 'write', 'Create and edit flows'),
    ('flows', 'execute', 'Execute flows'),
    ('flows', 'delete', 'Delete flows'),
    
    -- Teams
    ('teams', 'read', 'View teams'),
    ('teams', 'write', 'Create and edit teams'),
    ('teams', 'delete', 'Delete teams'),
    ('teams', 'manage', 'Manage team members'),
    
    -- Domains
    ('domains', 'read', 'View domains'),
    ('domains', 'write', 'Create and edit domains'),
    ('domains', 'delete', 'Delete domains'),
    ('domains', 'manage', 'Manage domain settings'),
    
    -- Organization Settings
    ('settings', 'read', 'View organization settings'),
    ('settings', 'write', 'Edit organization settings'),
    
    -- Members
    ('members', 'read', 'View organization members'),
    ('members', 'write', 'Invite and edit members'),
    ('members', 'delete', 'Remove members'),
    
    -- Roles & Permissions
    ('roles', 'read', 'View roles'),
    ('roles', 'write', 'Create and edit roles'),
    ('roles', 'delete', 'Delete roles'),
    ('roles', 'assign', 'Assign roles to users'),
    
    -- Reports & Dashboards
    ('reports', 'read', 'View reports and dashboards'),
    ('reports', 'write', 'Create and edit reports'),
    ('reports', 'execute', 'Generate and export reports');

-- ============================================================================
-- SEED DEFAULT SYSTEM ROLES
-- ============================================================================
-- We'll create system roles for each organization via backend code, not here
-- But we define the structure:
-- 
-- Organization Admin: Full access to everything
-- Domain Admin: Full access within a domain
-- Team Lead: Manage team members, view/edit team resources
-- Editor: Create and edit resources (sources, rules, flows)
-- Viewer: Read-only access
-- Analyst: View + execute rules/flows

-- ============================================================================
-- UPDATE organization_members TO ADD ROLE REFERENCE
-- ============================================================================
-- Add a role field to organization_members to link to the roles table
ALTER TABLE organization_members 
ADD COLUMN role_id UUID REFERENCES roles(id);

-- Create index for role lookups
CREATE INDEX idx_org_members_role ON organization_members(role_id);

-- Note: Existing 'role' VARCHAR column remains for backward compatibility
-- We'll migrate data in a separate script if needed

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE domains IS 'Business units, products, or regions within an organization';
COMMENT ON TABLE teams IS 'Groups of users within a domain';
COMMENT ON TABLE team_members IS 'Users assigned to teams';
COMMENT ON TABLE roles IS 'Role definitions with associated permissions';
COMMENT ON TABLE permissions IS 'Granular permissions for resources';
COMMENT ON TABLE role_permissions IS 'Permissions assigned to roles';
COMMENT ON TABLE user_role_assignments IS 'Roles assigned to users at org/domain/team level';
