-- Migration 008: Flow Builder Tables
-- Description: Creates tables for visual flow builder, flow executions, and node results
-- Author: DataQuality.AI
-- Date: 2026-01-14

-- ==============================================
-- 1. DQ Flows Table
-- ==============================================
CREATE TABLE IF NOT EXISTS dq_flows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Flow definition (visual nodes + connections)
    flow_definition JSONB NOT NULL,
    -- Example structure:
    -- {
    --   "nodes": [
    --     { "id": "source-1", "type": "source", "config": {...}, "position": {"x": 100, "y": 100} },
    --     { "id": "check-1", "type": "check", "checkType": "completeness", "config": {...}, "position": {"x": 300, "y": 100} }
    --   ],
    --   "connections": [
    --     { "id": "conn-1", "from": "source-1", "to": "check-1", "fromPort": "output", "toPort": "input" }
    --   ]
    -- }
    
    status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'inactive', 'archived')),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Schedule for automatic execution (cron expression)
    schedule JSONB,
    -- Example: { "enabled": true, "cron": "0 2 * * *", "timezone": "UTC" }
    
    -- Metadata
    tags TEXT[],
    version INTEGER DEFAULT 1,
    
    -- Audit fields
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_flow_name_per_org UNIQUE (organization_id, name)
);

-- Indexes for dq_flows
CREATE INDEX idx_flows_org ON dq_flows(organization_id);
CREATE INDEX idx_flows_status ON dq_flows(status) WHERE is_active = TRUE;
CREATE INDEX idx_flows_created_by ON dq_flows(created_by);
CREATE INDEX idx_flows_created_at ON dq_flows(created_at DESC);
CREATE INDEX idx_flows_tags ON dq_flows USING GIN(tags);
CREATE INDEX idx_flows_definition ON dq_flows USING GIN(flow_definition);

-- ==============================================
-- 2. Flow Executions Table
-- ==============================================
CREATE TABLE IF NOT EXISTS flow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flow_id UUID NOT NULL REFERENCES dq_flows(id) ON DELETE CASCADE,
    execution_type VARCHAR(50) DEFAULT 'manual' CHECK (execution_type IN ('manual', 'scheduled', 'triggered', 'test')),
    
    -- Execution status
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    
    -- Execution metrics
    nodes_executed INTEGER DEFAULT 0,
    nodes_passed INTEGER DEFAULT 0,
    nodes_failed INTEGER DEFAULT 0,
    nodes_skipped INTEGER DEFAULT 0,
    
    -- Execution configuration
    execution_config JSONB,
    -- Example: { "sample_size": 1000, "parallel": true, "continue_on_error": false }
    
    -- Results summary
    result_summary JSONB,
    -- Example: {
    --   "total_rows_scanned": 10000,
    --   "total_violations": 50,
    --   "overall_pass_rate": 99.5,
    --   "node_results": {...}
    -- }
    
    error_message TEXT,
    error_details JSONB,
    
    -- Audit fields
    executed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for flow_executions
CREATE INDEX idx_flow_exec_flow ON flow_executions(flow_id);
CREATE INDEX idx_flow_exec_status ON flow_executions(status);
CREATE INDEX idx_flow_exec_type ON flow_executions(execution_type);
CREATE INDEX idx_flow_exec_started ON flow_executions(started_at DESC);
CREATE INDEX idx_flow_exec_user ON flow_executions(executed_by);
CREATE INDEX idx_flow_exec_summary ON flow_executions USING GIN(result_summary);

-- ==============================================
-- 3. Flow Node Results Table
-- ==============================================
CREATE TABLE IF NOT EXISTS flow_node_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL REFERENCES flow_executions(id) ON DELETE CASCADE,
     node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(50) NOT NULL,
    
    -- Node execution status
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'warning', 'failed', 'skipped')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    
    -- Node results
    result_data JSONB,
    -- Example for completeness check:
    -- {
    --   "rows_scanned": 1000,
    --   "rows_passed": 995,
    --   "rows_failed": 5,
    --   "pass_rate": 99.5,
    --   "violations": [...]
    -- }
    
    error_message TEXT,
    error_details JSONB,
    
    -- Execution order
    execution_order INTEGER,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_node_per_execution UNIQUE (execution_id, node_id)
);

-- Indexes for flow_node_results
CREATE INDEX idx_node_results_execution ON flow_node_results(execution_id);
CREATE INDEX idx_node_results_node_id ON flow_node_results(node_id);
CREATE INDEX idx_node_results_status ON flow_node_results(status);
CREATE INDEX idx_node_results_type ON flow_node_results(node_type);
CREATE INDEX idx_node_results_order ON flow_node_results(execution_id, execution_order);
CREATE INDEX idx_node_results_data ON flow_node_results USING GIN(result_data);

-- ==============================================
-- 4. Flow Templates Table (Optional)
-- ==============================================
CREATE TABLE IF NOT EXISTS flow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    
    -- Template flow definition
    template_definition JSONB NOT NULL,
    
    -- Preview image
    preview_image_url TEXT,
    
    -- Template metadata
    is_public BOOLEAN DEFAULT FALSE,
    use_count INTEGER DEFAULT 0,
    
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_template_name UNIQUE (name)
);

-- Indexes for flow_templates
CREATE INDEX idx_templates_category ON flow_templates(category);
CREATE INDEX idx_templates_public ON flow_templates(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_templates_use_count ON flow_templates(use_count DESC);

-- ==============================================
-- 5. Comments & Annotations (Optional)
-- ==============================================
COMMENT ON TABLE dq_flows IS 'Stores visual flow definitions for data quality checks';
COMMENT ON COLUMN dq_flows.flow_definition IS 'JSONB containing nodes and connections for the visual flow';
COMMENT ON COLUMN dq_flows.schedule IS 'Cron schedule configuration for automatic execution';

COMMENT ON TABLE flow_executions IS 'Records of flow executions with metrics and results';
COMMENT ON COLUMN flow_executions.result_summary IS 'Aggregated results from all nodes in the flow';

COMMENT ON TABLE flow_node_results IS 'Individual node execution results within a flow execution';
COMMENT ON COLUMN flow_node_results.result_data IS 'Node-specific execution results and metrics';

COMMENT ON TABLE flow_templates IS 'Pre-built flow templates for common data quality patterns';

-- ==============================================
-- 6. Migration Complete
-- ==============================================
-- Insert migration record (if you have a migrations tracking table)
-- INSERT INTO schema_migrations (version, description, executed_at)
-- VALUES ('008', 'Flow Builder Tables', NOW());
