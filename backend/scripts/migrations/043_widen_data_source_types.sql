-- Migration 043 — Widen control.data_sources.source_type allowlist.
--
-- Background
-- ----------
-- The connector registry (``backend/app/services/datasources/connectors/registry.py``)
-- promotes file-based and lakehouse connectors (csv, excel, json, parquet,
-- s3, adls_gen2, gcs, databricks, redshift, synapse, iceberg, trino,
-- dbt_manifest, hive_metastore, powerbi) to ``READY``, and the F130
-- onboarding wizard (``frontend/src/pages/connections/CreateConnectionPage.tsx``)
-- exposes them. However the original F004 migration (009) hard-coded a
-- 6-entry CHECK constraint on ``control.data_sources.source_type`` /
-- ``control.data_source_credentials.source_type`` that rejects every
-- non-database connector with a CheckViolation, so the customer journey
-- "Login → CSV connection → Dataset" cannot complete.
--
-- This migration drops both legacy CHECK constraints and re-creates them
-- with the full registry-aligned allowlist. The Python validation layer
-- (``backend/app/services/data_sources/models.py::SUPPORTED_SOURCE_TYPES``)
-- is updated in the same change-set.
--
-- Idempotent: the constraint names are stable, so re-running only adds
-- the constraint when it's missing.

BEGIN;

ALTER TABLE control.data_sources
    DROP CONSTRAINT IF EXISTS ck_data_sources_source_type;

ALTER TABLE control.data_sources
    ADD CONSTRAINT ck_data_sources_source_type
    CHECK (source_type IN (
        -- Relational databases (legacy F004)
        'postgresql', 'mysql', 'mssql', 'oracle',
        -- Cloud DWHs (legacy F004 + extensions)
        'snowflake', 'bigquery', 'redshift', 'synapse',
        -- File-based connectors (F130 catalog)
        'csv', 'excel', 'json', 'parquet',
        -- Object storage / lakehouse (F130 catalog)
        's3', 'adls_gen2', 'gcs', 'databricks', 'iceberg', 'trino',
        -- Metadata / BI (F130 catalog)
        'dbt_manifest', 'hive_metastore', 'powerbi'
    ));

ALTER TABLE control.data_source_credentials
    DROP CONSTRAINT IF EXISTS ck_ds_credentials_source_type;

ALTER TABLE control.data_source_credentials
    ADD CONSTRAINT ck_ds_credentials_source_type
    CHECK (source_type IN (
        'postgresql', 'mysql', 'mssql', 'oracle',
        'snowflake', 'bigquery', 'redshift', 'synapse',
        'csv', 'excel', 'json', 'parquet',
        's3', 'adls_gen2', 'gcs', 'databricks', 'iceberg', 'trino',
        'dbt_manifest', 'hive_metastore', 'powerbi'
    ));

COMMIT;
