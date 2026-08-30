-- Migration: 009_f004_data_sources.sql
-- Feature: F004 — Data Source Connection Management
-- Packet: P01 — Database Schema and Migration
-- Created: 2026-04-01
-- Description:
--   Creates control.data_source_credentials (encrypted credential vault) and
--   control.data_sources (data source registry) with all constraints, indexes,
--   and the circular FK resolved via ALTER TABLE after both tables exist.
--
-- Tables created:
--   control.data_source_credentials  — encrypted credential payloads
--   control.data_sources             — data source registry with metadata
--
-- Circular FK strategy:
--   1. Create data_source_credentials WITHOUT the FK to data_sources
--   2. Create data_sources WITH FK to data_source_credentials (credential_reference)
--   3. ALTER TABLE data_source_credentials ADD CONSTRAINT to reference data_sources

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Credential vault (no FK to data_sources yet — circular reference)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE control.data_source_credentials (
    credential_id       UUID          NOT NULL DEFAULT gen_random_uuid(),
    data_source_id      UUID          NOT NULL,
    source_type         VARCHAR(50)   NOT NULL,
    encrypted_payload   BYTEA         NOT NULL,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_by          UUID          NOT NULL,
    superseded_at       TIMESTAMPTZ   NULL,

    CONSTRAINT pk_data_source_credentials
        PRIMARY KEY (credential_id),

    CONSTRAINT ck_ds_credentials_source_type
        CHECK (source_type IN (
            'postgresql', 'mysql', 'mssql', 'oracle', 'snowflake', 'bigquery'
        ))
);

CREATE INDEX idx_ds_credentials_data_source
    ON control.data_source_credentials (data_source_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Data sources table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE control.data_sources (
    data_source_id      UUID          NOT NULL DEFAULT gen_random_uuid(),
    workspace_id        UUID          NOT NULL,
    tenant_id           UUID          NOT NULL,
    source_name         VARCHAR(100)  NOT NULL,
    source_type         VARCHAR(50)   NOT NULL,
    connection_mode     VARCHAR(20)   NOT NULL,
    environment         VARCHAR(20)   NOT NULL,
    description         VARCHAR(500)  NULL,
    credential_reference UUID         NULL,
    status              VARCHAR(20)   NOT NULL DEFAULT 'active',
    last_test_status    VARCHAR(20)   NOT NULL DEFAULT 'untested',
    last_tested_at      TIMESTAMPTZ   NULL,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_by          UUID          NOT NULL,
    updated_by          UUID          NULL,
    archived_at         TIMESTAMPTZ   NULL,
    archived_by         UUID          NULL,

    CONSTRAINT pk_data_sources
        PRIMARY KEY (data_source_id),

    CONSTRAINT fk_data_sources_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_data_sources_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE NO ACTION,

    CONSTRAINT fk_data_sources_credential
        FOREIGN KEY (credential_reference)
        REFERENCES control.data_source_credentials (credential_id)
        ON DELETE SET NULL,

    CONSTRAINT ck_data_sources_source_type
        CHECK (source_type IN (
            'postgresql', 'mysql', 'mssql', 'oracle', 'snowflake', 'bigquery'
        )),

    CONSTRAINT ck_data_sources_connection_mode
        CHECK (connection_mode IN ('direct', 'agent')),

    CONSTRAINT ck_data_sources_environment
        CHECK (environment IN ('development', 'staging', 'production')),

    CONSTRAINT ck_data_sources_status
        CHECK (status IN ('active', 'archived')),

    CONSTRAINT ck_data_sources_test_status
        CHECK (last_test_status IN ('untested', 'reachable', 'unreachable', 'test_failed'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Deferred FK: credentials → data_sources (resolves circular reference)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.data_source_credentials
    ADD CONSTRAINT fk_ds_credentials_data_source
        FOREIGN KEY (data_source_id)
        REFERENCES control.data_sources (data_source_id)
        ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Indexes on data_sources
-- ─────────────────────────────────────────────────────────────────────────────

-- Unique: case-insensitive source_name per workspace
CREATE UNIQUE INDEX uq_data_source_name_workspace
    ON control.data_sources (workspace_id, lower(source_name));

-- Lookup indexes
CREATE INDEX idx_data_sources_workspace
    ON control.data_sources (workspace_id);

CREATE INDEX idx_data_sources_tenant
    ON control.data_sources (tenant_id);

CREATE INDEX idx_data_sources_status
    ON control.data_sources (status);

CREATE INDEX idx_data_sources_source_type
    ON control.data_sources (source_type);

COMMIT;
