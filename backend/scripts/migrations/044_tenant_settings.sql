-- Migration: 044_tenant_settings.sql
-- Purpose:
--   Adds the tenant_settings table for tenant-scoped configurable external
--   service credentials. The first consumer is SMTP (alert email delivery
--   fallback when an AlertChannel does not specify SMTP credentials).
--
-- Schema rationale:
--   * One row per tenant (1:1 with control.tenants).
--   * Encrypted columns (BYTEA) hold Fernet ciphertext of secret values
--     (currently smtp_password). Encryption uses CREDENTIAL_ENCRYPTION_KEY.
--   * smtp_enabled is the runtime gate the dispatcher consults.
--   * created_by / updated_by track admin identity for audit trail.

BEGIN;

CREATE TABLE IF NOT EXISTS control.tenant_settings (
    tenant_id           UUID PRIMARY KEY
                              REFERENCES control.tenants(tenant_id)
                              ON DELETE CASCADE,

    -- SMTP block (tenant-managed external service; NULL means "not configured")
    smtp_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    smtp_host           VARCHAR(255),
    smtp_port           INTEGER,
    smtp_username       VARCHAR(255),
    smtp_password_enc   BYTEA,
    smtp_use_tls        BOOLEAN NOT NULL DEFAULT TRUE,
    smtp_from_address   VARCHAR(255),
    smtp_last_tested_at TIMESTAMPTZ,
    smtp_last_test_ok   BOOLEAN,
    smtp_last_test_error VARCHAR(2000),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by          UUID,
    updated_by          UUID,
    version             INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT ck_tenant_settings_smtp_port
        CHECK (smtp_port IS NULL OR (smtp_port BETWEEN 1 AND 65535))
);

CREATE INDEX IF NOT EXISTS ix_tenant_settings_updated_at
    ON control.tenant_settings (updated_at);

-- Auto-touch updated_at
CREATE OR REPLACE FUNCTION control.fn_tenant_settings_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    NEW.version    := COALESCE(OLD.version, 0) + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenant_settings_touch ON control.tenant_settings;
CREATE TRIGGER trg_tenant_settings_touch
    BEFORE UPDATE ON control.tenant_settings
    FOR EACH ROW
    EXECUTE FUNCTION control.fn_tenant_settings_touch_updated_at();

-- Auto-create default row for every existing/new tenant
CREATE OR REPLACE FUNCTION control.fn_create_default_tenant_settings()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO control.tenant_settings (tenant_id, created_by, updated_by)
    VALUES (NEW.tenant_id, NEW.created_by, NEW.updated_by)
    ON CONFLICT (tenant_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenants_create_settings ON control.tenants;
CREATE TRIGGER trg_tenants_create_settings
    AFTER INSERT ON control.tenants
    FOR EACH ROW
    EXECUTE FUNCTION control.fn_create_default_tenant_settings();

-- Backfill existing tenants
INSERT INTO control.tenant_settings (tenant_id, created_by, updated_by)
SELECT t.tenant_id, t.created_by, t.updated_by
FROM control.tenants t
ON CONFLICT (tenant_id) DO NOTHING;

COMMIT;
