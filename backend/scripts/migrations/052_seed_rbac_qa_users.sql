-- Migration: 052_seed_rbac_qa_users.sql
-- Purpose:   Seed a dedicated RBAC-QA tenant + workspace + one user per role
--            for end-to-end role testing without relying on dev-mode role
--            impersonation (which has been removed).
--
-- Idempotent: every INSERT uses ON CONFLICT DO NOTHING.
--
-- Constants (also used by qa_seed_rbac_users.py):
--   tenant_id   = 33333333-3333-4333-8333-333333333333
--   workspace_id = 44444444-4444-4444-8444-444444444444
--
-- Password hashing scheme (matches User.set_password):
--   bcrypt(sha256_hex(plaintext), rounds=12)
-- Hashes below are pre-computed for the passwords listed in
-- documentation/TEST_CREDENTIALS.md. If a password is rotated, update both
-- this file and the credentials reference.
--
-- NOTE on workspaces.workspace_name_lower: it is GENERATED ALWAYS (migration
-- 041) — never include it in an INSERT column list.

BEGIN;

-- crypt() / gen_salt() / digest() come from pgcrypto. Idempotent.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─────────────────────────────────────────────────────────────────────────
-- 1. Tenant + Workspace
-- ─────────────────────────────────────────────────────────────────────────

INSERT INTO control.tenants (
    tenant_id, tenant_name, tenant_slug, status,
    region, plan, created_at, updated_at,
    created_by, updated_by, version
)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    'RBAC QA',
    'rbac-qa',
    'active',
    'eu-west',
    'enterprise',
    NOW(), NOW(),
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    0
)
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO control.workspaces (
    workspace_id, tenant_id, workspace_name,
    workspace_slug, default_timezone, status,
    created_at, updated_at, created_by, updated_by, version
)
VALUES (
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    'RBAC QA Workspace',
    'rbac-qa-workspace',
    'UTC',
    'active',
    NOW(), NOW(),
    '63cae557-c3bc-4442-8592-58205e772aa6',
    '63cae557-c3bc-4442-8592-58205e772aa6',
    0
)
ON CONFLICT (workspace_id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────
-- 2. Test users — one per role
--    (id, email, full_name, password_hash, platform_role, tenant_id)
-- ─────────────────────────────────────────────────────────────────────────
--
-- Pre-computed bcrypt hashes (rounds=12) of sha256_hex(<password>).
-- Verified by the qa_seed_rbac_users.py companion script which uses the
-- same hashing approach and is the canonical re-seed tool for live DBs.
-- The migration runner has no incremental tracking; this file is for fresh
-- DB bootstraps. For an existing DB, run the Python script instead.

-- platform_admin (no tenant)
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000001-0000-4000-8000-000000000001'::uuid,
       'qa.platformadmin@dq.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Platform Admin',
       'platform_admin', NULL, 'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.platformadmin@dq.test');

-- platform_viewer (no tenant)
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000002-0000-4000-8000-000000000002'::uuid,
       'qa.platformviewer@dq.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Platform Viewer',
       'platform_viewer', NULL, 'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.platformviewer@dq.test');

-- tenant_admin (RBAC QA tenant)
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000003-0000-4000-8000-000000000003'::uuid,
       'qa.tenantadmin@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Tenant Admin',
       'tenant_admin',
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.tenantadmin@rbac-qa.test');

-- workspace_administrator
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000004-0000-4000-8000-000000000004'::uuid,
       'qa.wsadmin@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Workspace Administrator',
       NULL,
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.wsadmin@rbac-qa.test');

-- data_engineer
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000005-0000-4000-8000-000000000005'::uuid,
       'qa.dataengineer@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Data Engineer',
       NULL,
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.dataengineer@rbac-qa.test');

-- data_steward
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000006-0000-4000-8000-000000000006'::uuid,
       'qa.datasteward@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Data Steward',
       NULL,
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.datasteward@rbac-qa.test');

-- business_analyst
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000007-0000-4000-8000-000000000007'::uuid,
       'qa.analyst@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Business Analyst',
       NULL,
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.analyst@rbac-qa.test');

-- governance_viewer
INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '50000008-0000-4000-8000-000000000008'::uuid,
       'qa.viewer@rbac-qa.test',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'QA Governance Viewer',
       NULL,
       '33333333-3333-4333-8333-333333333333',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'qa.viewer@rbac-qa.test');

-- ─────────────────────────────────────────────────────────────────────────
-- 3. Workspace role assignments — five canonical roles in the RBAC QA WS
-- ─────────────────────────────────────────────────────────────────────────

INSERT INTO control.workspace_role_assignments (workspace_id, user_id, role_name, granted_by, granted_at)
VALUES
  ('44444444-4444-4444-8444-444444444444', '50000004-0000-4000-8000-000000000004', 'workspace_administrator', '63cae557-c3bc-4442-8592-58205e772aa6', NOW()),
  ('44444444-4444-4444-8444-444444444444', '50000005-0000-4000-8000-000000000005', 'data_engineer',           '63cae557-c3bc-4442-8592-58205e772aa6', NOW()),
  ('44444444-4444-4444-8444-444444444444', '50000006-0000-4000-8000-000000000006', 'data_steward',            '63cae557-c3bc-4442-8592-58205e772aa6', NOW()),
  ('44444444-4444-4444-8444-444444444444', '50000007-0000-4000-8000-000000000007', 'business_analyst',        '63cae557-c3bc-4442-8592-58205e772aa6', NOW()),
  ('44444444-4444-4444-8444-444444444444', '50000008-0000-4000-8000-000000000008', 'governance_viewer',       '63cae557-c3bc-4442-8592-58205e772aa6', NOW())
ON CONFLICT (workspace_id, user_id) DO NOTHING;

COMMIT;
