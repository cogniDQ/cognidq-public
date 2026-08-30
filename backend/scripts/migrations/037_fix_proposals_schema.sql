-- Fix nl_rule_proposals table: add updated_at column, update CHECK constraint
-- Migration 037

-- Add updated_at column (defaults to now())
ALTER TABLE control.nl_rule_proposals
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Allow created_by to be nullable (auth may not always provide user_id)
ALTER TABLE control.nl_rule_proposals
    ALTER COLUMN created_by DROP NOT NULL;

-- Drop old CHECK constraint and add updated one that includes 'adjusted'
ALTER TABLE control.nl_rule_proposals
    DROP CONSTRAINT IF EXISTS nl_rule_proposals_status_check;

ALTER TABLE control.nl_rule_proposals
    ADD CONSTRAINT nl_rule_proposals_status_check
    CHECK (status IN ('pending', 'confirmed', 'rejected', 'adjusted', 'expired'));
