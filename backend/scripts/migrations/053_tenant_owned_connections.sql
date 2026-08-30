-- Migration: 053_tenant_owned_connections.sql
-- Feature : Tenant-owned connections (decouple data_sources from a single workspace)
-- Created : 2026-05-07
-- Description:
--   Connections are owned by a tenant and granted to one or more workspaces via
--   control.workspace_connection_assignments. This migration:
--     1. Drops NOT NULL on control.data_sources.workspace_id.
--     2. Replaces the workspace-scoped unique-name index with a tenant-scoped one.
--     3. Backfills tenant_id (defensive — should already be filled by 038).
--     4. Sets workspace_id = NULL for rows that already have an assignment row
--        for that workspace (so the column purely becomes a legacy/primary-owner
--        hint and is no longer required). NOTE: We keep the value in place when
--        present to avoid breaking older list/get queries that still filter by
--        workspace_id; new tenant-level creates will leave it NULL.
--
-- Idempotent and reversible-friendly: only constraint loosening + index swap.

BEGIN;

-- 1. tenant_id must be present and indexed (covered by migration 038, defensive).
UPDATE control.data_sources ds
SET    tenant_id = w.tenant_id
FROM   control.workspaces w
WHERE  ds.tenant_id IS NULL
  AND  ds.workspace_id = w.workspace_id;

ALTER TABLE control.data_sources
    ALTER COLUMN tenant_id SET NOT NULL;

-- 2. Drop NOT NULL on workspace_id so connections can be tenant-owned.
ALTER TABLE control.data_sources
    ALTER COLUMN workspace_id DROP NOT NULL;

-- 3. Replace workspace-scoped unique name index with tenant-scoped one.
--    Connection names are now unique within a tenant (across all workspaces).
DROP INDEX IF EXISTS control.uq_data_source_name_workspace;

CREATE UNIQUE INDEX IF NOT EXISTS uq_data_source_name_tenant
    ON control.data_sources (tenant_id, lower(source_name));

-- 4. Ensure every connection has at least one assignment row representing
--    its existing workspace ownership (defensive — 038 already backfills).
INSERT INTO control.workspace_connection_assignments (connection_id, workspace_id, assigned_by)
SELECT ds.data_source_id, ds.workspace_id, ds.created_by
FROM   control.data_sources ds
WHERE  ds.workspace_id IS NOT NULL
ON CONFLICT DO NOTHING;

COMMIT;
