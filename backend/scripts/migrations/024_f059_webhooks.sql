-- Migration 024: F059 — Webhook and Event Delivery
-- Creates webhook_subscriptions and webhook_delivery_log tables
-- webhook_subscriptions: stores target URLs and event type subscriptions per workspace
-- webhook_delivery_log: tracks dispatch attempts with retry state

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Webhook Subscriptions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE public.webhook_subscriptions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID        NOT NULL,
    tenant_id       UUID        NOT NULL,
    name            VARCHAR(200) NOT NULL,
    target_url      TEXT        NOT NULL,
    -- HMAC-SHA256 key used for signing payloads (stored as hex digest)
    secret_key      TEXT        NOT NULL,
    -- Array of event types this subscription listens for
    -- Allowed values: execution_failed, issue_created, incident_created, incident_updated
    event_types     TEXT[]      NOT NULL DEFAULT '{}',
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by      UUID        REFERENCES public.users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_webhook_subscriptions_name
        CHECK (char_length(name) BETWEEN 1 AND 200),
    CONSTRAINT ck_webhook_subscriptions_url
        CHECK (char_length(target_url) >= 1)
);

CREATE INDEX idx_webhook_subscriptions_workspace ON public.webhook_subscriptions (workspace_id);
CREATE INDEX idx_webhook_subscriptions_enabled   ON public.webhook_subscriptions (workspace_id, enabled)
    WHERE enabled = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Webhook Delivery Log
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE public.webhook_delivery_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id     UUID        NOT NULL REFERENCES public.webhook_subscriptions(id) ON DELETE CASCADE,
    workspace_id        UUID        NOT NULL,
    event_type          VARCHAR(100) NOT NULL,
    payload             JSONB       NOT NULL DEFAULT '{}',
    -- Delivery status: pending | delivered | failed | retrying | abandoned
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    attempt_count       INT         NOT NULL DEFAULT 0,
    max_attempts        INT         NOT NULL DEFAULT 3,
    last_attempt_at     TIMESTAMPTZ,
    next_attempt_at     TIMESTAMPTZ,
    http_response_code  INT,
    last_error          TEXT,
    delivered_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_webhook_delivery_status CHECK (
        status IN ('pending', 'delivered', 'failed', 'retrying', 'abandoned')
    ),
    CONSTRAINT ck_webhook_delivery_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_webhook_delivery_max_attempts CHECK (max_attempts >= 1)
);

CREATE INDEX idx_webhook_delivery_subscription ON public.webhook_delivery_log (subscription_id);
CREATE INDEX idx_webhook_delivery_status       ON public.webhook_delivery_log (status)
    WHERE status IN ('pending', 'retrying');
CREATE INDEX idx_webhook_delivery_workspace    ON public.webhook_delivery_log (workspace_id);

COMMIT;
