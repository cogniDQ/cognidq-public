-- Migration 035: Enhanced NL Rule Builder
-- Adds validation workflow, compiled config storage, and dataset auto-detection

-- 1. Add validation columns to nl_rule_parse_results
ALTER TABLE nl_rule_parse_results
    ADD COLUMN IF NOT EXISTS validated BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS validated_by UUID,
    ADD COLUMN IF NOT EXISTS user_adjustments JSONB,
    ADD COLUMN IF NOT EXISTS compiled_config JSONB,
    ADD COLUMN IF NOT EXISTS detected_datasets JSONB,
    ADD COLUMN IF NOT EXISTS detected_columns JSONB,
    ADD COLUMN IF NOT EXISTS check_configs JSONB;

-- 2. Add severity and tags to nl_rule_requests  
ALTER TABLE nl_rule_requests
    ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'medium',
    ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb;

-- 3. Index for listing parses by workspace and validation status
CREATE INDEX IF NOT EXISTS idx_nl_parse_results_validated 
    ON nl_rule_parse_results(request_id);

CREATE INDEX IF NOT EXISTS idx_nl_rule_requests_workspace_created
    ON nl_rule_requests(workspace_id, created_at DESC);
