-- Migration: 041_onboarding_hardening.sql
-- Date:      2026-04-24
-- Purpose:   Fix all P0 onboarding/auth bugs identified in the QA report
--            documentation/qa/new-customer-onboarding-qa-report-2026-04-24.md
--
-- This migration is idempotent — every object is guarded by IF (NOT) EXISTS
-- or a duplicate_object catch, so re-running is safe.

BEGIN;

-- ════════════════════════════════════════════════════════════════════════════
-- BUG-001  Tenant provisioning broken (restores payload from migration 027
--         that was never applied against the live DB).
-- ════════════════════════════════════════════════════════════════════════════

-- 1.a  Enum control.provisioning_status_enum
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'provisioning_status_enum'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.provisioning_status_enum AS ENUM (
            'not_started',
            'in_progress',
            'completed',
            'failed',
            'partially_failed'
        );
    END IF;
END$$;

-- 1.b  control.tenants.provisioning_status column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'control'
          AND table_name   = 'tenants'
          AND column_name  = 'provisioning_status'
    ) THEN
        ALTER TABLE control.tenants
            ADD COLUMN provisioning_status control.provisioning_status_enum
                NOT NULL DEFAULT 'not_started';
    END IF;
END$$;

-- 1.c  Provisioning step-level audit table
CREATE TABLE IF NOT EXISTS control.tenant_provisioning_logs (
    log_id         UUID         NOT NULL DEFAULT gen_random_uuid(),
    tenant_id      UUID         NOT NULL,
    step_name      VARCHAR(100) NOT NULL,
    step_order     INTEGER      NOT NULL,
    status         VARCHAR(50)  NOT NULL DEFAULT 'pending',
    started_at     TIMESTAMPTZ  NULL,
    completed_at   TIMESTAMPTZ  NULL,
    error_message  TEXT         NULL,
    step_data      JSONB        NULL,
    actor_id       UUID         NOT NULL,
    actor_role     VARCHAR(50)  NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_tenant_provisioning_logs PRIMARY KEY (log_id),
    CONSTRAINT fk_provisioning_logs_tenant
        FOREIGN KEY (tenant_id) REFERENCES control.tenants (tenant_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_provisioning_logs_tenant_id
    ON control.tenant_provisioning_logs (tenant_id, step_order);

-- 1.d  users.platform_role & users.tenant_id (defensive — may already exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='users' AND column_name='platform_role'
    ) THEN
        ALTER TABLE users ADD COLUMN platform_role VARCHAR(50) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='users' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE users ADD COLUMN tenant_id UUID NULL;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_users_tenant_id
    ON users (tenant_id) WHERE tenant_id IS NOT NULL;

-- ════════════════════════════════════════════════════════════════════════════
-- BUG-005  Session revocation on logout.
--          Add revoked_at to public.sessions; JWT checks still rely on
--          session existence, but this flag lets the logout endpoint mark
--          a session revoked without deleting it (so audit trail survives).
-- ════════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='sessions' AND column_name='revoked_at'
    ) THEN
        ALTER TABLE sessions ADD COLUMN revoked_at TIMESTAMPTZ NULL;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_sessions_active
    ON sessions (id) WHERE revoked_at IS NULL;

-- ════════════════════════════════════════════════════════════════════════════
-- BUG-012  control.workspaces.workspace_name_lower not generated.
--          Convert the existing column to a GENERATED ALWAYS STORED column
--          so every INSERT path auto-populates it, matching control.tenants.
-- ════════════════════════════════════════════════════════════════════════════

DO $$
DECLARE
    v_is_generated TEXT;
BEGIN
    SELECT is_generated INTO v_is_generated
    FROM information_schema.columns
    WHERE table_schema='control'
      AND table_name='workspaces'
      AND column_name='workspace_name_lower';

    IF v_is_generated IS DISTINCT FROM 'ALWAYS' THEN
        -- Backfill anything null just in case.
        UPDATE control.workspaces
        SET workspace_name_lower = LOWER(TRIM(workspace_name))
        WHERE workspace_name_lower IS NULL
           OR workspace_name_lower <> LOWER(TRIM(workspace_name));

        -- Drop dependent unique index, convert to generated, recreate the index.
        ALTER TABLE control.workspaces
            DROP CONSTRAINT IF EXISTS uq_workspaces_name_lower_per_tenant;

        ALTER TABLE control.workspaces
            DROP COLUMN workspace_name_lower;

        ALTER TABLE control.workspaces
            ADD COLUMN workspace_name_lower VARCHAR(150)
                GENERATED ALWAYS AS (LOWER(TRIM(workspace_name))) STORED;

        ALTER TABLE control.workspaces
            ADD CONSTRAINT uq_workspaces_name_lower_per_tenant
                UNIQUE (tenant_id, workspace_name_lower);
    END IF;
END$$;

-- ════════════════════════════════════════════════════════════════════════════
-- BUG-013  control.workspaces.created_at / updated_at missing DEFAULT now()
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE control.workspaces ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE control.workspaces ALTER COLUMN updated_at SET DEFAULT now();

-- ════════════════════════════════════════════════════════════════════════════
-- GAP-004  Invitation flow — extend public.invitations with tenant scope
--          plus explicit invitee_name and invited_by_role. Existing rows
--          remain valid; the new columns are nullable/defaulted.
-- ════════════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='invitations' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE invitations ADD COLUMN tenant_id UUID NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='invitations' AND column_name='invitee_name'
    ) THEN
        ALTER TABLE invitations ADD COLUMN invitee_name VARCHAR(255) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='invitations' AND column_name='status'
    ) THEN
        ALTER TABLE invitations
            ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'pending';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='invitations' AND column_name='accepted_at'
    ) THEN
        ALTER TABLE invitations ADD COLUMN accepted_at TIMESTAMPTZ NULL;
    END IF;

    -- Best-effort FK (skip if control.tenants not reachable for some reason).
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema='public'
          AND table_name='invitations'
          AND constraint_name='fk_invitations_tenant'
    ) THEN
        BEGIN
            ALTER TABLE invitations
                ADD CONSTRAINT fk_invitations_tenant
                FOREIGN KEY (tenant_id) REFERENCES control.tenants(tenant_id)
                ON DELETE CASCADE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'Skipping fk_invitations_tenant: %', SQLERRM;
        END;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_invitations_tenant_email
    ON invitations (tenant_id, LOWER(email))
    WHERE status = 'pending';

COMMIT;
