-- F109: Business Glossary Management — extend metadata_term_index
-- F111: Unified Proposal Engine — create nl_rule_proposals table
-- Migration 036

-- ─── F109: Add glossary management columns to metadata_term_index ───────

ALTER TABLE control.metadata_term_index
    ADD COLUMN IF NOT EXISTS data_type      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS owner          VARCHAR(255),
    ADD COLUMN IF NOT EXISTS is_mandatory   BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS allowed_values JSONB;

-- ─── F111: Create proposals table ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS control.nl_rule_proposals (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID         NOT NULL,
    created_by        UUID         NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'confirmed', 'rejected', 'expired')),
    original_prompt   TEXT         NOT NULL,
    proposal_payload  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    adjustments       JSONB,
    generated_flow_id UUID,
    confidence        FLOAT        NOT NULL DEFAULT 0.0,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours'),
    confirmed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_proposals_workspace ON control.nl_rule_proposals(workspace_id);
CREATE INDEX IF NOT EXISTS ix_proposals_status ON control.nl_rule_proposals(status);
CREATE INDEX IF NOT EXISTS ix_proposals_created_by ON control.nl_rule_proposals(created_by);
CREATE INDEX IF NOT EXISTS ix_proposals_created_at ON control.nl_rule_proposals(created_at DESC);

COMMENT ON TABLE control.nl_rule_proposals IS 'NL Rule proposals pending user validation (F111)';
