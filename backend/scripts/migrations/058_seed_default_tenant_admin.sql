-- Migration: 058_seed_default_tenant_admin.sql
-- Purpose:   The "Default Tenant" / "Default Workspace" seeded by 027b had
--            no tenant_admin and no workspace members at all — only
--            platform_admin's old unconditional cross-tenant bypass could
--            ever reach it. Now that platform_admin requires a tenant-admin-
--            issued support access grant (see control.support_access_grants),
--            that workspace became permanently unreachable with no one able
--            to grant access into it. Seed a real tenant_admin so it's
--            reachable the same way every other client tenant now works.
--
-- Idempotent: WHERE NOT EXISTS guard, matches the pattern in
-- 052_seed_rbac_qa_users.sql.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
SELECT '70000000-0000-4000-8000-000000000001'::uuid,
       'tenant-admin@example.com',
       crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
       'Default Tenant Admin',
       'tenant_admin',
       '8062ed84-5660-4470-833c-f748ed0a7481',
       'ACTIVE', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'tenant-admin@example.com');

COMMIT;
