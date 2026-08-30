-- =============================================================================
-- F035: Add resolution_summary column to issues table
-- =============================================================================
-- This migration adds the resolution_summary TEXT column for recording
-- issue resolution details when transitioning to resolved/closed status.
-- =============================================================================

ALTER TABLE public.issues ADD COLUMN IF NOT EXISTS resolution_summary TEXT;

COMMENT ON COLUMN public.issues.resolution_summary
    IS 'Free-text explanation of issue resolution. Max 5000 chars enforced at application layer.';
