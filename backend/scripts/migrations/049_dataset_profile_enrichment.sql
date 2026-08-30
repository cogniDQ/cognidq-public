-- 049_dataset_profile_enrichment.sql
-- Persist profiling results so they enrich dataset metadata.
-- Stores the most recent profile JSON on the dataset and per-column stats on dataset_fields.

BEGIN;

-- Dataset-level: last profile snapshot + timestamp
ALTER TABLE control.datasets
    ADD COLUMN IF NOT EXISTS last_profile JSONB,
    ADD COLUMN IF NOT EXISTS last_profiled_at TIMESTAMPTZ;

COMMENT ON COLUMN control.datasets.last_profile IS
    'Most recent dataset profile snapshot (total_rows, total_columns, columns[]).';
COMMENT ON COLUMN control.datasets.last_profiled_at IS
    'When the dataset was last profiled.';

-- Field-level: cached stats from the most recent profile
ALTER TABLE control.dataset_fields
    ADD COLUMN IF NOT EXISTS null_count BIGINT,
    ADD COLUMN IF NOT EXISTS distinct_count BIGINT,
    ADD COLUMN IF NOT EXISTS min_value TEXT,
    ADD COLUMN IF NOT EXISTS max_value TEXT,
    ADD COLUMN IF NOT EXISTS profile_stats JSONB,
    ADD COLUMN IF NOT EXISTS profiled_at TIMESTAMPTZ;

COMMENT ON COLUMN control.dataset_fields.null_count IS
    'Null count from the most recent profile run.';
COMMENT ON COLUMN control.dataset_fields.distinct_count IS
    'Distinct (unique) value count from the most recent profile run.';
COMMENT ON COLUMN control.dataset_fields.min_value IS
    'Minimum value (as text) from the most recent profile run.';
COMMENT ON COLUMN control.dataset_fields.max_value IS
    'Maximum value (as text) from the most recent profile run.';
COMMENT ON COLUMN control.dataset_fields.profile_stats IS
    'Full per-column profile (mean, median, std_dev, top_values, suggested_checks).';
COMMENT ON COLUMN control.dataset_fields.profiled_at IS
    'When this field was last profiled.';

COMMIT;
