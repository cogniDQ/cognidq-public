-- Migration: 012_f007_workspace_role_assignments.sql
-- Feature:   F007 — RBAC and Permission System
-- Packet:    P01 — DB Migration: workspace_role_assignments
-- Created:   2026-03-30
-- Description:
--   Creates the control.workspace_role_assignments table which stores the
--   single fixed workspace role held by each workspace member.
--
--   Fixed roles (enforced by CHECK constraint):
--     workspace_administrator, data_engineer, data_steward,
--     business_analyst, governance_viewer
--
--   Key constraints:
--     UNIQUE (workspace_id, user_id)  — one role per user per workspace
--     CHECK (role_name IN (...))      — only fixed roles accepted
--     ON DELETE CASCADE on workspace  — role removed when workspace deleted
--     ON DELETE CASCADE on user       — role removed when user deleted
--
-- Safe to re-run: all DDL uses IF NOT EXISTS.
-- No existing tables are modified.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Create workspace_role_assignments table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.workspace_role_assignments (
    id            UUID         NOT NULL DEFAULT gen_random_uuid(),
    workspace_id  UUID         NOT NULL,
    user_id       UUID         NOT NULL,
    role_name     VARCHAR(60)  NOT NULL,
    granted_by    UUID,
    granted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_workspace_role_assignments
        PRIMARY KEY (id),

    CONSTRAINT uq_wra_user_workspace
        UNIQUE (workspace_id, user_id),

    CONSTRAINT fk_wra_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_wra_user
        FOREIGN KEY (user_id)
        REFERENCES users (id)
        ON DELETE CASCADE,

    CONSTRAINT fk_wra_granted_by
        FOREIGN KEY (granted_by)
        REFERENCES users (id)
        ON DELETE SET NULL,

    CONSTRAINT ck_wra_role_name
        CHECK (role_name IN (
            'workspace_administrator',
            'data_engineer',
            'data_steward',
            'business_analyst',
            'governance_viewer'
        ))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Indexes
-- ─────────────────────────────────────────────────────────────────────────────

-- Supports: admin count check, member-role list join (by workspace)
CREATE INDEX IF NOT EXISTS idx_wra_workspace
    ON control.workspace_role_assignments (workspace_id);

-- Supports: user-centric queries (all workspaces for a user)
CREATE INDEX IF NOT EXISTS idx_wra_user
    ON control.workspace_role_assignments (user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Grant permissions to application role
-- ─────────────────────────────────────────────────────────────────────────────

-- dq_app_role is the application database role established in migration 006.
-- Allow full DML; no DDL rights for the application.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role'
    ) THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE
                 ON control.workspace_role_assignments
                 TO dq_app_role';
    END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Rollback instructions (manual, not executed here)
-- ─────────────────────────────────────────────────────────────────────────────
-- To roll back:
--   DROP TABLE IF EXISTS control.workspace_role_assignments;

COMMIT;
