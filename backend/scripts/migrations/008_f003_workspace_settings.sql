-- Migration: 008_f003_workspace_settings.sql
-- Feature:   F003 — Workspace Default Policies
-- Packet:    P01 — Database Schema and Migration
-- Created:   2026-03-29
--
-- Description:
--   Adds the workspace_settings table (one row per workspace), a trigger that
--   auto-creates a default settings row whenever a new workspace is inserted,
--   and a retroactive seed that covers all workspaces created before this
--   migration runs.
--
--   Columns (9):
--     workspace_id           UUID  PK  FK → control.workspaces (CASCADE)
--     tenant_id              UUID  NOT NULL  FK → control.tenants (NO ACTION)
--     default_timezone       VARCHAR(100)  NOT NULL  DEFAULT 'UTC'
--     severity_policy        JSONB  NULL   (NULL = use built-in defaults in service layer)
--     sla_policy             JSONB  NULL   (NULL = use built-in defaults in service layer)
--     issue_grouping_policy  VARCHAR(30)  NOT NULL  DEFAULT 'one_per_execution'
--     naming_standards       JSONB  NULL   (NULL = no naming constraints)
--     updated_at             TIMESTAMPTZ  NOT NULL
--     updated_by             UUID  NULL    (NULL when created by system trigger)
--
--   Constraints:
--     PRIMARY KEY (workspace_id)
--     FOREIGN KEY (workspace_id) REFERENCES control.workspaces ON DELETE CASCADE
--     FOREIGN KEY (tenant_id) REFERENCES control.tenants ON DELETE NO ACTION
--     CHECK (issue_grouping_policy IN ('one_per_execution', 'one_per_rule', 'one_per_day'))
--     CHECK (CHAR_LENGTH(TRIM(default_timezone)) > 0)
--
--   Indexes:
--     pk_workspace_settings (workspace_id)   — PK — created inline
--     ix_workspace_settings_tenant_id        — B-tree on tenant_id
--
--   Trigger:
--     trg_workspace_settings_on_insert  AFTER INSERT ON control.workspaces
--     → fn_create_default_workspace_settings() creates a settings row for every
--       new workspace. ON CONFLICT DO NOTHING makes it safe to replay.
--
--   Application DB role: dq_app_role (NOLOGIN).
--     Receives INSERT + SELECT + UPDATE on workspace_settings.
--
--   Authoritative timezone note:
--     After workspace creation, workspace_settings.default_timezone is the
--     authoritative effective timezone. The workspaces.default_timezone column
--     (F002) is a creation-time snapshot and is NOT updated by F003.
--     Downstream features must query workspace_settings.default_timezone.


-- ────────────────────────────────────────────────────────────────────────────
-- 0. Prerequisites (idempotent)
-- ────────────────────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS control;


-- ────────────────────────────────────────────────────────────────────────────
-- 1. Table: control.workspace_settings  (9 columns)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.workspace_settings (
    workspace_id          UUID            NOT NULL,
    tenant_id             UUID            NOT NULL,
    -- IANA canonical timezone; updated via PATCH /workspaces/{id}/settings.
    -- workspaces.default_timezone is the creation-time snapshot; this column
    -- is the authoritative value for the workspace's current timezone.
    default_timezone      VARCHAR(100)    NOT NULL DEFAULT 'UTC',
    -- NULL means: use the built-in default labels in the service layer.
    -- {'critical_label': str, 'major_label': str, 'minor_label': str,
    --  'informational_label': str}
    severity_policy       JSONB           NULL,
    -- NULL means: use the built-in default SLA hours in the service layer.
    -- {'critical_hours': int, 'major_hours': int, 'minor_hours': int,
    --  'informational_hours': int|null}
    sla_policy            JSONB           NULL,
    -- One of: 'one_per_execution' | 'one_per_rule' | 'one_per_day'
    issue_grouping_policy VARCHAR(30)     NOT NULL DEFAULT 'one_per_execution',
    -- NULL means: no naming constraints apply for this workspace.
    -- {'datasets': {...}, 'rules': {...}}
    naming_standards      JSONB           NULL,
    -- Set on every write by the service layer; set to NOW() on trigger creation.
    updated_at            TIMESTAMPTZ     NOT NULL,
    -- NULL when the row was created automatically by the trigger
    -- (no explicit human actor). Set to the actor UUID on every PATCH.
    updated_by            UUID            NULL,

    -- Primary key
    CONSTRAINT pk_workspace_settings
        PRIMARY KEY (workspace_id),

    -- Workspace referential integrity — cascade delete so settings are removed
    -- when the workspace is deleted (consistent with append-only audit pattern;
    -- workspace deletion is a hard admin operation).
    CONSTRAINT fk_workspace_settings_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE CASCADE,

    -- Tenant referential integrity — no cascade; tenant deletion must go through
    -- the tenant archival workflow, not hard delete, so this is a safety guard.
    CONSTRAINT fk_workspace_settings_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE NO ACTION,

    -- Constrain the grouping mode to the three defined values.
    CONSTRAINT ck_workspace_settings_grouping_mode
        CHECK (issue_grouping_policy IN
               ('one_per_execution', 'one_per_rule', 'one_per_day')),

    -- Timezone must not be an empty or whitespace-only string.
    CONSTRAINT ck_workspace_settings_timezone_not_empty
        CHECK (CHAR_LENGTH(TRIM(default_timezone)) > 0)
);


-- ────────────────────────────────────────────────────────────────────────────
-- 2. Index
-- ────────────────────────────────────────────────────────────────────────────

-- B-tree on tenant_id to support Platform Operator queries that may filter
-- workspace settings by tenant without joining on workspaces.
CREATE INDEX IF NOT EXISTS ix_workspace_settings_tenant_id
    ON control.workspace_settings USING BTREE (tenant_id);


-- ────────────────────────────────────────────────────────────────────────────
-- 3. Trigger — auto-create default settings on workspace INSERT
-- ────────────────────────────────────────────────────────────────────────────

-- Trigger function: creates a default workspace_settings row for the workspace
-- just inserted into control.workspaces. Uses ON CONFLICT DO NOTHING so the
-- migration is idempotent and the trigger is safe to run on a replica seeded
-- with existing data.
--
-- The initial default_timezone is copied from the workspace row itself so the
-- two tables start in sync. All JSONB policy columns are NULL (service layer
-- fills in built-in defaults on read). updated_by is NULL because this is a
-- system-initiated creation, not an explicit user action.
CREATE OR REPLACE FUNCTION control.fn_create_default_workspace_settings()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO control.workspace_settings (
        workspace_id,
        tenant_id,
        default_timezone,
        issue_grouping_policy,
        updated_at,
        updated_by
    ) VALUES (
        NEW.workspace_id,
        NEW.tenant_id,
        NEW.default_timezone,
        'one_per_execution',
        NOW(),
        NULL
    )
    ON CONFLICT (workspace_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Register the trigger. DROP IF EXISTS + CREATE is safe here because:
-- (a) IF EXISTS guards idempotency if the migration is run a second time;
-- (b) OR REPLACE on the function above means re-runs update the function body.
DROP TRIGGER IF EXISTS trg_workspace_settings_on_insert
    ON control.workspaces;

CREATE TRIGGER trg_workspace_settings_on_insert
    AFTER INSERT ON control.workspaces
    FOR EACH ROW
    EXECUTE FUNCTION control.fn_create_default_workspace_settings();


-- ────────────────────────────────────────────────────────────────────────────
-- 4. Retroactive seed — default settings for all existing workspaces
-- ────────────────────────────────────────────────────────────────────────────

-- Insert a default settings row for every workspace that existed before this
-- migration was applied. The trigger only fires on NEW inserts, so workspaces
-- created by F002 (before this migration runs) need an explicit back-fill.
-- ON CONFLICT DO NOTHING makes this block safe to replay.
INSERT INTO control.workspace_settings (
    workspace_id,
    tenant_id,
    default_timezone,
    issue_grouping_policy,
    updated_at,
    updated_by
)
SELECT
    w.workspace_id,
    w.tenant_id,
    w.default_timezone,
    'one_per_execution',
    NOW(),
    NULL
FROM control.workspaces w
ON CONFLICT (workspace_id) DO NOTHING;


-- ────────────────────────────────────────────────────────────────────────────
-- 5. DB Role Grants
-- ────────────────────────────────────────────────────────────────────────────

-- The application connects as dq_app_role (or a role inheriting from it).
-- workspace_settings: INSERT + SELECT + UPDATE allowed.
-- DELETE is guarded by the FK CASCADE from workspaces (only fires on workspace
-- hard-delete, which is an admin-only operation not issued by the app layer).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        GRANT INSERT, SELECT, UPDATE ON control.workspace_settings TO dq_app_role;
    END IF;
END$$;


-- ════════════════════════════════════════════════════════════════════════════
-- DOWN MIGRATION
-- Reverses all changes from this migration in dependency-safe reverse order.
-- Every statement uses IF EXISTS to guarantee idempotency: a re-run after a
-- successful down-migration must produce no errors.
-- ════════════════════════════════════════════════════════════════════════════

/*  ── DOWN ──

-- 1. Revoke grants (no-op if role does not exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        REVOKE INSERT, SELECT, UPDATE ON control.workspace_settings FROM dq_app_role;
    END IF;
END$$;

-- 2. Drop trigger and trigger function
DROP TRIGGER IF EXISTS trg_workspace_settings_on_insert ON control.workspaces;
DROP FUNCTION IF EXISTS control.fn_create_default_workspace_settings();

-- 3. Drop index
DROP INDEX IF EXISTS control.ix_workspace_settings_tenant_id;

-- 4. Drop table (cascade drops pk_workspace_settings and FK backing indexes)
DROP TABLE IF EXISTS control.workspace_settings;

── END DOWN ── */
