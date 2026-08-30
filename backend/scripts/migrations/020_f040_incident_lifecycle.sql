-- Migration: 020_f040_incident_lifecycle.sql
-- Feature:   F040 — Incident Acknowledgement and Resolution
-- Packet:    P01 — Add lifecycle columns to incidents table
-- Description:
--   Adds acknowledged_at, resolved_at, closed_at, resolution_summary
--   to the incidents table for lifecycle tracking.
--
--   Safe to re-run: uses ADD COLUMN IF NOT EXISTS.

BEGIN;

ALTER TABLE public.incidents
    ADD COLUMN IF NOT EXISTS acknowledged_at     TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS resolved_at         TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS closed_at           TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS resolution_summary  TEXT        NULL;

COMMIT;

-- ROLLBACK:
--   ALTER TABLE public.incidents DROP COLUMN IF EXISTS acknowledged_at;
--   ALTER TABLE public.incidents DROP COLUMN IF EXISTS resolved_at;
--   ALTER TABLE public.incidents DROP COLUMN IF EXISTS closed_at;
--   ALTER TABLE public.incidents DROP COLUMN IF EXISTS resolution_summary;
