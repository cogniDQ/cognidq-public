-- ============================================================================
-- Migration 051 — Add 'suspended' value to control.workspace_status_enum
-- ----------------------------------------------------------------------------
-- Purpose:
--   Enables tenant→workspace cascading lifecycle: when a tenant is suspended,
--   each of its active workspaces transitions to 'suspended'.  When the
--   tenant is reactivated, those workspaces transition back to 'active'.
--
--   Previously workspaces only had ('active', 'archived') statuses, so
--   tenant suspension could not be reflected on the workspace level.
-- ============================================================================

ALTER TYPE control.workspace_status_enum ADD VALUE IF NOT EXISTS 'suspended';
