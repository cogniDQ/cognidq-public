-- Migration: 042_connection_dataset_lifecycle.sql
-- Feature: F-CONN-CORE — Connection & Dataset Lifecycle Expansion
--
-- Expands the status CHECK constraints on `control.data_sources` and
-- `control.datasets` to cover the full lifecycle defined in
-- `documentation/planning/full_p0_p1_structured_data_connections_spec.md`
-- §11 (connections) and §12 (datasets).
--
-- This is purely ADDITIVE: every value previously accepted is still accepted,
-- so no existing row, code path, or test breaks. The new values are exercised
-- by the F-CONN-CORE state-machine helpers in:
--   - backend/app/services/connections/lifecycle.py
--   - backend/app/services/datasets/lifecycle.py
--
-- ─── Connection lifecycle (spec §11) ────────────────────────────────────────
-- Existing:   active, archived
-- Added:      draft, created, test_failed, test_successful,
--             discovery_available, disabled
-- ─── Dataset lifecycle (spec §12) ───────────────────────────────────────────
-- Existing:   draft, active, inactive, archived
-- Added:      discovered, registered, checked, inaccessible

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Connections (control.data_sources)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.data_sources
    DROP CONSTRAINT IF EXISTS ck_data_sources_status;

ALTER TABLE control.data_sources
    ADD CONSTRAINT ck_data_sources_status
    CHECK (status IN (
        -- Spec §11 lifecycle states
        'draft',
        'created',
        'test_failed',
        'test_successful',
        'discovery_available',
        'active',
        'disabled',
        'archived'
    ));

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Datasets (control.datasets)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.datasets
    DROP CONSTRAINT IF EXISTS ck_datasets_status;

ALTER TABLE control.datasets
    ADD CONSTRAINT ck_datasets_status
    CHECK (status IN (
        -- Spec §12 lifecycle states
        'discovered',
        'registered',
        'active',
        'checked',
        'inaccessible',
        'archived',
        -- Legacy values preserved for backwards compatibility
        'draft',
        'inactive'
    ));

COMMIT;
