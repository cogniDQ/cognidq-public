-- Migration: 013_f031_issues.sql
-- Feature:   F031 — Automatic Issue Creation
-- Packet:    P01 — Database Schema and Migration
-- Created:   2026-03-30
-- Description:
--   Creates the public.issues table which stores data quality issues
--   automatically generated when a check node fails during flow execution.
--
--   Issue severity is the issue-domain enum (critical/major/minor/informational).
--   Mapping from DQRule.severity to issue severity is handled in the service layer
--   (P03: IssueCreationService). See OTQ-001 in TDD for workspace_id resolution.
--
--   Key constraints:
--     CHECK (issue_type IN ('threshold_breach', 'execution_error'))
--     CHECK (severity IN ('critical', 'major', 'minor', 'informational'))
--     CHECK (status IN ('open', 'in_progress', 'resolved', 'closed', 'reopened'))
--     FK workspace_id → control.workspaces(workspace_id)   ON DELETE CASCADE
--     FK flow_execution_id → flow_executions(id)           ON DELETE CASCADE
--     FK flow_node_result_id → flow_node_results(id)       ON DELETE SET NULL
--     FK rule_id → dq_rules(id)                            ON DELETE SET NULL
--     FK dataset_id → control.datasets(dataset_id)         ON DELETE SET NULL
--     FK assignee_id → users(id)                           ON DELETE SET NULL
--
--   Safe to re-run: all DDL uses CREATE OR REPLACE / IF NOT EXISTS.
--   No existing tables are modified.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. set_updated_at() trigger function
--    Reused across tables; created here because no prior migration defines it.
--    CREATE OR REPLACE is idempotent: safe if the function already exists.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Create public.issues table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.issues (

    -- Primary key
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),

    -- Workspace scope (denormalized for partitioning + efficient workspace-scoped queries)
    workspace_id        UUID            NOT NULL,

    -- Tenant scope (denormalized alongside workspace_id for multi-tenant row security)
    tenant_id           UUID            NOT NULL,

    -- Source: the flow execution that produced this issue
    flow_execution_id   UUID            NOT NULL,

    -- Source: the specific node result that triggered the issue (nullable for
    -- execution-level errors where no single node result is the direct cause)
    flow_node_result_id UUID            NULL,

    -- Rule that defines the check (nullable; a node may not have an explicit rule)
    rule_id             UUID            NULL,

    -- Dataset the check ran against (nullable; may be absent for execution errors)
    dataset_id          UUID            NULL,

    -- User assigned to resolve this issue (nullable; auto-created issues are unassigned)
    assignee_id         UUID            NULL,

    -- Issue classification
    issue_type          VARCHAR(50)     NOT NULL,   -- 'threshold_breach' | 'execution_error'
    severity            VARCHAR(30)     NOT NULL,   -- 'critical' | 'major' | 'minor' | 'informational'
    status              VARCHAR(30)     NOT NULL DEFAULT 'open',

    -- Human-readable summary
    title               VARCHAR(500)    NOT NULL,

    -- Computed narrative: "150 of 1000 rows failed (85.0% pass rate)"
    impact_summary      TEXT            NULL,

    -- Numeric metrics captured at issue creation time
    failure_count       INTEGER         NULL,
    rows_scanned        INTEGER         NULL,
    pass_rate           DECIMAL(5, 2)   NULL,       -- percentage, e.g. 85.00

    -- SLA tracking
    due_at              TIMESTAMPTZ     NULL,       -- NULL when no SLA policy applies

    -- Lifecycle timestamps
    opened_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ     NULL,
    closed_at           TIMESTAMPTZ     NULL,

    -- Audit fields
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ────────── PRIMARY KEY ──────────
    CONSTRAINT pk_issues
        PRIMARY KEY (id),

    -- ────────── FOREIGN KEYS ──────────

    CONSTRAINT fk_issues_workspace
        FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issues_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issues_flow_execution
        FOREIGN KEY (flow_execution_id)
        REFERENCES public.flow_executions (id)
        ON DELETE CASCADE,

    CONSTRAINT fk_issues_flow_node_result
        FOREIGN KEY (flow_node_result_id)
        REFERENCES public.flow_node_results (id)
        ON DELETE SET NULL,

    CONSTRAINT fk_issues_rule
        FOREIGN KEY (rule_id)
        REFERENCES public.dq_rules (id)
        ON DELETE SET NULL,

    CONSTRAINT fk_issues_dataset
        FOREIGN KEY (dataset_id)
        REFERENCES control.datasets (dataset_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_issues_assignee
        FOREIGN KEY (assignee_id)
        REFERENCES public.users (id)
        ON DELETE SET NULL,

    -- ────────── CHECK CONSTRAINTS ──────────

    CONSTRAINT ck_issues_issue_type
        CHECK (issue_type IN ('threshold_breach', 'execution_error')),

    CONSTRAINT ck_issues_severity
        CHECK (severity IN ('critical', 'major', 'minor', 'informational')),

    CONSTRAINT ck_issues_status
        CHECK (status IN ('open', 'in_progress', 'resolved', 'closed', 'reopened')),

    -- pass_rate must be in [0, 100] when not null
    CONSTRAINT ck_issues_pass_rate
        CHECK (pass_rate IS NULL OR (pass_rate >= 0 AND pass_rate <= 100)),

    -- failure_count must be non-negative when not null
    CONSTRAINT ck_issues_failure_count
        CHECK (failure_count IS NULL OR failure_count >= 0),

    -- resolved_at must come after opened_at
    CONSTRAINT ck_issues_resolved_after_opened
        CHECK (resolved_at IS NULL OR resolved_at >= opened_at),

    -- closed_at must come after opened_at
    CONSTRAINT ck_issues_closed_after_opened
        CHECK (closed_at IS NULL OR closed_at >= opened_at)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Indexes
-- ─────────────────────────────────────────────────────────────────────────────

-- Primary workspace-scoped query pattern: list all issues for a workspace,
-- ordered by opened_at DESC. This is the hot path for the list API.
CREATE INDEX IF NOT EXISTS idx_issues_workspace_opened
    ON public.issues (workspace_id, opened_at DESC);

-- Filter by workspace + status (e.g., open issues dashboard)
CREATE INDEX IF NOT EXISTS idx_issues_workspace_status
    ON public.issues (workspace_id, status);

-- Filter by workspace + severity (e.g., critical issues list)
CREATE INDEX IF NOT EXISTS idx_issues_workspace_severity
    ON public.issues (workspace_id, severity);

-- Trace all issues produced by a specific flow execution
CREATE INDEX IF NOT EXISTS idx_issues_flow_execution
    ON public.issues (flow_execution_id);

-- Trace all issues linked to a specific rule (rule-level health)
CREATE INDEX IF NOT EXISTS idx_issues_rule
    ON public.issues (rule_id)
    WHERE rule_id IS NOT NULL;

-- Trace all issues for a specific dataset (dataset-level health)
CREATE INDEX IF NOT EXISTS idx_issues_dataset
    ON public.issues (dataset_id)
    WHERE dataset_id IS NOT NULL;

-- All issues assigned to a user (my work queue)
CREATE INDEX IF NOT EXISTS idx_issues_assignee
    ON public.issues (assignee_id)
    WHERE assignee_id IS NOT NULL;

-- SLA breach detection: find issues with due_at in the past and status = 'open'
CREATE INDEX IF NOT EXISTS idx_issues_due_at
    ON public.issues (due_at)
    WHERE due_at IS NOT NULL AND status IN ('open', 'in_progress');

-- Unique constraint: one issue per (workspace, flow_node_result) — prevents
-- duplicate issue creation if the hook is accidentally invoked twice for the
-- same node result. Non-unique when flow_node_result_id IS NULL (execution errors).
CREATE UNIQUE INDEX IF NOT EXISTS uq_issues_node_result
    ON public.issues (flow_node_result_id)
    WHERE flow_node_result_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. updated_at trigger
-- ─────────────────────────────────────────────────────────────────────────────

DROP TRIGGER IF EXISTS issues_set_updated_at ON public.issues;

CREATE TRIGGER issues_set_updated_at
    BEFORE UPDATE ON public.issues
    FOR EACH ROW
    EXECUTE FUNCTION public.set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Grant permissions to application role
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role'
    ) THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE
                 ON public.issues
                 TO dq_app_role';
    END IF;
END;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Rollback instructions (manual, not executed here)
-- ─────────────────────────────────────────────────────────────────────────────
-- To roll back:
--   DROP TRIGGER IF EXISTS issues_set_updated_at ON public.issues;
--   DROP INDEX IF EXISTS uq_issues_node_result;
--   DROP INDEX IF EXISTS idx_issues_due_at;
--   DROP INDEX IF EXISTS idx_issues_assignee;
--   DROP INDEX IF EXISTS idx_issues_dataset;
--   DROP INDEX IF EXISTS idx_issues_rule;
--   DROP INDEX IF EXISTS idx_issues_flow_execution;
--   DROP INDEX IF EXISTS idx_issues_workspace_severity;
--   DROP INDEX IF EXISTS idx_issues_workspace_status;
--   DROP INDEX IF EXISTS idx_issues_workspace_opened;
--   DROP TABLE IF EXISTS public.issues;
--   -- Do NOT drop public.set_updated_at() — it may be shared by future tables.

COMMIT;
