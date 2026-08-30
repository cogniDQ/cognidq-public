-- F106: NL Rule Audit Trail
-- Migration 031: rule_generation_audit + rule_user_feedback

BEGIN;

-- Audit trail for NL rule generation pipeline
CREATE TABLE IF NOT EXISTS control.rule_generation_audit (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL,
    user_id         UUID NOT NULL,
    rule_text       TEXT NOT NULL,
    parse_request_id UUID,
    parsed_sir      JSONB,
    resolution_candidates JSONB,
    selected_mappings JSONB,
    user_overrides  JSONB,
    compiled_config JSONB,
    flow_id         UUID,
    compilation_status TEXT,
    model_version   TEXT,
    metadata_snapshot_version INTEGER DEFAULT 1,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_gen_audit_workspace
    ON control.rule_generation_audit(workspace_id);
CREATE INDEX IF NOT EXISTS idx_rule_gen_audit_user
    ON control.rule_generation_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_rule_gen_audit_created
    ON control.rule_generation_audit(created_at DESC);

-- User feedback on NL rule generation
CREATE TABLE IF NOT EXISTS control.rule_user_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id        UUID NOT NULL REFERENCES control.rule_generation_audit(id) ON DELETE CASCADE,
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN ('accepted_match', 'rejected_match', 'manual_override', 'corrected_rule')),
    entity_role     TEXT NOT NULL CHECK (entity_role IN ('subject', 'object', 'general')),
    original_candidate JSONB,
    selected_candidate JSONB,
    confidence_at_decision FLOAT,
    user_comment    TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rule_feedback_audit
    ON control.rule_user_feedback(audit_id);

COMMIT;
