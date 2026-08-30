-- F108: Metadata Connectors Framework
-- Tables for connector configuration and sync history

-- ── connector configurations ──
CREATE TABLE IF NOT EXISTS control.metadata_connector_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    connector_type  VARCHAR(50) NOT NULL,          -- glossary, catalog, lineage, schema, bi, etl
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    connection_config JSONB NOT NULL DEFAULT '{}',  -- host, port, api_key, etc.
    sync_mode       VARCHAR(20) NOT NULL DEFAULT 'hybrid'
                    CHECK (sync_mode IN ('real_time', 'scheduled', 'full', 'hybrid')),
    sync_schedule   VARCHAR(100),                   -- cron expression
    is_active       BOOLEAN NOT NULL DEFAULT true,
    trust_priority  INTEGER NOT NULL DEFAULT 50
                    CHECK (trust_priority BETWEEN 1 AND 100),
    last_sync_at      TIMESTAMPTZ,
    last_sync_status  VARCHAR(20),
    last_sync_error   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mcc_workspace
    ON control.metadata_connector_configs (workspace_id);
CREATE INDEX IF NOT EXISTS idx_mcc_active
    ON control.metadata_connector_configs (workspace_id, is_active)
    WHERE is_active = true;

-- ── sync history ──
CREATE TABLE IF NOT EXISTS control.metadata_connector_sync_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_config_id UUID NOT NULL
        REFERENCES control.metadata_connector_configs(id) ON DELETE CASCADE,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'success', 'failed')),
    assets_created      INTEGER NOT NULL DEFAULT 0,
    assets_updated      INTEGER NOT NULL DEFAULT 0,
    terms_created       INTEGER NOT NULL DEFAULT 0,
    terms_updated       INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mcsh_connector
    ON control.metadata_connector_sync_history (connector_config_id);
CREATE INDEX IF NOT EXISTS idx_mcsh_started
    ON control.metadata_connector_sync_history (started_at DESC);
