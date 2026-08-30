-- Migration: 010_f005_datasets.sql
-- Feature: F005 — Dataset Registration and Schema
-- Packet: P01 — Database Schema and Migration
-- Created: 2026-04-01
-- Description:
--   Creates control.datasets (dataset registry) and control.dataset_fields
--   (column-level metadata) with all constraints, indexes, and FK references.
--
-- Tables created:
--   control.datasets         — dataset registry with metadata and lifecycle state
--   control.dataset_fields   — column-level field metadata per dataset

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Datasets table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE control.datasets (
    dataset_id            UUID          NOT NULL DEFAULT gen_random_uuid(),
    workspace_id          UUID          NOT NULL,
    tenant_id             UUID          NOT NULL,
    data_source_id        UUID          NOT NULL,
    dataset_name          VARCHAR(200)  NOT NULL,
    dataset_type          VARCHAR(20)   NOT NULL,
    physical_identifier   VARCHAR(500)  NOT NULL,
    schema_name           VARCHAR(200)  NULL,
    description           VARCHAR(1000) NULL,
    business_domain       VARCHAR(100)  NULL,
    criticality           VARCHAR(20)   NOT NULL DEFAULT 'low',
    owner_user_id         UUID          NULL,
    freshness_expectation VARCHAR(200)  NULL,
    status                VARCHAR(20)   NOT NULL DEFAULT 'draft',
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    created_by            UUID          NOT NULL,
    updated_by            UUID          NULL,
    activated_at          TIMESTAMPTZ   NULL,
    archived_at           TIMESTAMPTZ   NULL,
    archived_by           UUID          NULL,

    CONSTRAINT pk_datasets
        PRIMARY KEY (dataset_id),

    CONSTRAINT fk_datasets_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_datasets_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE NO ACTION,

    CONSTRAINT fk_datasets_data_source
        FOREIGN KEY (data_source_id)
        REFERENCES control.data_sources (data_source_id)
        ON DELETE RESTRICT,

    CONSTRAINT ck_datasets_dataset_type
        CHECK (dataset_type IN ('table', 'view', 'file', 'logical')),

    CONSTRAINT ck_datasets_criticality
        CHECK (criticality IN ('low', 'medium', 'high', 'critical')),

    CONSTRAINT ck_datasets_status
        CHECK (status IN ('draft', 'active', 'inactive', 'archived'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Indexes on datasets
-- ─────────────────────────────────────────────────────────────────────────────

-- Unique: case-insensitive dataset_name per workspace
CREATE UNIQUE INDEX uq_dataset_name_workspace
    ON control.datasets (workspace_id, lower(dataset_name));

-- Unique: case-insensitive physical_identifier per data source (excluding archived)
CREATE UNIQUE INDEX uq_dataset_physical_id_source
    ON control.datasets (data_source_id, lower(physical_identifier))
    WHERE status != 'archived';

-- Lookup indexes
CREATE INDEX idx_datasets_workspace       ON control.datasets (workspace_id);
CREATE INDEX idx_datasets_data_source     ON control.datasets (data_source_id);
CREATE INDEX idx_datasets_status          ON control.datasets (status);
CREATE INDEX idx_datasets_owner           ON control.datasets (owner_user_id);
CREATE INDEX idx_datasets_business_domain ON control.datasets (business_domain);
CREATE INDEX idx_datasets_criticality     ON control.datasets (criticality);
CREATE INDEX idx_datasets_tenant          ON control.datasets (tenant_id);
CREATE INDEX idx_datasets_type            ON control.datasets (dataset_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Dataset fields table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE control.dataset_fields (
    field_id                   UUID          NOT NULL DEFAULT gen_random_uuid(),
    dataset_id                 UUID          NOT NULL,
    field_name                 VARCHAR(200)  NOT NULL,
    data_type                  VARCHAR(100)  NOT NULL,
    nullable                   BOOLEAN       NOT NULL DEFAULT true,
    business_definition        VARCHAR(1000) NULL,
    sensitivity_classification VARCHAR(20)   NOT NULL DEFAULT 'internal',
    is_key_candidate           BOOLEAN       NOT NULL DEFAULT false,
    ordinal_position           INTEGER       NOT NULL,
    created_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT pk_dataset_fields
        PRIMARY KEY (field_id),

    CONSTRAINT fk_dataset_fields_dataset
        FOREIGN KEY (dataset_id)
        REFERENCES control.datasets (dataset_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_dataset_fields_sensitivity
        CHECK (sensitivity_classification IN ('public', 'internal', 'confidential', 'restricted'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Indexes on dataset_fields
-- ─────────────────────────────────────────────────────────────────────────────

-- Unique: case-insensitive field_name per dataset
CREATE UNIQUE INDEX uq_field_name_dataset
    ON control.dataset_fields (dataset_id, lower(field_name));

-- Lookup index
CREATE INDEX idx_dataset_fields_dataset
    ON control.dataset_fields (dataset_id);

COMMIT;
