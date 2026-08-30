-- F060 — External Ticketing Integration Hooks
-- Migration 025
-- Adds external ticket reference columns to issues and incidents,
-- and a workspace-scoped ticketing integration config table.

BEGIN;

-- --------------------------------------------------------------------------
-- 1. External ticket reference columns on issues
-- --------------------------------------------------------------------------

ALTER TABLE public.issues
    ADD COLUMN IF NOT EXISTS external_ticket_id   VARCHAR(255),
    ADD COLUMN IF NOT EXISTS external_ticket_url  TEXT,
    ADD COLUMN IF NOT EXISTS external_system      VARCHAR(100);

-- --------------------------------------------------------------------------
-- 2. External ticket reference columns on incidents
-- --------------------------------------------------------------------------

ALTER TABLE public.incidents
    ADD COLUMN IF NOT EXISTS external_ticket_id   VARCHAR(255),
    ADD COLUMN IF NOT EXISTS external_ticket_url  TEXT,
    ADD COLUMN IF NOT EXISTS external_system      VARCHAR(100);

-- --------------------------------------------------------------------------
-- 3. Workspace ticketing integration config table
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.ticketing_integration_configs (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
    workspace_id        UUID        NOT NULL,
    tenant_id           UUID        NOT NULL,
    system_name         VARCHAR(100) NOT NULL,         -- e.g. "jira", "linear", "github", "servicenow"
    display_name        VARCHAR(255) NOT NULL,
    base_url            TEXT,                           -- e.g. https://mycompany.atlassian.net
    project_key         VARCHAR(100),                   -- e.g. DQ, INFRA
    default_issue_type  VARCHAR(100),                   -- e.g. Bug, Task
    enabled             BOOLEAN     NOT NULL DEFAULT true,
    config_json         JSONB,                          -- additional system-specific config (placeholder)
    created_by          UUID        NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_ticketing_integration_configs PRIMARY KEY (id),
    CONSTRAINT fk_tic_workspace FOREIGN KEY (workspace_id)
        REFERENCES control.workspaces (workspace_id) ON DELETE CASCADE,
    CONSTRAINT fk_tic_tenant FOREIGN KEY (tenant_id)
        REFERENCES control.tenants (tenant_id) ON DELETE CASCADE,
    CONSTRAINT uq_tic_workspace_system UNIQUE (workspace_id, system_name),
    CONSTRAINT ck_tic_system_name CHECK (
        system_name IN ('jira', 'linear', 'github', 'servicenow', 'pagerduty', 'custom')
    )
);

CREATE INDEX IF NOT EXISTS idx_tic_workspace
    ON public.ticketing_integration_configs (workspace_id);

-- --------------------------------------------------------------------------
-- 4. Trigger: auto-update updated_at on ticketing_integration_configs
-- --------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_tic_updated_at'
          AND tgrelid = 'public.ticketing_integration_configs'::regclass
    ) THEN
        CREATE TRIGGER trg_tic_updated_at
            BEFORE UPDATE ON public.ticketing_integration_configs
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;

COMMIT;
