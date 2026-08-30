-- =============================================================================
-- F052: Extend workspace_audit_logs for platform-wide immutable audit logging
-- =============================================================================
-- Adds actor_type, target_entity_type, target_entity_id columns.
-- Relaxes workspace_id and actor_id to nullable for tenant-level and
-- system-initiated actions respectively.
-- Adds composite index for entity-specific audit trail queries.
-- =============================================================================

-- 1. Add new columns
ALTER TABLE control.workspace_audit_logs
    ADD COLUMN IF NOT EXISTS actor_type VARCHAR(20) NOT NULL DEFAULT 'user',
    ADD COLUMN IF NOT EXISTS target_entity_type VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS target_entity_id UUID NULL;

-- 2. Relax workspace_id to nullable (tenant-level events have no workspace)
ALTER TABLE control.workspace_audit_logs
    ALTER COLUMN workspace_id DROP NOT NULL;

-- 3. Relax actor_id to nullable (system-initiated actions have no actor)
ALTER TABLE control.workspace_audit_logs
    ALTER COLUMN actor_id DROP NOT NULL;

-- 4. New composite index for entity-specific audit trail queries
CREATE INDEX IF NOT EXISTS ix_audit_target_entity
    ON control.workspace_audit_logs USING BTREE (target_entity_type, target_entity_id);

-- 5. Ensure dq_app_role permissions remain INSERT + SELECT only
GRANT INSERT, SELECT ON control.workspace_audit_logs TO dq_app_role;

-- =============================================================================
-- Down migration (manual rollback):
-- =============================================================================
-- DROP INDEX IF EXISTS control.ix_audit_target_entity;
-- ALTER TABLE control.workspace_audit_logs
--     ALTER COLUMN workspace_id SET NOT NULL,
--     ALTER COLUMN actor_id SET NOT NULL;
-- ALTER TABLE control.workspace_audit_logs
--     DROP COLUMN IF EXISTS target_entity_id,
--     DROP COLUMN IF EXISTS target_entity_type,
--     DROP COLUMN IF EXISTS actor_type;
