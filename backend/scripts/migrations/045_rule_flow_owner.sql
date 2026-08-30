-- Migration: 045_rule_flow_owner.sql
-- Purpose: Add explicit owner_id to dq_rules and dq_flows for RBAC ownership
--          and accountability. Defaults to created_by for existing rows so
--          ownership is non-NULL in practice; column itself is nullable to
--          allow unassigned rules during bulk imports.

BEGIN;

ALTER TABLE public.dq_rules
    ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE public.dq_flows
    ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_dq_rules_owner_user_id
    ON public.dq_rules (owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dq_flows_owner_user_id
    ON public.dq_flows (owner_user_id) WHERE owner_user_id IS NOT NULL;

-- Backfill: default owner = created_by where owner is NULL
UPDATE public.dq_rules SET owner_user_id = created_by
    WHERE owner_user_id IS NULL AND created_by IS NOT NULL;

UPDATE public.dq_flows SET owner_user_id = created_by
    WHERE owner_user_id IS NULL AND created_by IS NOT NULL;

COMMIT;
