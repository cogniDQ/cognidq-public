-- Migration 007: DQ Rules, Executions, and Violations
-- Created: 2026-01-13
-- Description: Core rule engine tables for data quality rule management, execution tracking, and violation storage

-- Drop existing tables if they exist (for clean migration)
DROP TABLE IF EXISTS rule_violations CASCADE;
DROP TABLE IF EXISTS rule_executions CASCADE;
DROP TABLE IF EXISTS dq_rules CASCADE;

-- DQ Rules Table
-- Stores data quality rule definitions with canonical representation and compiled SQL/Spark
CREATE TABLE dq_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50), -- completeness, validity, conformity, uniqueness, consistency, accuracy, timeliness, statistical, reconciliation
    rule_type VARCHAR(50), -- null_check, regex_check, range_check, unique_check, etc.
    
    -- Canonical rule definition (platform-agnostic JSON structure)
    canonical_rule JSONB NOT NULL,
    -- Example structure:
    -- {
    --   "dimension": "completeness",
    --   "entity": "customers.email",
    --   "condition": "IS NOT NULL",
    --   "expectation": "100%",
    --   "severity": "blocker",
    --   "parameters": {...}
    -- }
    
    -- Compiled SQL for different database engines
    compiled_sql TEXT, -- Generic SQL
    compiled_postgres TEXT, -- PostgreSQL-specific
    compiled_mysql TEXT, -- MySQL-specific
    compiled_snowflake TEXT, -- Snowflake-specific
    compiled_spark TEXT, -- PySpark code
    
    -- Target configuration
    data_source_id UUID REFERENCES data_sources(id) ON DELETE SET NULL,
    target_schema VARCHAR(255),
    target_table VARCHAR(255),
    target_columns TEXT[], -- Array of column names
    
    -- Rule status and activation
    status VARCHAR(50) DEFAULT 'draft', -- draft, active, inactive, archived
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Scheduling (cron expression for recurring executions)
    schedule JSONB, -- { "cron": "0 0 * * *", "timezone": "UTC" }
    
    -- Thresholds and configuration
    threshold_config JSONB, -- Pass/fail thresholds, warning levels
    notification_config JSONB, -- Who to notify on failures
    
    -- Metadata
    tags TEXT[], -- For categorization and filtering
    meta_data JSONB, -- Custom metadata
    
    -- Audit fields
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('draft', 'active', 'inactive', 'archived')),
    CONSTRAINT valid_category CHECK (category IN ('completeness', 'validity', 'conformity', 'uniqueness', 'consistency', 'accuracy', 'timeliness', 'statistical', 'reconciliation'))
);

-- Rule Executions Table
-- Tracks each execution of a rule with results and metrics
CREATE TABLE rule_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES dq_rules(id) ON DELETE CASCADE,
    execution_type VARCHAR(50) NOT NULL, -- manual, scheduled, triggered, test
    
    -- Execution status
    status VARCHAR(50) DEFAULT 'pending', -- pending, running, completed, failed, cancelled
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    
    -- Execution results
    rows_scanned BIGINT DEFAULT 0,
    rows_passed BIGINT DEFAULT 0,
    rows_failed BIGINT DEFAULT 0,
    pass_rate DECIMAL(5,2), -- Percentage (0.00 - 100.00)
    
    -- Error handling
    error_message TEXT,
    error_details JSONB, -- Stack trace, error code, etc.
    
    -- Detailed results
    result_details JSONB,
    -- Example structure:
    -- {
    --   "total_rows": 10000,
    --   "passed": 9950,
    --   "failed": 50,
    --   "pass_rate": 99.50,
    --   "violation_count": 50,
    --   "sample_violations": [...],
    --   "statistics": {...}
    -- }
    
    -- Execution metadata
    execution_params JSONB, -- Parameters used for this execution
    environment JSONB, -- Environment info (engine version, cluster info, etc.)
    
    -- Audit fields
    executed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_execution_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    CONSTRAINT valid_execution_type CHECK (execution_type IN ('manual', 'scheduled', 'triggered', 'test'))
);

-- Rule Violations Table
-- Stores individual row violations from rule executions
CREATE TABLE rule_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL REFERENCES rule_executions(id) ON DELETE CASCADE,
    
    -- Violation identification
    row_identifier TEXT, -- Primary key or unique row identifier
    row_number BIGINT, -- Row number in dataset
    
    -- Violation details
    violation_details JSONB NOT NULL,
    -- Example structure:
    -- {
    --   "column": "email",
    --   "value": "invalid@",
    --   "expected": "valid email format",
    --   "actual": "missing domain",
    --   "rule_condition": "REGEX(...)",
    --   "additional_context": {...}
    -- }
    
    -- Severity and categorization
    severity VARCHAR(50), -- blocker, critical, major, minor, info
    category VARCHAR(50), -- Same as rule category
    
    -- Sample flag (to limit storage of violations)
    is_sample BOOLEAN DEFAULT FALSE, -- TRUE if this is a sample violation (not all violations stored)
    
    -- Metadata
    meta_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_severity CHECK (severity IN ('blocker', 'critical', 'major', 'minor', 'info'))
);

-- Indexes for performance

-- DQ Rules indexes
CREATE INDEX idx_rules_organization ON dq_rules(organization_id);
CREATE INDEX idx_rules_data_source ON dq_rules(data_source_id);
CREATE INDEX idx_rules_status ON dq_rules(status);
CREATE INDEX idx_rules_category ON dq_rules(category);
CREATE INDEX idx_rules_is_active ON dq_rules(is_active);
CREATE INDEX idx_rules_created_at ON dq_rules(created_at DESC);
CREATE INDEX idx_rules_target_table ON dq_rules(target_schema, target_table);

-- GIN index for JSONB queries
CREATE INDEX idx_rules_canonical_rule ON dq_rules USING gin(canonical_rule);
CREATE INDEX idx_rules_tags ON dq_rules USING gin(tags);

-- Rule Executions indexes
CREATE INDEX idx_executions_rule ON rule_executions(rule_id);
CREATE INDEX idx_executions_status ON rule_executions(status);
CREATE INDEX idx_executions_type ON rule_executions(execution_type);
CREATE INDEX idx_executions_started_at ON rule_executions(started_at DESC);
CREATE INDEX idx_executions_pass_rate ON rule_executions(pass_rate);
CREATE INDEX idx_executions_executed_by ON rule_executions(executed_by);

-- Rule Violations indexes
CREATE INDEX idx_violations_execution ON rule_violations(execution_id);
CREATE INDEX idx_violations_severity ON rule_violations(severity);
CREATE INDEX idx_violations_created_at ON rule_violations(created_at DESC);
CREATE INDEX idx_violations_is_sample ON rule_violations(is_sample);

-- GIN index for violation details
CREATE INDEX idx_violations_details ON rule_violations USING gin(violation_details);

-- Comments for documentation
COMMENT ON TABLE dq_rules IS 'Data quality rule definitions with canonical representation';
COMMENT ON TABLE rule_executions IS 'Execution history and results for DQ rules';
COMMENT ON TABLE rule_violations IS 'Individual row violations detected during rule execution';

COMMENT ON COLUMN dq_rules.canonical_rule IS 'Platform-agnostic JSON rule definition';
COMMENT ON COLUMN dq_rules.compiled_sql IS 'Compiled SQL for execution on SQL databases';
COMMENT ON COLUMN dq_rules.compiled_spark IS 'Compiled PySpark code for big data execution';
COMMENT ON COLUMN rule_executions.pass_rate IS 'Percentage of rows that passed the rule (0-100)';
COMMENT ON COLUMN rule_violations.is_sample IS 'Flag indicating if this is a sampled violation (not all violations stored)';
