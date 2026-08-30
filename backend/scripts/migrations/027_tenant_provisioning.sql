-- Migration: 027_tenant_provisioning.sql
-- Feature: Tenant Provisioning — automated end-to-end tenant setup
-- Created: 2026-04-06
-- Description:
--   Adds provisioning tracking infrastructure:
--   1. provisioning_status enum on control.tenants
--   2. control.tenant_provisioning_logs for step-level auditability
--   3. Indexes for provisioning queries
--
-- This migration is idempotent — safe to re-run.

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Enum: provisioning_status
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'provisioning_status_enum'
                     AND n.nspname = 'control') THEN
        CREATE TYPE control.provisioning_status_enum AS ENUM (
            'not_started',
            'in_progress',
            'completed',
            'failed',
            'partially_failed'
        );
    END IF;
END$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Add provisioning columns to control.tenants
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control'
          AND table_name = 'tenants'
          AND column_name = 'provisioning_status'
    ) THEN
        ALTER TABLE control.tenants
            ADD COLUMN provisioning_status control.provisioning_status_enum
                NOT NULL DEFAULT 'not_started';
    END IF;
END$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 3. Table: control.tenant_provisioning_logs
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.tenant_provisioning_logs (
    log_id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    tenant_id           UUID            NOT NULL,
    step_name           VARCHAR(100)    NOT NULL,
    step_order          INTEGER         NOT NULL,
    status              VARCHAR(50)     NOT NULL DEFAULT 'pending',  -- pending, success, failed, rolled_back
    started_at          TIMESTAMPTZ     NULL,
    completed_at        TIMESTAMPTZ     NULL,
    error_message       TEXT            NULL,
    step_data           JSONB           NULL,     -- IDs and metadata created in this step
    actor_id            UUID            NOT NULL,
    actor_role          VARCHAR(50)     NOT NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_tenant_provisioning_logs PRIMARY KEY (log_id),
    CONSTRAINT fk_provisioning_logs_tenant
        FOREIGN KEY (tenant_id) REFERENCES control.tenants (tenant_id)
        ON DELETE CASCADE
);

-- Index for listing provisioning steps for a tenant
CREATE INDEX IF NOT EXISTS idx_provisioning_logs_tenant_id
    ON control.tenant_provisioning_logs (tenant_id, step_order);

-- ────────────────────────────────────────────────────────────────────────────
-- 4. Add platform_role and tenant_id to users if missing
-- ────────────────────────────────────────────────────────────────────────────

-- platform_role was added in a prior migration; ensure it exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'platform_role'
    ) THEN
        ALTER TABLE users ADD COLUMN platform_role VARCHAR(50) NULL;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE users ADD COLUMN tenant_id UUID NULL;
    END IF;
END$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 5. Index: lookup users by tenant
-- ────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_users_tenant_id
    ON users (tenant_id) WHERE tenant_id IS NOT NULL;
