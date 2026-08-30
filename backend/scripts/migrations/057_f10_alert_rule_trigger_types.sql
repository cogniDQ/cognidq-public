-- F10 — Expand alert_rules.trigger_type CHECK constraint to include the
-- new auto-escalation trigger types: `rule_failed`, `check_failed`, and
-- `execution_completed` (the latter is already produced by the flow worker
-- but was missing from the original constraint).
--
-- Idempotent: drop the existing constraint (if present) and recreate.

ALTER TABLE public.alert_rules
    DROP CONSTRAINT IF EXISTS ck_alert_rules_trigger_type;

ALTER TABLE public.alert_rules
    ADD CONSTRAINT ck_alert_rules_trigger_type
    CHECK (trigger_type IN (
        'execution_failed',
        'execution_completed',
        'rule_failed',
        'check_failed',
        'issue_created',
        'issue_overdue',
        'incident_created',
        'incident_status_changed'
    ));
