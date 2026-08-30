-- 033: Add llm_config JSONB column to workspace_settings
-- Stores per-workspace LLM provider configuration (provider, encrypted API key, model, etc.)

ALTER TABLE control.workspace_settings
    ADD COLUMN IF NOT EXISTS llm_config JSONB NULL;

COMMENT ON COLUMN control.workspace_settings.llm_config
    IS 'Workspace-level LLM provider configuration (provider, encrypted API key, model, temperature, max_tokens). NULL means use global env config.';
