-- Migration: 019_f038_incidents.sql
-- Feature:   F038 — Manual Incident Creation
-- Packet:    P01 — Database Schema and Migration
-- Description:
--   Creates the public.incidents table and public.incident_issues junction
--   table for manually-created incidents that group data-quality issues.
--
--   Key constraints:
--     CHECK (severity IN ('critical', 'major', 'minor', 'informational'))
--     CHECK (priority IN ('P1', 'P2', 'P3', 'P4'))
--     CHECK (status IN ('open', 'acknowledged', 'mitigated', 'resolved', 'closed'))
--     CHECK (char_length(title) BETWEEN 1 AND 500)
--     FK owner_id → users(id)              ON DELETE SET NULL
--     FK created_by_user_id → users(id)    ON DELETE SET NULL
--     FK incident_id → incidents(id)       ON DELETE CASCADE
--     FK issue_id → issues(id)             ON DELETE CASCADE
--
--   Safe to re-run: all DDL uses IF NOT EXISTS.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. public.incidents table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.incidents (

    -- Primary key
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant / workspace scope
    tenant_id           UUID            NOT NULL,
    workspace_id        UUID            NOT NULL,

    -- Content
    title               VARCHAR(500)    NOT NULL,
    severity            VARCHAR(30)     NOT NULL,
    priority            VARCHAR(10)     NOT NULL,
    status              VARCHAR(30)     NOT NULL DEFAULT 'open',
    impact_summary      TEXT            NULL,

    -- Ownership
    owner_id            UUID            NULL,
    created_by_user_id  UUID            NULL,

    -- Timestamps
    opened_at           TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT pk_incidents             PRIMARY KEY (id),
    CONSTRAINT fk_incidents_owner       FOREIGN KEY (owner_id)
                                        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_incidents_creator     FOREIGN KEY (created_by_user_id)
                                        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT ck_incidents_severity    CHECK (severity IN ('critical', 'major', 'minor', 'informational')),
    CONSTRAINT ck_incidents_priority    CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
    CONSTRAINT ck_incidents_status      CHECK (status IN ('open', 'acknowledged', 'mitigated', 'resolved', 'closed')),
    CONSTRAINT ck_incidents_title_length CHECK (char_length(title) BETWEEN 1 AND 500)
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_incidents_workspace ON public.incidents(workspace_id);
CREATE INDEX IF NOT EXISTS ix_incidents_status    ON public.incidents(workspace_id, status);

-- updated_at trigger (reuses set_updated_at() created by 013_f031_issues.sql)
DROP TRIGGER IF EXISTS trg_incidents_updated_at ON public.incidents;
CREATE TRIGGER trg_incidents_updated_at
    BEFORE UPDATE ON public.incidents
    FOR EACH ROW
    EXECUTE FUNCTION public.set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. public.incident_issues junction table
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.incident_issues (

    incident_id         UUID            NOT NULL,
    issue_id            UUID            NOT NULL,
    linked_at           TIMESTAMPTZ     NOT NULL DEFAULT now(),
    linked_by_user_id   UUID            NULL,

    CONSTRAINT pk_incident_issues       PRIMARY KEY (incident_id, issue_id),
    CONSTRAINT fk_incident_issues_incident
                                        FOREIGN KEY (incident_id)
                                        REFERENCES incidents(id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_issues_issue FOREIGN KEY (issue_id)
                                        REFERENCES issues(id) ON DELETE CASCADE,
    CONSTRAINT fk_incident_issues_linked_by
                                        FOREIGN KEY (linked_by_user_id)
                                        REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_incident_issues_issue ON public.incident_issues(issue_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Grants (conditional — only if role exists)
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app_role') THEN
        GRANT SELECT, INSERT, UPDATE ON public.incidents TO dq_app_role;
        GRANT SELECT, INSERT, DELETE ON public.incident_issues TO dq_app_role;
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- ROLLBACK instructions (manual):
--   DROP TRIGGER IF EXISTS trg_incidents_updated_at ON public.incidents;
--   DROP TABLE IF EXISTS public.incident_issues;
--   DROP TABLE IF EXISTS public.incidents;
-- ─────────────────────────────────────────────────────────────────────────────
