-- Migration: 016_f032_issue_grouping.sql
-- Feature:   F032 — Issue Grouping and Deduplication
-- Packet:    P01 — Database Schema
-- Created:   2026-03-31
--
-- Description:
--   Adds the `last_seen_at` column to `public.issues` and two partial indexes
--   that support efficient grouping candidate lookups.
--
--   Changes:
--     1. ALTER TABLE public.issues ADD COLUMN last_seen_at TIMESTAMPTZ NULL
--        - NULL on initial issue creation (no prior grouping event)
--        - Set to `completed_at` of the most recent grouped execution on update
--
--     2. CREATE INDEX idx_issues_grouping_rule
--        ON public.issues (workspace_id, rule_id, dataset_id)
--        WHERE status IN ('open', 'in_progress', 'reopened')
--        - Supports one_per_rule mode: find the open issue for workspace+rule+dataset
--
--     3. CREATE INDEX idx_issues_grouping_day
--        ON public.issues (workspace_id, rule_id, dataset_id, opened_at)
--        WHERE status IN ('open', 'in_progress', 'reopened')
--        - Supports one_per_day mode: find the open issue within a calendar window
--
--   Both indexes are partial (filtered to open statuses) to stay proportional
--   to open issue count, not total historic issue corpus.
--
--   All statements use IF NOT EXISTS / IF EXISTS for idempotency.


-- ────────────────────────────────────────────────────────────────────────────
-- 1. Add last_seen_at column
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.issues
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN public.issues.last_seen_at IS
    'Timestamp of the most recent execution grouped into this issue. '
    'NULL when the issue has never been the target of a grouping update. '
    'Set by F032 IssueGroupingService on each accumulation event.';


-- ────────────────────────────────────────────────────────────────────────────
-- 2. Partial index for one_per_rule grouping lookups
-- ────────────────────────────────────────────────────────────────────────────

-- Used by IssueRepository.find_open_for_grouping() in one_per_rule mode.
-- The partial condition limits index size to currently-open issues only.
CREATE INDEX IF NOT EXISTS idx_issues_grouping_rule
    ON public.issues (workspace_id, rule_id, dataset_id)
    WHERE status IN ('open', 'in_progress', 'reopened');


-- ────────────────────────────────────────────────────────────────────────────
-- 3. Partial index for one_per_day grouping lookups
-- ────────────────────────────────────────────────────────────────────────────

-- Used by IssueRepository.find_open_for_grouping() in one_per_day mode.
-- Includes opened_at for the calendar-day window filter.
-- The partial condition is identical so the planner can use this index
-- for one_per_rule queries too (covers superset of columns).
CREATE INDEX IF NOT EXISTS idx_issues_grouping_day
    ON public.issues (workspace_id, rule_id, dataset_id, opened_at)
    WHERE status IN ('open', 'in_progress', 'reopened');


-- ────────────────────────────────────────────────────────────────────────────
-- 4. DB Role Grants (no new table; no additional grants needed)
-- ────────────────────────────────────────────────────────────────────────────
-- dq_app_role already has INSERT + SELECT + UPDATE on public.issues (F031).
-- The new column inherits those grants automatically.


-- ════════════════════════════════════════════════════════════════════════════
-- DOWN MIGRATION
-- ════════════════════════════════════════════════════════════════════════════

/*  ── DOWN ──

DROP INDEX IF EXISTS idx_issues_grouping_day;
DROP INDEX IF EXISTS idx_issues_grouping_rule;
ALTER TABLE public.issues DROP COLUMN IF EXISTS last_seen_at;

*/
