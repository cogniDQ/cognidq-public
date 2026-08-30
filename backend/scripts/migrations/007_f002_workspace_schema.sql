-- Migration: 007_f002_workspace_schema.sql
-- Feature:   F002 — Workspace Creation and Archival
-- Packet:    P01 — Database Schema and Migration
-- Created:   2026-03-27
--
-- Description:
--   Establishes the complete control-plane PostgreSQL schema for F002:
--   the workspace_status_enum type, the workspaces table (14 columns),
--   the workspace_audit_logs table (11 columns), all inline constraints,
--   all 12 indexes per TDD §11.2, and DB role grants.
--
-- workspace_name_lower convention (HA-2 / TDD §3.1.1):
--   Unlike F001's tenant_name_lower (which uses GENERATED ALWAYS AS STORED),
--   this column is a plain VARCHAR managed entirely by the application service
--   layer. The packet plan explicitly excludes GENERATED ALWAYS AS syntax for
--   this feature. Application code must always set this column to
--   LOWER(TRIM(nfc_normalize(workspace_name))) before any INSERT or UPDATE.
--
-- pg_trgm schema (HA-2):
--   The pg_trgm extension is installed into the 'public' schema (PostgreSQL
--   default), consistent with migration 006. The GIN indexes on workspace_name
--   and workspace_slug reference gin_trgm_ops operators from the public schema.
--   If the application search_path does not include 'public', the schema must
--   be added or the extension reinstalled with an explicit schema qualifier.
--   Current dev and CI environments include 'public' in search_path.
--
-- Application DB role: dq_app_role (NOLOGIN). Created in migration 006.
--   Receives INSERT+SELECT+UPDATE on workspaces;
--   receives INSERT+SELECT ONLY on workspace_audit_logs (no UPDATE, no DELETE).
--
-- ck_status_reason_on_archived divergence note (EC-1):
--   PostgreSQL TRIM() removes only ASCII space (0x20). The application layer
--   uses Unicode-aware trimming and is more restrictive. The DB constraint is
--   the last-resort safety net; the application rejects non-compliant values
--   before this constraint fires in normal operation.


-- ────────────────────────────────────────────────────────────────────────────
-- 0. Prerequisites
-- ────────────────────────────────────────────────────────────────────────────

-- Ensure the control schema exists (idempotent; created in migration 006).
CREATE SCHEMA IF NOT EXISTS control;

-- Ensure pg_trgm is enabled (idempotent; likely installed in migration 006).
-- Required before GIN trigram indexes can be created (TDD §15 item 3).
-- Fails loudly if the extension cannot be enabled (TG-1).
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ────────────────────────────────────────────────────────────────────────────
-- 1. Enum Type: workspace_status_enum
-- ────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'workspace_status_enum'
          AND n.nspname = 'control'
    ) THEN
        CREATE TYPE control.workspace_status_enum AS ENUM (
            'active',
            'archived'
        );
    END IF;
END$$;


-- ────────────────────────────────────────────────────────────────────────────
-- 2. Table: control.workspaces  (14 columns)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.workspaces (
    workspace_id        UUID                            NOT NULL,
    tenant_id           UUID                            NOT NULL,
    workspace_name      VARCHAR(150)                    NOT NULL,
    -- Application-managed: stored as LOWER(TRIM(nfc_normalize(workspace_name))).
    -- Never set by triggers; never exposed in API responses.
    -- Application code must populate this before every INSERT/UPDATE.
    workspace_name_lower VARCHAR(150)                   NOT NULL,
    -- Immutable after creation; stored lowercase; validated [a-z0-9-] by service.
    workspace_slug      VARCHAR(80)                     NOT NULL,
    description         VARCHAR(500)                    NULL,
    -- Any IANA canonical timezone identifier; service normalises deprecated links.
    default_timezone    VARCHAR(100)                    NOT NULL DEFAULT 'UTC',
    -- System-managed; never accepted from API caller.
    status              control.workspace_status_enum   NOT NULL DEFAULT 'active',
    -- Required for archival (min 10 chars after trim); cleared to NULL on restore.
    status_reason       VARCHAR(500)                    NULL,
    -- Set by service at creation/mutation; no DB-level default (service-managed).
    created_at          TIMESTAMPTZ                     NOT NULL,
    updated_at          TIMESTAMPTZ                     NOT NULL,
    created_by          UUID                            NOT NULL,
    updated_by          UUID                            NOT NULL,
    -- Optimistic-locking counter; incremented by service on every successful write.
    version             INTEGER                         NOT NULL DEFAULT 0,

    -- Primary key
    CONSTRAINT pk_workspaces
        PRIMARY KEY (workspace_id),

    -- Case-insensitive workspace name uniqueness within a Tenant (all statuses)
    CONSTRAINT uq_workspaces_name_lower_per_tenant
        UNIQUE (tenant_id, workspace_name_lower),

    -- Slug uniqueness within a Tenant (all statuses)
    CONSTRAINT uq_workspaces_slug_per_tenant
        UNIQUE (tenant_id, workspace_slug),

    -- Tenant referential integrity; no cascade delete
    CONSTRAINT fk_workspaces_tenant_id
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE NO ACTION,

    -- Archived workspace must carry a non-trivial status_reason.
    -- EC-1: PostgreSQL TRIM() is ASCII-space only (0x20). Application layer is
    -- more restrictive (Unicode-aware trim). This constraint is the DB-level
    -- last resort; application rejects non-compliant values before this fires.
    CONSTRAINT ck_status_reason_on_archived
        CHECK (
            status != 'archived'
            OR (
                status_reason IS NOT NULL
                AND CHAR_LENGTH(TRIM(status_reason)) >= 10
            )
        ),

    -- Prevent negative version numbers (HA-5 / MV-4).
    CONSTRAINT ck_version_non_negative
        CHECK (version >= 0)
);


-- ────────────────────────────────────────────────────────────────────────────
-- 3. Table: control.workspace_audit_logs  (11 columns)
-- Append-only: no UPDATE or DELETE is ever issued by the application.
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.workspace_audit_logs (
    log_id          UUID            NOT NULL,
    tenant_id       UUID            NOT NULL,
    workspace_id    UUID            NOT NULL,
    -- One of: workspace_created | workspace_metadata_updated |
    --         workspace_archived | workspace_restored
    action_type     VARCHAR(50)     NOT NULL,
    actor_id        UUID            NOT NULL,
    actor_role      VARCHAR(50)     NOT NULL,
    -- NULL for workspace_created events (no prior state).
    previous_data   JSONB           NULL,
    -- Full fields snapshot on create; only changed fields on update/archive/restore.
    new_data        JSONB           NOT NULL,
    occurred_at     TIMESTAMPTZ     NOT NULL,
    -- Correlation ID from the originating HTTP request; NULL for internal ops.
    request_id      UUID            NULL,
    -- Client IP; NULL for service-account operations without a client address.
    source_ip       VARCHAR(45)     NULL,

    -- Primary key
    CONSTRAINT pk_workspace_audit_logs
        PRIMARY KEY (log_id),

    -- Workspace referential integrity; no cascade delete
    CONSTRAINT fk_audit_logs_workspace_id
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE NO ACTION,

    -- Tenant referential integrity; no cascade delete
    CONSTRAINT fk_audit_logs_tenant_id
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE NO ACTION
);


-- ────────────────────────────────────────────────────────────────────────────
-- 4. Indexes on control.workspaces
--    pk_workspaces, uq_workspaces_name_lower_per_tenant, and
--    uq_workspaces_slug_per_tenant are already created as inline constraints above.
--    The remaining 4 explicit indexes follow.
-- ────────────────────────────────────────────────────────────────────────────

-- Covers the primary list query: tenant-scoped, filtered by status, sorted by creation date.
CREATE INDEX IF NOT EXISTS ix_workspaces_tenant_status_created_at
    ON control.workspaces USING BTREE (tenant_id, status, created_at);

-- Covers list query sorted by last update date.
CREATE INDEX IF NOT EXISTS ix_workspaces_tenant_status_updated_at
    ON control.workspaces USING BTREE (tenant_id, status, updated_at);

-- Accelerates ILIKE '%term%' name search (requires pg_trgm).
CREATE INDEX IF NOT EXISTS ix_workspaces_name_trgm
    ON control.workspaces USING GIN (workspace_name gin_trgm_ops);

-- Accelerates ILIKE '%term%' slug search (requires pg_trgm).
CREATE INDEX IF NOT EXISTS ix_workspaces_slug_trgm
    ON control.workspaces USING GIN (workspace_slug gin_trgm_ops);


-- ────────────────────────────────────────────────────────────────────────────
-- 5. Indexes on control.workspace_audit_logs
--    pk_workspace_audit_logs already created as an inline constraint above.
--    The remaining 4 explicit indexes follow.
-- ────────────────────────────────────────────────────────────────────────────

-- Workspace-scoped audit log listing ordered by descending occurrence time.
CREATE INDEX IF NOT EXISTS ix_audit_logs_workspace_occurred_at
    ON control.workspace_audit_logs USING BTREE (workspace_id, occurred_at DESC);

-- Tenant-scoped audit queries (Platform Operator use).
-- NOTE: TDD §11.2 names this ix_audit_logs_tenant_occurred_at, but that name is
-- already used by F001 for tenant_audit_logs (PostgreSQL index names are
-- schema-wide unique). Using ix_ws_audit_logs_tenant_occurred_at instead.
-- This divergence is flagged in the implementation record.
CREATE INDEX IF NOT EXISTS ix_ws_audit_logs_tenant_occurred_at
    ON control.workspace_audit_logs USING BTREE (tenant_id, occurred_at DESC);

-- Filter audit logs by action type.
CREATE INDEX IF NOT EXISTS ix_audit_logs_action_type
    ON control.workspace_audit_logs USING BTREE (action_type);

-- Filter audit logs by actor.
-- NOTE: TDD §11.2 names this ix_audit_logs_actor_id, but that name is already
-- used by F001 for tenant_audit_logs. Using ix_ws_audit_logs_actor_id instead.
CREATE INDEX IF NOT EXISTS ix_ws_audit_logs_actor_id
    ON control.workspace_audit_logs USING BTREE (actor_id);


-- ────────────────────────────────────────────────────────────────────────────
-- 6. DB Role Grants
-- ────────────────────────────────────────────────────────────────────────────

-- The application connects as dq_app_role (or a role inheriting from it).
-- workspaces: INSERT + SELECT + UPDATE allowed; DELETE is never issued by application code.
-- workspace_audit_logs: INSERT + SELECT only; no UPDATE or DELETE (append-only enforcement).

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        GRANT INSERT, SELECT, UPDATE ON control.workspaces TO dq_app_role;
        GRANT INSERT, SELECT         ON control.workspace_audit_logs TO dq_app_role;
    END IF;
END$$;


-- ════════════════════════════════════════════════════════════════════════════
-- DOWN MIGRATION
-- Reverses all changes from this migration in dependency-safe reverse order.
-- Every statement uses IF EXISTS to guarantee idempotency: a re-run after a
-- successful down-migration must produce no errors (TG-1).
-- NOTE: pg_trgm is NOT dropped — it may be shared by other features.
-- ════════════════════════════════════════════════════════════════════════════

-- To execute the down-migration, run the block below manually or via a
-- migration runner that supports reversible migrations.

/*  ── DOWN ──

-- 1. Revoke grants (no-op if role does not exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        REVOKE INSERT, SELECT, UPDATE ON control.workspaces         FROM dq_app_role;
        REVOKE INSERT, SELECT         ON control.workspace_audit_logs FROM dq_app_role;
    END IF;
END$$;

-- 2. Drop indexes on workspace_audit_logs
DROP INDEX IF EXISTS control.ix_ws_audit_logs_actor_id;
DROP INDEX IF EXISTS control.ix_audit_logs_action_type;
DROP INDEX IF EXISTS control.ix_ws_audit_logs_tenant_occurred_at;
DROP INDEX IF EXISTS control.ix_audit_logs_workspace_occurred_at;

-- 3. Drop indexes on workspaces
DROP INDEX IF EXISTS control.ix_workspaces_slug_trgm;
DROP INDEX IF EXISTS control.ix_workspaces_name_trgm;
DROP INDEX IF EXISTS control.ix_workspaces_tenant_status_updated_at;
DROP INDEX IF EXISTS control.ix_workspaces_tenant_status_created_at;

-- 4. Drop tables (cascade drops inline constraints and their backing indexes)
DROP TABLE IF EXISTS control.workspace_audit_logs;
DROP TABLE IF EXISTS control.workspaces;

-- 5. Drop enum type
DROP TYPE IF EXISTS control.workspace_status_enum;

── END DOWN ── */
