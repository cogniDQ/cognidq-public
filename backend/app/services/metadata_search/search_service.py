"""MetadataSearchService — unified search across assets and terms (F101)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.metadata_search import (
    MetadataAsset,
    MetadataSearchResponse,
    MetadataTermResponse,
)


class MetadataSearchService:
    """Searches metadata_asset_index and metadata_term_index with ranked scoring."""

    # Weight constants for combined scoring
    W_EXACT = 0.3
    W_TSRANK = 0.4
    W_TRIGRAM = 0.3

    def search(
        self,
        db: Session,
        workspace_id: UUID,
        query: str,
        asset_type: str | None = None,
        domain: str | None = None,
        limit: int = 20,
    ) -> MetadataSearchResponse:
        query = query.strip()
        if not query:
            return MetadataSearchResponse(assets=[], terms=[], total=0)

        limit = min(max(limit, 1), 100)

        assets = self._search_assets(db, workspace_id, query, asset_type, domain, limit)
        terms = self._search_terms(db, workspace_id, query, domain, limit)

        return MetadataSearchResponse(
            assets=assets,
            terms=terms,
            total=len(assets) + len(terms),
        )

    # ── Asset search ──────────────────────────────────────────────────

    def _search_assets(
        self,
        db: Session,
        workspace_id: UUID,
        query: str,
        asset_type: str | None,
        domain: str | None,
        limit: int,
    ) -> list[MetadataAsset]:
        type_clause = "AND a.asset_type = :asset_type" if asset_type else ""
        domain_clause = "AND a.business_domain = :domain" if domain else ""

        sql = text(f"""
            SELECT
                a.asset_id, a.workspace_id, a.asset_type, a.name,
                a.display_name, a.description, a.business_domain,
                a.data_type, a.parent_asset_id, a.source_table,
                a.source_id, a.created_at,
                (
                    {self.W_EXACT}   * CASE WHEN lower(a.name) = lower(:q) THEN 1.0 ELSE 0.0 END
                  + {self.W_TSRANK}  * coalesce(ts_rank(a.search_text, plainto_tsquery('english', :q)), 0)
                  + {self.W_TRIGRAM} * coalesce(similarity(a.name, :q), 0)
                ) AS relevance_score
            FROM control.metadata_asset_index a
            WHERE a.workspace_id = :wid
              AND (
                  a.search_text @@ plainto_tsquery('english', :q)
                  OR similarity(a.name, :q) > 0.15
                  OR lower(a.name) = lower(:q)
              )
              {type_clause}
              {domain_clause}
            ORDER BY relevance_score DESC
            LIMIT :lim
        """)

        params: dict = {"wid": str(workspace_id), "q": query, "lim": limit}
        if asset_type:
            params["asset_type"] = asset_type
        if domain:
            params["domain"] = domain

        rows = db.execute(sql, params).fetchall()
        return [
            MetadataAsset(
                asset_id=r.asset_id,
                workspace_id=r.workspace_id,
                asset_type=r.asset_type,
                name=r.name,
                display_name=r.display_name,
                description=r.description,
                business_domain=r.business_domain,
                data_type=r.data_type,
                parent_asset_id=r.parent_asset_id,
                source_table=r.source_table,
                source_id=r.source_id,
                relevance_score=float(r.relevance_score),
                created_at=r.created_at,
            )
            for r in rows
        ]

    # ── Term search ───────────────────────────────────────────────────

    def _search_terms(
        self,
        db: Session,
        workspace_id: UUID,
        query: str,
        domain: str | None,
        limit: int,
    ) -> list[MetadataTermResponse]:
        domain_clause = "AND t.domain = :domain" if domain else ""

        sql = text(f"""
            SELECT
                t.term_id, t.workspace_id, t.business_name,
                t.technical_name, t.definition, t.synonyms,
                t.domain, t.linked_asset_ids, t.source,
                t.trust_level, t.created_at,
                (
                    {self.W_EXACT}   * CASE WHEN lower(t.business_name) = lower(:q) THEN 1.0 ELSE 0.0 END
                  + {self.W_TSRANK}  * coalesce(ts_rank(t.search_text, plainto_tsquery('english', :q)), 0)
                  + {self.W_TRIGRAM} * coalesce(similarity(t.business_name, :q), 0)
                ) AS relevance_score
            FROM control.metadata_term_index t
            WHERE t.workspace_id = :wid
              AND (
                  t.search_text @@ plainto_tsquery('english', :q)
                  OR similarity(t.business_name, :q) > 0.15
                  OR lower(t.business_name) = lower(:q)
              )
              {domain_clause}
            ORDER BY relevance_score DESC
            LIMIT :lim
        """)

        params: dict = {"wid": str(workspace_id), "q": query, "lim": limit}
        if domain:
            params["domain"] = domain

        rows = db.execute(sql, params).fetchall()
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
                relevance_score=float(r.relevance_score),
                created_at=r.created_at,
            )
            for r in rows
        ]
