"""MetadataSyncService — populates metadata_asset_index from existing tables (F101)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.metadata_search import MetadataSyncResponse


class MetadataSyncService:
    """Syncs datasets, dataset fields, and data sources into the metadata asset index."""

    def sync_workspace(self, db: Session, workspace_id: UUID) -> MetadataSyncResponse:
        created = 0
        updated = 0

        # ── Sync datasets ──────────────────────────────────────────────
        ds_result = db.execute(
            text("""
                INSERT INTO control.metadata_asset_index
                    (workspace_id, asset_type, name, display_name, description,
                     business_domain, data_type, source_table, source_id)
                SELECT
                    d.workspace_id,
                    'dataset',
                    d.dataset_name,
                    d.dataset_name,
                    d.description,
                    d.business_domain,
                    d.dataset_type,
                    'datasets',
                    d.dataset_id
                FROM control.datasets d
                WHERE d.workspace_id = :wid
                  AND d.status != 'archived'
                ON CONFLICT (workspace_id, source_table, source_id)
                DO UPDATE SET
                    name            = EXCLUDED.name,
                    display_name    = EXCLUDED.display_name,
                    description     = EXCLUDED.description,
                    business_domain = EXCLUDED.business_domain,
                    data_type       = EXCLUDED.data_type
                RETURNING (xmax = 0) AS is_insert
            """),
            {"wid": str(workspace_id)},
        )
        for row in ds_result:
            if row.is_insert:
                created += 1
            else:
                updated += 1

        # ── Sync dataset fields ────────────────────────────────────────
        fld_result = db.execute(
            text("""
                INSERT INTO control.metadata_asset_index
                    (workspace_id, asset_type, name, display_name, description,
                     data_type, parent_asset_id, source_table, source_id)
                SELECT
                    d.workspace_id,
                    'field',
                    f.field_name,
                    f.field_name,
                    f.business_definition,
                    f.data_type,
                    (SELECT ai.asset_id FROM control.metadata_asset_index ai
                     WHERE ai.workspace_id = d.workspace_id
                       AND ai.source_table = 'datasets'
                       AND ai.source_id = d.dataset_id
                     LIMIT 1),
                    'dataset_fields',
                    f.field_id
                FROM control.dataset_fields f
                JOIN control.datasets d ON d.dataset_id = f.dataset_id
                WHERE d.workspace_id = :wid
                  AND d.status != 'archived'
                ON CONFLICT (workspace_id, source_table, source_id)
                DO UPDATE SET
                    name         = EXCLUDED.name,
                    display_name = EXCLUDED.display_name,
                    description  = EXCLUDED.description,
                    data_type    = EXCLUDED.data_type,
                    parent_asset_id = EXCLUDED.parent_asset_id
                RETURNING (xmax = 0) AS is_insert
            """),
            {"wid": str(workspace_id)},
        )
        for row in fld_result:
            if row.is_insert:
                created += 1
            else:
                updated += 1

        # ── Sync data sources ──────────────────────────────────────────
        src_result = db.execute(
            text("""
                INSERT INTO control.metadata_asset_index
                    (workspace_id, asset_type, name, display_name, description,
                     data_type, source_table, source_id)
                SELECT
                    ds.workspace_id,
                    'datasource',
                    ds.name,
                    ds.name,
                    NULL,
                    ds.type,
                    'data_sources',
                    ds.id
                FROM control.data_sources ds
                WHERE ds.workspace_id = :wid
                  AND ds.status = 'active'
                ON CONFLICT (workspace_id, source_table, source_id)
                DO UPDATE SET
                    name         = EXCLUDED.name,
                    display_name = EXCLUDED.display_name,
                    data_type    = EXCLUDED.data_type
                RETURNING (xmax = 0) AS is_insert
            """),
            {"wid": str(workspace_id)},
        )
        for row in src_result:
            if row.is_insert:
                created += 1
            else:
                updated += 1

        db.commit()

        return MetadataSyncResponse(
            assets_created=created,
            assets_updated=updated,
            total=created + updated,
            workspace_id=workspace_id,
        )
