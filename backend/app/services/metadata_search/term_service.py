"""MetadataTermService â€” glossary term CRUD for metadata_term_index (F101)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.metadata_search import MetadataTermCreate, MetadataTermResponse


class MetadataTermService:
    """CRUD operations on the metadata_term_index table."""

    def create_term(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        payload: MetadataTermCreate,
    ) -> MetadataTermResponse:
        result = db.execute(
            text("""
                INSERT INTO control.metadata_term_index
                    (workspace_id, tenant_id, business_name, technical_name, definition,
                     synonyms, domain, linked_asset_ids, source, trust_level)
                VALUES
                    (:wid, :tid, :bname, :tname, :defn,
                     :syns::jsonb, :dom, :links::jsonb, :src, :trust)
                RETURNING term_id, workspace_id, business_name, technical_name,
                          definition, synonyms, domain, linked_asset_ids,
                          source, trust_level, created_at
            """),
            {
                "wid": str(workspace_id),
                "tid": str(tenant_id),
                "bname": payload.business_name,
                "tname": payload.technical_name,
                "defn": payload.definition,
                "syns": json.dumps(payload.synonyms),
                "dom": payload.domain,
                "links": json.dumps(payload.linked_asset_ids),
                "src": "manual",
                "trust": payload.trust_level,
            },
        )
        db.commit()

        row = result.fetchone()
        return MetadataTermResponse(
            term_id=row.term_id,
            workspace_id=row.workspace_id,
            business_name=row.business_name,
            technical_name=row.technical_name,
            definition=row.definition,
            synonyms=row.synonyms if isinstance(row.synonyms, list) else [],
            domain=row.domain,
            linked_asset_ids=row.linked_asset_ids if isinstance(row.linked_asset_ids, list) else [],
            source=row.source,
            trust_level=row.trust_level,
            created_at=row.created_at,
        )

    def list_terms(
        self,
        db: Session,
        tenant_id: UUID,
        domain: str | None = None,
        limit: int = 50,
    ) -> list[MetadataTermResponse]:
        domain_clause = "AND t.domain = :domain" if domain else ""
        limit = min(max(limit, 1), 200)

        result = db.execute(
            text(f"""
                SELECT t.term_id, t.workspace_id, t.business_name,
                       t.technical_name, t.definition, t.synonyms,
                       t.domain, t.linked_asset_ids, t.source,
                       t.trust_level, t.created_at
                FROM control.metadata_term_index t
                WHERE t.tenant_id = :tid
                  {domain_clause}
                ORDER BY t.created_at DESC
                LIMIT :lim
            """),
            {"tid": str(tenant_id), **({"domain": domain} if domain else {}), "lim": limit},
        )

        rows = result.fetchall()
        return [
            MetadataTermResponse(
                term_id=r.term_id,
                workspace_id=r.workspace_id,
                business_name=r.business_name,
                technical_name=r.technical_name,
                definition=r.definition,
                synonyms=r.synonyms if isinstance(r.synonyms, list) else [],
                domain=r.domain,
                linked_asset_ids=r.linked_asset_ids if isinstance(r.linked_asset_ids, list) else [],
                source=r.source,
                trust_level=r.trust_level,
                created_at=r.created_at,
            )
            for r in rows
        ]
