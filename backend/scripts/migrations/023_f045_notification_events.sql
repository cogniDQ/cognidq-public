-- Migration: 023_f045_notification_events.sql
-- Feature:   F045 — Notification Event Logging
-- Packet:    P01 — ORM + Repository + Schema
-- Description:
--   Creates the public.notification_events table for tracking notification
--   delivery status, retries, and payloads.
--
--   Safe to re-run: all DDL uses IF NOT EXISTS checks.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. public.notification_events table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.notification_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID        NOT NULL,
    workspace_id    UUID        NOT NULL,
    alert_rule_id   UUID        NOT NULL REFERENCES public.alert_rules(id) ON DELETE CASCADE,
    alert_channel_id UUID       NOT NULL REFERENCES public.alert_channels(id) ON DELETE CASCADE,
    recipient       VARCHAR(500) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'failed', 'retrying')),
    payload         JSONB,
    retry_count     INTEGER     NOT NULL DEFAULT 0,
    max_retries     INTEGER     NOT NULL DEFAULT 3,
    last_error      TEXT,
    sent_at         TIMESTAMP WITH TIME ZONE,
    delivered_at    TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Indexes
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_notification_events_workspace_status
    ON public.notification_events (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_notification_events_rule
    ON public.notification_events (alert_rule_id);

CREATE INDEX IF NOT EXISTS idx_notification_events_channel
    ON public.notification_events (alert_channel_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Auto-update trigger for updated_at
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.trg_notification_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notification_events_updated_at
    ON public.notification_events;

CREATE TRIGGER trg_notification_events_updated_at
    BEFORE UPDATE ON public.notification_events
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_notification_events_updated_at();

COMMIT;
