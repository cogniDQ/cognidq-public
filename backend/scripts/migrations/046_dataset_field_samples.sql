-- 046_dataset_field_samples.sql
-- E2 — candidate enrichment with table preview: cache sample values per dataset field
-- so the NL Rule Builder can show representative values when the user is choosing
-- which column a candidate refers to.

ALTER TABLE control.dataset_fields
    ADD COLUMN IF NOT EXISTS sample_values TEXT[] DEFAULT '{}'::TEXT[];

ALTER TABLE control.dataset_fields
    ADD COLUMN IF NOT EXISTS sample_values_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN control.dataset_fields.sample_values IS
    'Up to ~10 representative values for this column, used for candidate previews in NL Rule Builder.';
COMMENT ON COLUMN control.dataset_fields.sample_values_updated_at IS
    'When the sample_values array was last refreshed.';
