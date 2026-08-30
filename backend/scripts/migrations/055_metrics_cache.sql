-- Migration 055: Create the metrics_cache table.
-- The MetricsCache ORM model (app/models/dashboard.py) and KQI services
-- (coverage, operational, dataset_quality, check_effectiveness, incident_sla)
-- depend on this table for read-through caching of dashboard metrics.
-- It was missing from the schema, causing 500s on /metrics/overview and
-- /kqi/coverage/* endpoints with: relation "metrics_cache" does not exist.

BEGIN;

CREATE TABLE IF NOT EXISTS metrics_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE,
    metric_type     VARCHAR(100) NOT NULL,
    metric_key      VARCHAR(255),
    metric_value    JSONB NOT NULL,
    time_period     VARCHAR(50),
    calculated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_cache_workspace_type
    ON metrics_cache(workspace_id, metric_type);

CREATE INDEX IF NOT EXISTS idx_metrics_cache_workspace_key
    ON metrics_cache(workspace_id, metric_type, metric_key);

CREATE INDEX IF NOT EXISTS idx_metrics_cache_calculated_at
    ON metrics_cache(calculated_at);

COMMIT;
