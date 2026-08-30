-- Migration: 050_workspace_custom_roles.sql
-- Feature:   Custom workspace roles (extends F007 RBAC)
-- Description:
--   Allows authorized users (workspace_administrator / tenant_admin /
--   platform_admin) to define their own workspace-scoped roles in addition
--   to the five fixed system roles. Each custom role is a named bundle of
--   permissions that lives inside one workspace and can be assigned to
--   members exactly like a fixed role.
--
-- Changes:
--   1) Drop the strict CHECK on workspace_role_assignments.role_name so it
--      accepts any non-empty string. Validity is now enforced at the
--      service layer (must be a fixed role OR a custom role row that
--      belongs to the same workspace).
--   2) Create control.workspace_custom_roles to store custom role
--      definitions (1 row = 1 custom role per workspace).
--   3) Create control.workspace_custom_role_permissions for the
--      role-to-permission mapping (1 row = 1 permission grant).
--   4) Grant DML to the application role.
--
-- Safe to re-run.

BEGIN;

-- 1. Drop fixed-role-only CHECK so custom role names are accepted.
ALTER TABLE control.workspace_role_assignments
    DROP CONSTRAINT IF EXISTS ck_wra_role_name;

ALTER TABLE control.workspace_role_assignments
    ADD CONSTRAINT ck_wra_role_name_nonempty
        CHECK (length(trim(role_name)) > 0);

-- 2. Custom role definitions (per workspace)
CREATE TABLE IF NOT EXISTS control.workspace_custom_roles (
    id            UUID         NOT NULL DEFAULT gen_random_uuid(),
    workspace_id  UUID         NOT NULL,
    name          VARCHAR(60)  NOT NULL,
    display_name  VARCHAR(120) NOT NULL,
    description   TEXT,
    created_by    UUID,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_workspace_custom_roles
        PRIMARY KEY (id),

    CONSTRAINT uq_wcr_workspace_name
        UNIQUE (workspace_id, name),

    CONSTRAINT fk_wcr_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_wcr_created_by
        FOREIGN KEY (created_by)
        REFERENCES users (id)
        ON DELETE SET NULL,

    CONSTRAINT ck_wcr_name_format
        CHECK (name ~ '^[a-z][a-z0-9_]{2,59}$')
);

CREATE INDEX IF NOT EXISTS idx_wcr_workspace
    ON control.workspace_custom_roles (workspace_id);

-- 3. Permission grants for custom roles
CREATE TABLE IF NOT EXISTS control.workspace_custom_role_permissions (
    role_id     UUID         NOT NULL,
    permission  VARCHAR(80)  NOT NULL,

    CONSTRAINT pk_wcrp
        PRIMARY KEY (role_id, permission),

    CONSTRAINT fk_wcrp_role
        FOREIGN KEY (role_id)
        REFERENCES control.workspace_custom_roles (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_wcrp_role
    ON control.workspace_custom_role_permissions (role_id);

-- 4. Grants
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE
                 ON control.workspace_custom_roles
                 TO dq_app_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE
                 ON control.workspace_custom_role_permissions
                 TO dq_app_role';
    END IF;
END;
$$;

COMMIT;
