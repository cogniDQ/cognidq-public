BEGIN;

-- ── ORGANIZATION ──────────────────────────────────────────────────────────────
INSERT INTO organizations (id, name, slug, status, settings, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Organization', 'default-org', 'active', '{}', now(), now());

-- ── ADMIN USER (platform_admin = highest privileges) ─────────────────────────
-- Default password: change-me-strong-password (rotate immediately after first login).
INSERT INTO users (id, email, password_hash, full_name, email_verified, status, created_at, updated_at, platform_role)
VALUES (
  '63cae557-c3bc-4442-8592-58205e772aa6',
  'admin@example.com',
  '$2b$12$TBZmiPRdgZvv8b0UCsodjudf.6Ssc0JFZMV.YLXxE83zTaPTkCj9G',
  'CogniDQ Admin',
  true,
  'ACTIVE',
  now(),
  now(),
  'platform_admin'
);

-- ── DEFAULT DOMAIN ────────────────────────────────────────────────────────────
INSERT INTO domains (id, organization_id, name, description, slug, is_active, metadata, created_by, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'Default Domain', 'Default domain for initial setup', 'default-domain',
  true, '{}', '63cae557-c3bc-4442-8592-58205e772aa6', now(), now()
);

-- ── DEFAULT TEAM ──────────────────────────────────────────────────────────────
INSERT INTO teams (id, domain_id, organization_id, name, description, slug, is_active, metadata, created_by, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'Default Team', 'Default team for initial setup', 'default-team',
  true, '{}', '63cae557-c3bc-4442-8592-58205e772aa6', now(), now()
);

-- ── ORGANIZATION MEMBER (owner) ───────────────────────────────────────────────
INSERT INTO organization_members (organization_id, user_id, role, status, invited_at, joined_at)
VALUES ('00000000-0000-0000-0000-000000000001', '63cae557-c3bc-4442-8592-58205e772aa6', 'owner', 'active', now(), now());

-- ── TEAM MEMBER (owner) ───────────────────────────────────────────────────────
INSERT INTO team_members (team_id, user_id, role, joined_at)
VALUES ('00000000-0000-0000-0000-000000000003', '63cae557-c3bc-4442-8592-58205e772aa6', 'owner', now());

-- ── PERMISSIONS (all) ────────────────────────────────────────────────────────
INSERT INTO permissions (resource, action, description) VALUES
  ('datasources','read','View data sources'),
  ('datasources','write','Create and edit data sources'),
  ('datasources','delete','Delete data sources'),
  ('datasources','execute','Test connections and query data'),
  ('glossary','read','View glossary terms'),
  ('glossary','write','Create and edit glossary terms'),
  ('glossary','delete','Delete glossary terms'),
  ('glossary','manage','Manage glossary mappings'),
  ('rules','read','View data quality rules'),
  ('rules','write','Create and edit rules'),
  ('rules','execute','Execute rules'),
  ('rules','delete','Delete rules'),
  ('flows','read','View DQ flows'),
  ('flows','write','Create and edit flows'),
  ('flows','execute','Execute flows'),
  ('flows','delete','Delete flows'),
  ('teams','read','View teams'),
  ('teams','write','Create and edit teams'),
  ('teams','delete','Delete teams'),
  ('teams','manage','Manage team members'),
  ('domains','read','View domains'),
  ('domains','write','Create and edit domains'),
  ('domains','delete','Delete domains'),
  ('domains','manage','Manage domain settings'),
  ('settings','read','View organization settings'),
  ('settings','write','Edit organization settings'),
  ('members','read','View organization members'),
  ('members','write','Invite and edit members'),
  ('members','delete','Remove members'),
  ('roles','read','View roles'),
  ('roles','write','Create and edit roles'),
  ('roles','delete','Delete roles'),
  ('roles','assign','Assign roles to users'),
  ('reports','read','View reports and dashboards'),
  ('reports','write','Create and edit reports'),
  ('reports','execute','Generate and export reports');

-- ── ORGANIZATION & WORKSPACE ROLES ───────────────────────────────────────────
INSERT INTO roles (id, organization_id, name, description, is_system, scope, metadata, created_at, updated_at) VALUES
  ('00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000001','Admin','Administrator with full access',true,'organization','{}',now(),now()),
  ('00000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000001','workspace_administrator','Full workspace access; can assign/revoke roles',true,'workspace','{}',now(),now()),
  ('00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000001','data_engineer','Create/modify/delete data sources, datasets, rules, executions',true,'workspace','{}',now(),now()),
  ('00000000-0000-0000-0000-000000000013','00000000-0000-0000-0000-000000000001','data_steward','Edit datasets & rules; write to issues/incidents',true,'workspace','{}',now(),now()),
  ('00000000-0000-0000-0000-000000000014','00000000-0000-0000-0000-000000000001','business_analyst','Read-only: datasets, rules, executions, issues, incidents, reports',true,'workspace','{}',now(),now()),
  ('00000000-0000-0000-0000-000000000015','00000000-0000-0000-0000-000000000001','governance_viewer','Read-only access to all resources',true,'workspace','{}',now(),now());

-- ── ASSIGN ALL PERMISSIONS TO ADMIN ROLE ─────────────────────────────────────
INSERT INTO role_permissions (role_id, permission_id)
SELECT '00000000-0000-0000-0000-000000000010', id FROM permissions;

-- ── ASSIGN ADMIN ROLE TO USER ─────────────────────────────────────────────────
INSERT INTO user_role_assignments (user_id, role_id, organization_id, assigned_by, assigned_at)
VALUES (
  '63cae557-c3bc-4442-8592-58205e772aa6',
  '00000000-0000-0000-0000-000000000010',
  '00000000-0000-0000-0000-000000000001',
  '63cae557-c3bc-4442-8592-58205e772aa6',
  now()
);

COMMIT;

SELECT 'Users: '       || COUNT(*) FROM users;
SELECT 'Roles: '       || COUNT(*) FROM roles;
SELECT 'Permissions: ' || COUNT(*) FROM permissions;
SELECT 'Role-Perms: '  || COUNT(*) FROM role_permissions;
SELECT 'Org members: ' || COUNT(*) FROM organization_members;
