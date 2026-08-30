-- Migration: 021_f043_alert_rules.sql
-- Feature:   F043 — Alert Rule Configuration
-- Packet:    P01 — ORM + Repository + Schema
-- Description:
--   Creates the public.alert_rules table for configurable alert triggers.
--
--   Key constraints:
--     CHECK (trigger_type IN (...5 supported types...))
--     CHECK (char_length(name) BETWEEN 1 AND 200)
--     UNIQUE (workspace_id, name)
--     FK created_by_user_id → users(id) ON DELETE SET NULL
--
--   Safe to re-run: all DDL uses IF NOT EXISTS.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. public.alert_rules table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.alert_rules (

    -- Primary key
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant / workspace scope
    tenant_id           UUID            NOT NULL,
    workspace_id        UUID            NOT NULL,

    -- Content
    name                VARCHAR(200)    NOT NULL,
    trigger_type        VARCHAR(50)     NOT NULL,
    conditions          JSONB           NULL,
    recipient_user_ids  JSONB           NOT NULL,
    enabled             BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Ownership
    created_by_user_id  UUID            NULL,

    -- Timestamps
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT pk_alert_rules PRIMARY KEY (id),

    CONSTRAINT ck_alert_rules_name_length
        CHECK (char_length(name) BETWEEN 1 AND 200),

    CONSTRAINT ck_alert_rules_trigger_type
        CHECK (trigger_type IN (
            'execution_failed',
            'issue_created',
            'issue_overdue',
            'incident_created',
            'incident_status_changed'
        )),

    CONSTRAINT fk_alert_rules_created_by
        FOREIGN KEY (created_by_user_id)
        REFERENCES users (id)
        ON DELETE SET NULL,

    CONSTRAINT uq_alert_rules_workspace_name
        UNIQUE (workspace_id, name)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Indexes
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_alert_rules_workspace_id
    ON public.alert_rules (workspace_id);

CREATE INDEX IF NOT EXISTS ix_alert_rules_trigger_type
    ON public.alert_rules (trigger_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Auto-update updated_at trigger
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.trg_alert_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_rules_updated_at ON public.alert_rules;
CREATE TRIGGER trg_alert_rules_updated_at
    BEFORE UPDATE ON public.alert_rules
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_alert_rules_updated_at();

COMMIT;
