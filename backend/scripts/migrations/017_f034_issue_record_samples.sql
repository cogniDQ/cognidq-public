-- Migration 017 — F034 Record Sample Capture and Masking
-- Creates public.issue_record_samples table.
-- Depends on migration 013 (public.issues).
-- Safe to run multiple times (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS public.issue_record_samples (
    id                UUID        NOT NULL DEFAULT gen_random_uuid(),
    issue_id          UUID        NOT NULL,
    workspace_id      UUID        NOT NULL,
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sample_count      INTEGER     NOT NULL DEFAULT 0,
    -- JSON array of record dicts; values masked at capture time.
    rows              JSONB       NOT NULL DEFAULT '[]',
    -- TRUE when at least one column value was replaced with "[MASKED]".
    masking_applied   BOOLEAN     NOT NULL DEFAULT false,
    -- The masking threshold applied: 'confidential' = mask confidential+restricted.
    -- NULL means no masking was performed (e.g. no dataset_id available).
    masking_threshold VARCHAR(20) NULL,

    CONSTRAINT pk_issue_record_samples
        PRIMARY KEY (id),

    CONSTRAINT fk_issue_samples_issue
        FOREIGN KEY (issue_id)
        REFERENCES public.issues (id)
        ON DELETE CASCADE,

    CONSTRAINT ck_issue_samples_masking_threshold
        CHECK (masking_threshold IS NULL OR masking_threshold IN ('confidential', 'restricted', 'none'))
);

-- Primary lookup by issue
CREATE INDEX IF NOT EXISTS idx_issue_samples_issue_id
    ON public.issue_record_samples (issue_id);

-- Secondary lookup scoped to workspace (for access-control queries)
CREATE INDEX IF NOT EXISTS idx_issue_samples_workspace
    ON public.issue_record_samples (workspace_id);

COMMENT ON TABLE public.issue_record_samples IS
    'F034: bounded sample of failing records captured at issue-creation time, '
    'with sensitivity-based column masking applied before storage.';
