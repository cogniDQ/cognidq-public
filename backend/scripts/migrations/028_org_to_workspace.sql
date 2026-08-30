-- Migration 028: Rename organization_id → workspace_id across all legacy tables
-- Transitions from the legacy `organizations` tenant model to `control.workspaces`.
--
-- Affected tables (14): dashboards, data_sources, domains, dq_flows, dq_rules,
-- ingestion_jobs, invitations, metrics_cache, organization_members,
-- report_executions, reports, roles, teams, user_role_assignments
BEGIN;

-- ============================================================
-- Step 1: Drop all FK constraints referencing organizations(id)
-- ============================================================
ALTER TABLE IF EXISTS organization_members DROP CONSTRAINT IF EXISTS organization_members_organization_id_fkey;
ALTER TABLE IF EXISTS invitations         DROP CONSTRAINT IF EXISTS invitations_organization_id_fkey;
ALTER TABLE IF EXISTS domains             DROP CONSTRAINT IF EXISTS domains_organization_id_fkey;
ALTER TABLE IF EXISTS teams               DROP CONSTRAINT IF EXISTS teams_organization_id_fkey;
ALTER TABLE IF EXISTS roles               DROP CONSTRAINT IF EXISTS roles_organization_id_fkey;
ALTER TABLE IF EXISTS user_role_assignments DROP CONSTRAINT IF EXISTS user_role_assignments_organization_id_fkey;
ALTER TABLE IF EXISTS data_sources        DROP CONSTRAINT IF EXISTS data_sources_organization_id_fkey;
ALTER TABLE IF EXISTS ingestion_jobs      DROP CONSTRAINT IF EXISTS ingestion_jobs_organization_id_fkey;
ALTER TABLE IF EXISTS dq_rules            DROP CONSTRAINT IF EXISTS dq_rules_organization_id_fkey;
ALTER TABLE IF EXISTS dq_flows            DROP CONSTRAINT IF EXISTS dq_flows_organization_id_fkey;
ALTER TABLE IF EXISTS dashboards          DROP CONSTRAINT IF EXISTS dashboards_organization_id_fkey;
ALTER TABLE IF EXISTS reports             DROP CONSTRAINT IF EXISTS reports_organization_id_fkey;
ALTER TABLE IF EXISTS report_executions   DROP CONSTRAINT IF EXISTS report_executions_organization_id_fkey;
ALTER TABLE IF EXISTS metrics_cache       DROP CONSTRAINT IF EXISTS metrics_cache_organization_id_fkey;

-- ============================================================
-- Step 2: Rename organization_id → workspace_id in all tables
-- ============================================================
ALTER TABLE IF EXISTS dashboards          RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS data_sources        RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS domains             RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS dq_flows            RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS dq_rules            RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS ingestion_jobs      RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS invitations         RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS metrics_cache       RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS organization_members RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS report_executions   RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS reports             RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS roles               RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS teams               RENAME COLUMN organization_id TO workspace_id;
ALTER TABLE IF EXISTS user_role_assignments RENAME COLUMN organization_id TO workspace_id;

-- ============================================================
-- Step 3: Migrate existing data — map legacy org ID to workspace ID
-- ============================================================
DO $do$ BEGIN IF to_regclass('public.dashboards') IS NOT NULL THEN UPDATE dashboards            SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.data_sources') IS NOT NULL THEN UPDATE data_sources          SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.domains') IS NOT NULL THEN UPDATE domains               SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.dq_flows') IS NOT NULL THEN UPDATE dq_flows              SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.dq_rules') IS NOT NULL THEN UPDATE dq_rules              SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.ingestion_jobs') IS NOT NULL THEN UPDATE ingestion_jobs        SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.invitations') IS NOT NULL THEN UPDATE invitations           SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.metrics_cache') IS NOT NULL THEN UPDATE metrics_cache         SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.organization_members') IS NOT NULL THEN UPDATE organization_members  SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.report_executions') IS NOT NULL THEN UPDATE report_executions     SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.reports') IS NOT NULL THEN UPDATE reports               SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.roles') IS NOT NULL THEN UPDATE roles                 SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.teams') IS NOT NULL THEN UPDATE teams                 SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;
DO $do$ BEGIN IF to_regclass('public.user_role_assignments') IS NOT NULL THEN UPDATE user_role_assignments  SET workspace_id = '00000000-0000-0000-0000-000000000020' WHERE workspace_id = '00000000-0000-0000-0000-000000000001'; END IF; END $do$;

-- ============================================================
-- Step 4: Rename indexes for clarity
-- ============================================================
ALTER INDEX IF EXISTS idx_dashboards_org           RENAME TO idx_dashboards_workspace;
ALTER INDEX IF EXISTS idx_datasources_org          RENAME TO idx_datasources_workspace;
ALTER INDEX IF EXISTS unique_datasource_name_per_org RENAME TO unique_datasource_name_per_workspace;
ALTER INDEX IF EXISTS domains_organization_id_slug_key RENAME TO domains_workspace_id_slug_key;
ALTER INDEX IF EXISTS idx_domains_org              RENAME TO idx_domains_workspace;
ALTER INDEX IF EXISTS idx_domains_slug             RENAME TO idx_domains_workspace_slug;
ALTER INDEX IF EXISTS idx_flows_org                RENAME TO idx_flows_workspace;
ALTER INDEX IF EXISTS idx_rules_organization       RENAME TO idx_rules_workspace;
ALTER INDEX IF EXISTS idx_ingestion_jobs_org        RENAME TO idx_ingestion_jobs_workspace;
ALTER INDEX IF EXISTS ix_invitations_org_email_pending RENAME TO ix_invitations_workspace_email_pending;
ALTER INDEX IF EXISTS idx_metrics_cache_org_key    RENAME TO idx_metrics_cache_workspace_key;
ALTER INDEX IF EXISTS idx_metrics_cache_org_type   RENAME TO idx_metrics_cache_workspace_type;
ALTER INDEX IF EXISTS idx_org_members_org          RENAME TO idx_workspace_members_workspace;
ALTER INDEX IF EXISTS ix_org_members_org_status    RENAME TO ix_workspace_members_status;
ALTER INDEX IF EXISTS organization_members_organization_id_user_id_key RENAME TO organization_members_workspace_id_user_id_key;
ALTER INDEX IF EXISTS idx_report_executions_org    RENAME TO idx_report_executions_workspace;
ALTER INDEX IF EXISTS idx_reports_org              RENAME TO idx_reports_workspace;
ALTER INDEX IF EXISTS idx_roles_org                RENAME TO idx_roles_workspace;
ALTER INDEX IF EXISTS roles_organization_id_name_key RENAME TO roles_workspace_id_name_key;
ALTER INDEX IF EXISTS idx_teams_org                RENAME TO idx_teams_workspace;
ALTER INDEX IF EXISTS idx_user_roles_org           RENAME TO idx_user_roles_workspace;
ALTER INDEX IF EXISTS user_role_assignments_user_id_role_id_organization_id_domai_key
    RENAME TO user_role_assignments_user_role_workspace_domain_team_key;

-- ============================================================
-- Step 5: Add FK constraints to control.workspaces(workspace_id)
-- ============================================================
ALTER TABLE IF EXISTS dashboards          ADD CONSTRAINT dashboards_workspace_id_fkey          FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS data_sources        ADD CONSTRAINT data_sources_workspace_id_fkey        FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS domains             ADD CONSTRAINT domains_workspace_id_fkey             FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS dq_flows            ADD CONSTRAINT dq_flows_workspace_id_fkey            FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS dq_rules            ADD CONSTRAINT dq_rules_workspace_id_fkey            FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS ingestion_jobs      ADD CONSTRAINT ingestion_jobs_workspace_id_fkey      FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS invitations         ADD CONSTRAINT invitations_workspace_id_fkey         FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS metrics_cache       ADD CONSTRAINT metrics_cache_workspace_id_fkey       FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS organization_members ADD CONSTRAINT organization_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS report_executions   ADD CONSTRAINT report_executions_workspace_id_fkey   FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS reports             ADD CONSTRAINT reports_workspace_id_fkey             FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS roles               ADD CONSTRAINT roles_workspace_id_fkey              FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id);
ALTER TABLE IF EXISTS teams               ADD CONSTRAINT teams_workspace_id_fkey              FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS user_role_assignments ADD CONSTRAINT user_role_assignments_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE;

COMMIT;
