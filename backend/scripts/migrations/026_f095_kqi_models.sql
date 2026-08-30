-- F095: KQI Dynamic Reports Engine
-- Migration 026: New tables for SLA definitions, cost models, KQI snapshots
-- Plus performance indexes on existing tables for KQI aggregation queries

BEGIN;

-- ============================================================
-- 1. SLA Definitions (workspace-scoped SLA target times)
-- ============================================================
CREATE TABLE IF NOT EXISTS sla_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES control.workspaces(workspace_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    severity_level VARCHAR(50) NOT NULL,
    target_hours FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sla_workspace_severity UNIQUE (workspace_id, severity_level)
);

CREATE INDEX ix_sla_definitions_workspace_id ON sla_definitions(workspace_id);

-- ============================================================
-- 2. Cost Models (org-scoped cost-per-incident configuration)
-- ============================================================
CREATE TABLE IF NOT EXISTS cost_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    severity VARCHAR(50) NOT NULL,
    estimated_cost_usd FLOAT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cost_model_org_severity UNIQUE (organization_id, severity)
);

CREATE INDEX ix_cost_models_organization_id ON cost_models(organization_id);

-- ============================================================
-- 3. KQI Snapshots (daily historical KQI values for trends)
-- ============================================================
CREATE TABLE IF NOT EXISTS kqi_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kqi_id VARCHAR(20) NOT NULL,
    value FLOAT NOT NULL,
    snapshot_date DATE NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kqi_snapshot_org_kqi_date UNIQUE (organization_id, kqi_id, snapshot_date)
);

CREATE INDEX ix_kqi_snapshots_org_date ON kqi_snapshots(organization_id, snapshot_date);
CREATE INDEX ix_kqi_snapshots_kqi_id ON kqi_snapshots(kqi_id);

-- ============================================================
-- 4. Performance indexes on existing tables
-- ============================================================

-- Speed up check result aggregation (node_type + created_at for time-bounded queries)
CREATE INDEX IF NOT EXISTS ix_flow_node_results_node_type_created
    ON flow_node_results(node_type, created_at);

-- Speed up JSONB result_data extraction (pass_rate, check_type, source_name)
CREATE INDEX IF NOT EXISTS ix_flow_node_results_result_data_gin
    ON flow_node_results USING GIN (result_data);

-- Speed up execution status queries for MTTR and success rate calculations
CREATE INDEX IF NOT EXISTS ix_flow_executions_flow_status_started
    ON flow_executions(flow_id, status, started_at);

COMMIT;
