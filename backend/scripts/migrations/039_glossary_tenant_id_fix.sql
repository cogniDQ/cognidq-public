-- Migration: 039_glossary_tenant_id_fix.sql
-- Feature: F131 — Phase A/B Critical Defect Remediation
-- Packet: P02 — Glossary tenant_id Migration and Fix
-- Created: 2026-04-23
-- BUG-004: control.metadata_term_index missing tenant_id column
-- Description:
--   Ensure tenant_id exists on control.metadata_term_index and backfill from
--   the workspace record. Migration 038 added this in its Part 3, but if 038
--   was partially rolled back (e.g. due to the workspace_connection_assignments
--   FK failure), this migration re-applies the missing column independently.
--
-- Idempotent: uses ADD COLUMN IF NOT EXISTS and IF NOT EXISTS for the index.

BEGIN;

ALTER TABLE control.metadata_term_index
    ADD COLUMN IF NOT EXISTS tenant_id UUID;

-- Backfill tenant_id from workspace record where possible.
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

CREATE INDEX IF NOT EXISTS ix_metadata_term_index_tenant_id
    ON control.metadata_term_index (tenant_id);

COMMIT;
