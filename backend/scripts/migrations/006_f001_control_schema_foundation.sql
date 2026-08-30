-- Migration: 006_f001_control_schema_foundation.sql
-- Feature: F001 — Tenant Creation and Lifecycle
-- Packet: P1 — Database Schema Foundation
-- Created: 2026-03-26
-- Description:
--   Establishes the complete control-plane PostgreSQL schema for F001:
--   three enum types, the tenants table, tenant_audit_logs table, and
--   outbox_events table, along with all indexes, constraints, and the
--   append-only REVOKE on tenant_audit_logs.
--
-- Convention: tenant_name_lower is a GENERATED ALWAYS AS computed column
--   (LOWER(TRIM(tenant_name)) STORED). Application layer must NOT provide
--   a value for this column in INSERT or UPDATE statements.
--
-- Application DB role: dq_app_role (NOLOGIN). The application should
--   connect as this role (or a role inheriting from it) in all environments.
--   In the current dev environment the postgres superuser is used; the role
--   is created here so that the REVOKE semantics are testable.

-- ────────────────────────────────────────────────────────────────────────────
-- 0. Prerequisites
-- ────────────────────────────────────────────────────────────────────────────

-- Create the control schema (all F001 objects live here)
CREATE SCHEMA IF NOT EXISTS control;

-- Enable trigram extension (required for GIN trgm indexes on tenants)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ────────────────────────────────────────────────────────────────────────────
-- 1. Enum Types
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'tenant_status_enum'
                     AND n.nspname = 'control') THEN
        CREATE TYPE control.tenant_status_enum AS ENUM (
            'draft',
            'active',
            'suspended',
            'archived'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'tenant_region_enum'
                     AND n.nspname = 'control') THEN
        CREATE TYPE control.tenant_region_enum AS ENUM (
            'eu-west',
            'eu-central',
            'us-east',
            'us-west'
        );
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t
                   JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'tenant_plan_enum'
                     AND n.nspname = 'control') THEN
        CREATE TYPE control.tenant_plan_enum AS ENUM (
            'starter',
            'growth',
            'enterprise'
        );
    END IF;
END$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 2. Table: control.tenants  (16 columns)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.tenants (
    tenant_id         UUID                        NOT NULL DEFAULT gen_random_uuid(),
    tenant_name       VARCHAR(150)                NOT NULL,
    -- Computed from tenant_name; managed at DB level; never set by application code.
    tenant_name_lower VARCHAR(150)                GENERATED ALWAYS AS (LOWER(TRIM(tenant_name))) STORED,
    tenant_slug       VARCHAR(80)                 NOT NULL,
    status            control.tenant_status_enum  NOT NULL DEFAULT 'draft',
    status_reason     VARCHAR(500)                NULL,
    region            control.tenant_region_enum  NOT NULL,
    plan              control.tenant_plan_enum    NOT NULL,
    service_start_date DATE                       NULL,
    tenant_notes      VARCHAR(5000)               NULL,
    created_at        TIMESTAMPTZ                 NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ                 NOT NULL DEFAULT NOW(),
    created_by        UUID                        NOT NULL,
    updated_by        UUID                        NOT NULL,
    version           INTEGER                     NOT NULL DEFAULT 0,

    CONSTRAINT pk_tenants PRIMARY KEY (tenant_id),

    -- status_reason is mandatory (≥ 10 non-whitespace chars) for suspended/archived
    CONSTRAINT chk_tenants_status_reason CHECK (
        status NOT IN ('suspended', 'archived')
        OR (
            status_reason IS NOT NULL
            AND TRIM(status_reason) <> ''
            AND LENGTH(TRIM(status_reason)) >= 10
        )
    )
);

-- ────────────────────────────────────────────────────────────────────────────
-- 3. Table: control.tenant_audit_logs  (9 columns)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.tenant_audit_logs (
    log_id        UUID          NOT NULL DEFAULT gen_random_uuid(),
    tenant_id     UUID          NOT NULL,
    event_type    VARCHAR(50)   NOT NULL,
    actor_id      UUID          NOT NULL,
    actor_role    VARCHAR(50)   NOT NULL,
    previous_data JSONB         NULL,
    new_data      JSONB         NOT NULL,
    occurred_at   TIMESTAMPTZ   NOT NULL,
    reason        VARCHAR(500)  NULL,

    CONSTRAINT pk_tenant_audit_logs PRIMARY KEY (log_id),
    CONSTRAINT fk_audit_logs_tenant_id FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE RESTRICT
);

-- ────────────────────────────────────────────────────────────────────────────
-- 4. Table: control.outbox_events  (9 columns)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.outbox_events (
    event_id     UUID          NOT NULL DEFAULT gen_random_uuid(),
    event_type   VARCHAR(100)  NOT NULL,
    tenant_id    UUID          NOT NULL,
    payload      JSONB         NOT NULL,
    occurred_at  TIMESTAMPTZ   NOT NULL,
    delivered    BOOLEAN       NOT NULL DEFAULT FALSE,
    delivered_at TIMESTAMPTZ   NULL,
    retry_count  INTEGER       NOT NULL DEFAULT 0,
    last_error   TEXT          NULL,

    CONSTRAINT pk_outbox_events PRIMARY KEY (event_id)
);

-- ────────────────────────────────────────────────────────────────────────────
-- 5. Indexes on control.tenants
--    (pk_tenants already added inline above)
-- ────────────────────────────────────────────────────────────────────────────

-- Case-insensitive name uniqueness (enforced via generated column)
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_name_lower
    ON control.tenants (tenant_name_lower);

-- Slug uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_slug
    ON control.tenants (tenant_slug);

-- Composite indexes for filtered + sorted list queries
CREATE INDEX IF NOT EXISTS ix_tenants_status_created_at
    ON control.tenants USING BTREE (status, created_at);

CREATE INDEX IF NOT EXISTS ix_tenants_region_created_at
    ON control.tenants USING BTREE (region, created_at);

CREATE INDEX IF NOT EXISTS ix_tenants_plan_created_at
    ON control.tenants USING BTREE (plan, created_at);

-- Single-column date indexes for unfiltered sort queries
CREATE INDEX IF NOT EXISTS ix_tenants_created_at
    ON control.tenants USING BTREE (created_at);

CREATE INDEX IF NOT EXISTS ix_tenants_updated_at
    ON control.tenants USING BTREE (updated_at);

-- GIN trigram indexes for ILIKE fragment search
CREATE INDEX IF NOT EXISTS ix_tenants_name_trgm
    ON control.tenants USING GIN (tenant_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_tenants_slug_trgm
    ON control.tenants USING GIN (tenant_slug gin_trgm_ops);

-- ────────────────────────────────────────────────────────────────────────────
-- 6. Indexes on control.tenant_audit_logs
--    (pk_tenant_audit_logs already added inline above)
-- ────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_occurred_at
    ON control.tenant_audit_logs USING BTREE (tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type
    ON control.tenant_audit_logs USING BTREE (event_type);

CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id
    ON control.tenant_audit_logs USING BTREE (actor_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 7. Index on control.outbox_events
-- ────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_outbox_events_delivered_occurred_at
    ON control.outbox_events USING BTREE (delivered, occurred_at);

-- ────────────────────────────────────────────────────────────────────────────
-- 8. Security: REVOKE UPDATE / DELETE on tenant_audit_logs
--    tenant_audit_logs is append-only; no row may ever be mutated or removed
--    by the application layer.
-- ────────────────────────────────────────────────────────────────────────────

-- Revoke from PUBLIC so that newly created roles do not inherit these privileges
REVOKE UPDATE, DELETE ON control.tenant_audit_logs FROM PUBLIC;

-- Create the application DB role if it does not yet exist, then revoke from it.
-- In production the application process must run as dq_app_role (or a role
-- inheriting from it). The postgres superuser used in development bypasses
-- privilege checks and is not subject to this REVOKE.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        CREATE ROLE dq_app_role NOLOGIN;
    END IF;
END$$;

GRANT USAGE ON SCHEMA control TO dq_app_role;
GRANT SELECT, INSERT ON control.tenants            TO dq_app_role;
GRANT SELECT, INSERT ON control.tenant_audit_logs  TO dq_app_role;
GRANT SELECT, INSERT ON control.outbox_events      TO dq_app_role;

REVOKE UPDATE, DELETE ON control.tenant_audit_logs FROM dq_app_role;
