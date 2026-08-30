-- Migration: 022_f044_alert_channels.sql
-- Feature:   F044 — Alert Channel and Recipient Targeting
-- Packet:    P01 — ORM + Repository + Schema
-- Description:
--   Creates the public.alert_channels table for notification channel config.
--   Extends public.alert_rules with channel_ids and recipient_roles JSONB columns.
--
--   Safe to re-run: all DDL uses IF NOT EXISTS / IF NOT EXISTS checks.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. public.alert_channels table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.alert_channels (

    -- Primary key
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant / workspace scope
    tenant_id           UUID            NOT NULL,
    workspace_id        UUID            NOT NULL,

    -- Content
    name                VARCHAR(200)    NOT NULL,
    channel_type        VARCHAR(50)     NOT NULL,
    configuration       JSONB           NOT NULL DEFAULT '{}'::jsonb,
    enabled             BOOLEAN         NOT NULL DEFAULT TRUE,

    -- Ownership
    created_by_user_id  UUID            NULL,

    -- Timestamps
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT pk_alert_channels PRIMARY KEY (id),

    CONSTRAINT ck_alert_channels_name_length
        CHECK (char_length(name) BETWEEN 1 AND 200),

    CONSTRAINT ck_alert_channels_type
        CHECK (channel_type IN ('email', 'webhook')),

    CONSTRAINT fk_alert_channels_created_by
        FOREIGN KEY (created_by_user_id)
        REFERENCES users (id)
        ON DELETE SET NULL,

    CONSTRAINT uq_alert_channels_workspace_name
        UNIQUE (workspace_id, name)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Indexes
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_alert_channels_workspace_id
    ON public.alert_channels (workspace_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Auto-update updated_at trigger
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.trg_alert_channels_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_channels_updated_at ON public.alert_channels;
CREATE TRIGGER trg_alert_channels_updated_at
    BEFORE UPDATE ON public.alert_channels
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_alert_channels_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Extend alert_rules with channel_ids and recipient_roles
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'alert_rules' AND column_name = 'channel_ids'
    ) THEN
        ALTER TABLE public.alert_rules ADD COLUMN channel_ids JSONB NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'alert_rules' AND column_name = 'recipient_roles'
    ) THEN
        ALTER TABLE public.alert_rules ADD COLUMN recipient_roles JSONB NULL;
    END IF;
END $$;

COMMIT;
