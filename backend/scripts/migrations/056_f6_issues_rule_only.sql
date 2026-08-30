-- Migration: 056_f6_issues_rule_only.sql
-- Feature:   F6 — Auto-create Issue when running a rule directly
-- Description:
--   F031 originally tied every Issue to a FlowExecution. Direct rule
--   executions (no Flow) need to raise issues too, so we relax the
--   flow_execution_id column to be nullable.
--
--   Safe to re-run: ALTER ... DROP NOT NULL is idempotent.

BEGIN;

ALTER TABLE public.issues
    ALTER COLUMN flow_execution_id DROP NOT NULL;

COMMIT;
