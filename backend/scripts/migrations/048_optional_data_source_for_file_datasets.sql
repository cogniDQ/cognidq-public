-- ─────────────────────────────────────────────────────────────────────────────
-- 048 — Allow file-typed datasets to omit data_source_id
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Purpose
-- -------
-- File-typed datasets (CSV / Excel / JSON / Parquet uploads) do not have a
-- backing connection in `control.data_sources`.  Make `data_source_id`
-- nullable and enforce, via CHECK, that only `dataset_type='file'` is allowed
-- to omit it.
--
-- The `uq_dataset_physical_id_source` partial unique index is left untouched:
-- PostgreSQL treats NULLs as distinct in unique indexes, so multiple file
-- datasets with NULL data_source_id are permitted (file uniqueness is already
-- guaranteed by the per-workspace name index).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE control.datasets
    ALTER COLUMN data_source_id DROP NOT NULL;

ALTER TABLE control.datasets
    ADD CONSTRAINT ck_datasets_data_source_required
        CHECK (data_source_id IS NOT NULL OR dataset_type = 'file');
