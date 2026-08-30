-- Migration: 040_f134_demo_sandbox_schema.sql
-- Feature: F134 — Demo Sandbox Provisioning
-- Packet: P01 — Database Schema and Migration
-- Created: 2026-04-25
-- Description:
--   Part 1:  Four new enum types in the control schema.
--   Part 2:  Add tenant_type column to control.tenants; backfill 'customer'.
--   Part 3:  Add seed_source column to 7 asset tables.
--   Part 4:  Add sandbox_admin to the workspace_role_assignments CHECK constraint.
--   Part 5:  New tables: demo_templates, access_profiles, demo_requests,
--             sandbox_environments, sandbox_users, sandbox_usage_events
--             (range-partitioned by month), sandbox_extensions, provisioning_jobs.
--   Part 6:  Seed rows for demo_templates and access_profiles (MVP defaults).
--   Part 7:  Indexes.
--
-- Idempotent: all DDL uses IF NOT EXISTS or DO $$ guards.
-- Backward compatible: no columns removed; all new columns default/nullable.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 1: Enum types
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'demo_request_status'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.demo_request_status AS ENUM (
            'submitted',
            'under_review',
            'approved',
            'rejected',
            'provisioned',
            'active',
            'expired',
            'archived',
            'converted'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'sandbox_environment_status'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.sandbox_environment_status AS ENUM (
            'provisioning',
            'provisioning_failed',
            'active',
            'suspended',
            'expired',
            'archived',
            'deleted'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'provisioning_job_status'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.provisioning_job_status AS ENUM (
            'pending',
            'running',
            'succeeded',
            'failed'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'sandbox_usage_event_type'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.sandbox_usage_event_type AS ENUM (
            'login',
            'page_view',
            'check_executed',
            'rule_created',
            'rule_edited',
            'dataset_viewed',
            'issue_opened',
            'issue_status_changed',
            'dashboard_viewed',
            'onboarding_step_completed',
            'invitation_accepted',
            'extension_requested',
            'system_notification'
        );
    END IF;
END$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 2: control.tenants — add tenant_type column
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control'
          AND table_name   = 'tenants'
          AND column_name  = 'tenant_type'
    ) THEN
        ALTER TABLE control.tenants
            ADD COLUMN tenant_type VARCHAR(20) NOT NULL DEFAULT 'customer';
    END IF;
END$$;

-- Add CHECK constraint if it does not already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'control'
          AND table_name        = 'tenants'
          AND constraint_name   = 'ck_tenants_tenant_type'
    ) THEN
        ALTER TABLE control.tenants
            ADD CONSTRAINT ck_tenants_tenant_type
                CHECK (tenant_type IN ('customer', 'sandbox', 'internal'));
    END IF;
END$$;

-- Backfill: ensure all pre-existing rows are 'customer'
UPDATE control.tenants
SET    tenant_type = 'customer'
WHERE  tenant_type IS NULL
   OR  tenant_type NOT IN ('customer', 'sandbox', 'internal');

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 3: seed_source column on asset tables
--         NULL for all existing rows; populated only by template seeders.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control'
          AND table_name   = 'data_sources'
          AND column_name  = 'seed_source'
    ) THEN
        ALTER TABLE control.data_sources ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control'
          AND table_name   = 'metadata_term_index'
          AND column_name  = 'seed_source'
    ) THEN
        ALTER TABLE control.metadata_term_index ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- datasets table (may be in public or control schema; try both safely)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'control' AND table_name = 'datasets'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control' AND table_name = 'datasets' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE control.datasets ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'datasets'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE public.datasets ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- dq_rules
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'control' AND table_name = 'dq_rules'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control' AND table_name = 'dq_rules' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE control.dq_rules ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'dq_rules'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'dq_rules' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE public.dq_rules ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- dq_flows
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'control' AND table_name = 'dq_flows'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control' AND table_name = 'dq_flows' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE control.dq_flows ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'dq_flows'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'dq_flows' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE public.dq_flows ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- issues
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'control' AND table_name = 'issues'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control' AND table_name = 'issues' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE control.issues ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'issues'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'issues' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE public.issues ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- dashboards
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'control' AND table_name = 'dashboards'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'control' AND table_name = 'dashboards' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE control.dashboards ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'dashboards'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'dashboards' AND column_name = 'seed_source'
    ) THEN
        ALTER TABLE public.dashboards ADD COLUMN seed_source VARCHAR(80) NULL;
    END IF;
END$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 4: Add sandbox_admin to workspace_role_assignments CHECK constraint
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    -- Only replace constraint if sandbox_admin is not already present
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'control'
          AND table_name        = 'workspace_role_assignments'
          AND constraint_name   = 'ck_wra_role_name'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.conname    = 'ck_wra_role_name'
          AND n.nspname    = 'control'
          AND pg_get_constraintdef(c.oid) LIKE '%sandbox_admin%'
    ) THEN
        ALTER TABLE control.workspace_role_assignments
            DROP CONSTRAINT ck_wra_role_name;
        ALTER TABLE control.workspace_role_assignments
            ADD CONSTRAINT ck_wra_role_name
                CHECK (role_name IN (
                    'workspace_administrator',
                    'data_engineer',
                    'data_steward',
                    'business_analyst',
                    'governance_viewer',
                    'sandbox_admin'
                ));
    END IF;
END$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 5: New tables
-- ─────────────────────────────────────────────────────────────────────────────

-- 5a. demo_templates (seed registry)
CREATE TABLE IF NOT EXISTS control.demo_templates (
    id                   VARCHAR(64)     NOT NULL,
    display_name         VARCHAR(120)    NOT NULL,
    description          TEXT            NOT NULL DEFAULT '',
    seeder_module        VARCHAR(200)    NOT NULL,
    default_duration_days INTEGER        NOT NULL DEFAULT 7,
    is_enabled           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_demo_templates PRIMARY KEY (id)
);

-- 5b. access_profiles (feature-flag bundles)
CREATE TABLE IF NOT EXISTS control.access_profiles (
    id            UUID        NOT NULL DEFAULT gen_random_uuid(),
    code          VARCHAR(64) NOT NULL,
    display_name  VARCHAR(120) NOT NULL,
    flags         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    default_role  VARCHAR(40) NOT NULL DEFAULT 'sandbox_admin',
    is_enabled    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_access_profiles PRIMARY KEY (id),
    CONSTRAINT uq_access_profiles_code UNIQUE (code)
);

-- 5c. demo_requests (public intake)
CREATE TABLE IF NOT EXISTS control.demo_requests (
    id                   UUID                          NOT NULL DEFAULT gen_random_uuid(),
    status               control.demo_request_status  NOT NULL DEFAULT 'submitted',
    public_status_token  VARCHAR(80)                  NOT NULL,
    work_email           VARCHAR(254)                 NOT NULL,
    first_name           VARCHAR(60)                  NOT NULL,
    last_name            VARCHAR(60)                  NOT NULL,
    company_name         VARCHAR(120)                 NOT NULL,
    job_title            VARCHAR(120)                 NULL,
    team_size            VARCHAR(20)                  NOT NULL,
    country              CHAR(2)                      NULL,
    primary_use_case     TEXT                         NOT NULL,
    stack                JSONB                        NOT NULL DEFAULT '{}'::jsonb,
    heard_about_us       VARCHAR(80)                  NULL,
    consent              BOOLEAN                      NOT NULL DEFAULT FALSE,
    is_personal_email    BOOLEAN                      NOT NULL DEFAULT FALSE,
    source_ip            INET                         NULL,
    user_agent           TEXT                         NULL,
    admin_tags           JSONB                        NOT NULL DEFAULT '[]'::jsonb,
    internal_note        TEXT                         NULL,
    rejection_reason     TEXT                         NULL,
    decided_by           UUID                         NULL,
    decided_at           TIMESTAMPTZ                  NULL,
    created_at           TIMESTAMPTZ                  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ                  NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_demo_requests PRIMARY KEY (id),
    CONSTRAINT uq_demo_requests_public_status_token UNIQUE (public_status_token),
    CONSTRAINT chk_demo_requests_consent
        CHECK (consent = TRUE),
    CONSTRAINT fk_demo_requests_decided_by
        FOREIGN KEY (decided_by) REFERENCES users (id) ON DELETE SET NULL
);

-- 5d. sandbox_environments
CREATE TABLE IF NOT EXISTS control.sandbox_environments (
    id                   UUID                              NOT NULL DEFAULT gen_random_uuid(),
    demo_request_id      UUID                             NOT NULL,
    tenant_id            UUID                             NOT NULL,
    workspace_id         UUID                             NOT NULL,
    template_id          VARCHAR(64)                      NOT NULL,
    access_profile_id    UUID                             NOT NULL,
    status               control.sandbox_environment_status NOT NULL DEFAULT 'provisioning',
    provisioned_at       TIMESTAMPTZ                      NULL,
    expires_at           TIMESTAMPTZ                      NULL,
    suspended_at         TIMESTAMPTZ                      NULL,
    archived_at          TIMESTAMPTZ                      NULL,
    deleted_at           TIMESTAMPTZ                      NULL,
    extension_count      SMALLINT                         NOT NULL DEFAULT 0,
    grace_period_days    SMALLINT                         NOT NULL DEFAULT 3,
    retention_policy     VARCHAR(40)                      NOT NULL DEFAULT 'retain_metadata_only',
    engagement_score     VARCHAR(10)                      NOT NULL DEFAULT 'unknown',
    last_activity_at     TIMESTAMPTZ                      NULL,
    session_count        INTEGER                          NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ                      NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ                      NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_sandbox_environments PRIMARY KEY (id),
    CONSTRAINT uq_sandbox_env_demo_request UNIQUE (demo_request_id),
    CONSTRAINT chk_sandbox_env_extension_count CHECK (extension_count <= 2),
    CONSTRAINT chk_sandbox_env_expires_after_provisioned
        CHECK (
            expires_at IS NULL
            OR provisioned_at IS NULL
            OR expires_at > provisioned_at
        ),
    CONSTRAINT fk_sandbox_env_demo_request
        FOREIGN KEY (demo_request_id) REFERENCES control.demo_requests (id),
    CONSTRAINT fk_sandbox_env_template
        FOREIGN KEY (template_id) REFERENCES control.demo_templates (id),
    CONSTRAINT fk_sandbox_env_access_profile
        FOREIGN KEY (access_profile_id) REFERENCES control.access_profiles (id),
    CONSTRAINT fk_sandbox_env_tenant
        FOREIGN KEY (tenant_id) REFERENCES control.tenants (tenant_id)
);

-- 5e. sandbox_users
CREATE TABLE IF NOT EXISTS control.sandbox_users (
    id                       UUID        NOT NULL DEFAULT gen_random_uuid(),
    sandbox_id               UUID        NULL,
    user_id                  UUID        NULL,
    invitation_token_hash    CHAR(64)    NULL,
    invitation_expires_at    TIMESTAMPTZ NULL,
    invitation_accepted_at   TIMESTAMPTZ NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_sandbox_users PRIMARY KEY (id),
    CONSTRAINT fk_sandbox_users_sandbox
        FOREIGN KEY (sandbox_id)
        REFERENCES control.sandbox_environments (id) ON DELETE SET NULL,
    CONSTRAINT fk_sandbox_users_user
        FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE SET NULL
);

-- 5f. sandbox_usage_events (partitioned by month)
CREATE TABLE IF NOT EXISTS control.sandbox_usage_events (
    id              BIGSERIAL                          NOT NULL,
    sandbox_id      UUID                               NULL,
    user_id         UUID                               NULL,
    event_type      control.sandbox_usage_event_type  NOT NULL,
    event_payload   JSONB                              NOT NULL DEFAULT '{}'::jsonb,
    request_id      UUID                               NULL,
    source_ip       INET                               NULL,
    occurred_at     TIMESTAMPTZ                        NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_sandbox_usage_events PRIMARY KEY (id, occurred_at),
    CONSTRAINT fk_sue_sandbox
        FOREIGN KEY (sandbox_id)
        REFERENCES control.sandbox_environments (id) ON DELETE SET NULL,
    CONSTRAINT fk_sue_user
        FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE SET NULL
) PARTITION BY RANGE (occurred_at);

-- Initial monthly partition (covers first deployment month and 2 following)
DO $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
    i INT;
BEGIN
    FOR i IN 0..2 LOOP
        start_date := date_trunc('month', NOW()) + (i * interval '1 month');
        end_date   := start_date + interval '1 month';
        partition_name := 'sandbox_usage_events_' || to_char(start_date, 'YYYYMM');
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = partition_name
              AND n.nspname = 'control'
        ) THEN
            EXECUTE format(
                'CREATE TABLE control.%I PARTITION OF control.sandbox_usage_events
                 FOR VALUES FROM (%L) TO (%L)',
                partition_name, start_date, end_date
            );
        END IF;
    END LOOP;
END$$;

-- 5g. sandbox_extensions
CREATE TABLE IF NOT EXISTS control.sandbox_extensions (
    id                   UUID        NOT NULL DEFAULT gen_random_uuid(),
    sandbox_id           UUID        NOT NULL,
    extended_by          UUID        NULL,
    extension_days       SMALLINT    NOT NULL DEFAULT 3,
    note                 TEXT        NOT NULL,
    previous_expires_at  TIMESTAMPTZ NOT NULL,
    new_expires_at       TIMESTAMPTZ NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_sandbox_extensions PRIMARY KEY (id),
    CONSTRAINT chk_sandbox_ext_days CHECK (extension_days = 3),
    CONSTRAINT fk_sandbox_ext_sandbox
        FOREIGN KEY (sandbox_id)
        REFERENCES control.sandbox_environments (id) ON DELETE CASCADE,
    CONSTRAINT fk_sandbox_ext_user
        FOREIGN KEY (extended_by)
        REFERENCES users (id) ON DELETE SET NULL
);

-- 5h. provisioning_jobs
CREATE TABLE IF NOT EXISTS control.provisioning_jobs (
    id               UUID                           NOT NULL DEFAULT gen_random_uuid(),
    demo_request_id  UUID                           NOT NULL,
    sandbox_id       UUID                           NULL,
    status           control.provisioning_job_status NOT NULL DEFAULT 'pending',
    attempt_count    SMALLINT                        NOT NULL DEFAULT 0,
    last_error       TEXT                            NULL,
    started_at       TIMESTAMPTZ                     NULL,
    finished_at      TIMESTAMPTZ                     NULL,
    celery_task_id   VARCHAR(120)                    NULL,
    created_at       TIMESTAMPTZ                     NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ                     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_provisioning_jobs PRIMARY KEY (id),
    CONSTRAINT fk_pj_demo_request
        FOREIGN KEY (demo_request_id)
        REFERENCES control.demo_requests (id),
    CONSTRAINT fk_pj_sandbox
        FOREIGN KEY (sandbox_id)
        REFERENCES control.sandbox_environments (id) ON DELETE SET NULL
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 6: Seed rows
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO control.demo_templates (id, display_name, description, seeder_module, default_duration_days, is_enabled)
VALUES (
    'general_dq',
    'General Data Quality Evaluation',
    'A turnkey sandbox preloaded with synthetic datasets, DQ rules, flows, issues, a dashboard, and a glossary to demonstrate the full data quality lifecycle.',
    'app.services.demo.templates.general_dq',
    7,
    TRUE
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO control.access_profiles (code, display_name, flags, default_role, is_enabled)
VALUES (
    'mvp_default',
    'MVP Default (Demo Sandbox)',
    '{"platform_admin_hidden": true, "destructive_operations_disabled": true, "external_integrations_disabled": true}'::jsonb,
    'sandbox_admin',
    TRUE
)
ON CONFLICT (code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 7: Indexes
-- ─────────────────────────────────────────────────────────────────────────────

-- demo_requests
CREATE INDEX IF NOT EXISTS ix_demo_requests_status
    ON control.demo_requests (status);

CREATE INDEX IF NOT EXISTS ix_demo_requests_created_at
    ON control.demo_requests (created_at DESC);

-- Partial index: active/recent requests per email (supports BR-001 dedupe check)
CREATE INDEX IF NOT EXISTS ix_demo_requests_email_active
    ON control.demo_requests (work_email)
    WHERE status IN ('submitted', 'under_review', 'approved', 'provisioned', 'active');

-- sandbox_environments
CREATE INDEX IF NOT EXISTS ix_sandbox_env_status
    ON control.sandbox_environments (status);

CREATE INDEX IF NOT EXISTS ix_sandbox_env_tenant
    ON control.sandbox_environments (tenant_id);

-- Partial index: expiration scanner hot path
CREATE INDEX IF NOT EXISTS ix_sandbox_env_expires_at
    ON control.sandbox_environments (expires_at)
    WHERE status IN ('active', 'suspended');

-- sandbox_users
CREATE INDEX IF NOT EXISTS ix_sandbox_users_sandbox
    ON control.sandbox_users (sandbox_id);

CREATE INDEX IF NOT EXISTS ix_sandbox_users_user
    ON control.sandbox_users (user_id);

-- sandbox_extensions
CREATE INDEX IF NOT EXISTS ix_sandbox_extensions_sandbox
    ON control.sandbox_extensions (sandbox_id);

-- provisioning_jobs
CREATE INDEX IF NOT EXISTS ix_provisioning_jobs_demo_request
    ON control.provisioning_jobs (demo_request_id);

CREATE INDEX IF NOT EXISTS ix_provisioning_jobs_status
    ON control.provisioning_jobs (status);

COMMIT;
