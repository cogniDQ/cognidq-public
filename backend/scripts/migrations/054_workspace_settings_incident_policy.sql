-- Migration 054: Add incident_policy column to workspace_settings
-- The column was referenced by backend code but never created in the schema.

ALTER TABLE control.workspace_settings
  ADD COLUMN IF NOT EXISTS incident_policy JSONB DEFAULT NULL;
