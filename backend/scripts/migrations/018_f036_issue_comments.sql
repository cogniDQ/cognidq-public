-- ============================================================
-- Migration 018 — F036 Issue Comments and Activity Timeline
-- ============================================================
-- Creates the issue_comments table for immutable user comments
-- on data-quality issues.
--
-- Depends on: 013_f031_issues.sql (public.issues table)
-- ============================================================

-- ----------------------------------------------------------
-- Table: public.issue_comments
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.issue_comments (
    -- Primary key
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),

    -- Parent issue (cascade on delete)
    issue_id        UUID            NOT NULL,

    -- Workspace + tenant scope (cross-schema FK enforced elsewhere)
    workspace_id    UUID            NOT NULL,
    tenant_id       UUID            NOT NULL,

    -- Author (nullable in case user is later deleted)
    author_id       UUID,

    -- Comment body — immutable after creation
    body            TEXT            NOT NULL,

    -- Timestamp
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Constraints
    CONSTRAINT pk_issue_comments PRIMARY KEY (id),

    CONSTRAINT fk_issue_comments_issue
        FOREIGN KEY (issue_id) REFERENCES public.issues (id) ON DELETE CASCADE,

    CONSTRAINT fk_issue_comments_author
        FOREIGN KEY (author_id) REFERENCES public.users (id) ON DELETE SET NULL,

    CONSTRAINT ck_issue_comments_body_length
        CHECK (length(body) BETWEEN 1 AND 10000)
);

-- ----------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_issue_comments_issue_id
    ON public.issue_comments (issue_id);

CREATE INDEX IF NOT EXISTS ix_issue_comments_timeline
    ON public.issue_comments (issue_id, created_at DESC);

-- ----------------------------------------------------------
-- Grants (conditional — only if app role exists)
-- ----------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app') THEN
        GRANT SELECT, INSERT ON public.issue_comments TO app;
    END IF;
END
$$;

-- ----------------------------------------------------------
-- Rollback (manual reference)
-- ----------------------------------------------------------
-- DROP TABLE IF EXISTS public.issue_comments;
