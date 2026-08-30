-- Migration: 038_tenant_connections_and_glossary.sql
-- Feature: F130 — Frontend Domain Migrations: Connections and Glossary
-- Packet: P01 — DB Migration
-- Created: 2026-04-23
-- Description:
--   Part 1: Add tenant_id to control.data_sources; backfill from workspaces.
--   Part 2: Create workspace_connection_assignments for many-to-many tenant↔workspace.
--   Part 3: Add tenant_id to control.metadata_term_index; backfill from workspaces.
--
-- Idempotent: all ALTER/CREATE use IF NOT EXISTS or ALTER TABLE ADD COLUMN IF NOT EXISTS.
-- Backward compatible: workspace_id columns are NOT removed.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 1: control.data_sources — add tenant_id
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.data_sources
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

-- Backfill tenant_id from workspace record.
-- Wrapped in DO block to gracefully handle missing columns.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema = 'control'
          AND  table_name   = 'workspaces'
          AND  column_name  = 'tenant_id'
    ) THEN
        UPDATE control.data_sources ds
        SET    tenant_id = w.tenant_id
        FROM   control.workspaces w
        WHERE  ds.workspace_id = w.workspace_id
          AND  ds.tenant_id IS NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_data_sources_tenant_id
    ON control.data_sources (tenant_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 2: workspace_connection_assignments — new table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.workspace_connection_assignments (
    connection_id  UUID         NOT NULL
                   REFERENCES control.data_sources (data_source_id) ON DELETE CASCADE,
    workspace_id   UUID         NOT NULL,
    assigned_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    assigned_by    UUID,
    PRIMARY KEY (connection_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS ix_wca_workspace
    ON control.workspace_connection_assignments (workspace_id);

CREATE INDEX IF NOT EXISTS ix_wca_connection
    ON control.workspace_connection_assignments (connection_id);

-- Backfill: existing workspace-scoped data sources get a self-assignment row.
INSERT INTO control.workspace_connection_assignments (connection_id, workspace_id)
SELECT data_source_id, workspace_id
FROM   control.data_sources
WHERE  workspace_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Part 3: control.metadata_term_index — add tenant_id
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.metadata_term_index
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

-- Backfill tenant_id from workspace record.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema = 'control'
          AND  table_name   = 'workspaces'
          AND  column_name  = 'tenant_id'
    ) THEN
        UPDATE control.metadata_term_index mti
        SET    tenant_id = w.tenant_id
        FROM   control.workspaces w
        WHERE  mti.workspace_id = w.workspace_id
          AND  mti.tenant_id IS NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_meta_term_tenant
    ON control.metadata_term_index (tenant_id);

COMMIT;
