"""GlossaryService -- unified business glossary CRUD (F109).

Builds on F101's metadata_term_index table, adding glossary management
capabilities: full CRUD, search, CSV import/export.

Terms are scoped by tenant_id so all workspaces within a tenant share
the same glossary.
"""

from __future__ import annotations

import csv
import io
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.glossary import (
    GlossaryImportResult,
    GlossaryListResponse,
    GlossaryTermCreate,
    GlossaryTermResponse,
    GlossaryTermUpdate,
)


def _row_to_response(row) -> GlossaryTermResponse:
    return GlossaryTermResponse(
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
        data_type=getattr(row, "data_type", None),
        owner=getattr(row, "owner", None),
        is_mandatory=getattr(row, "is_mandatory", False) or False,
        allowed_values=getattr(row, "allowed_values", None),
    )


_SELECT_COLS = """
    t.term_id, t.workspace_id, t.business_name, t.technical_name,
    t.definition, t.synonyms, t.domain, t.linked_asset_ids,
    t.source, t.trust_level, t.created_at,
    t.data_type, t.owner, t.is_mandatory, t.allowed_values
"""

_RETURNING_COLS = """
    term_id, workspace_id, business_name, technical_name,
    definition, synonyms, domain, linked_asset_ids,
    source, trust_level, created_at,
    data_type, owner, is_mandatory, allowed_values
"""


class GlossaryService:
    """Full glossary management service (F109)."""

    # -- Create ---

    def create_term(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        payload: GlossaryTermCreate,
    ) -> GlossaryTermResponse:
        result = db.execute(
            text(f"""
                INSERT INTO control.metadata_term_index
                    (workspace_id, tenant_id, business_name, technical_name, definition,
                     synonyms, domain, linked_asset_ids, source, trust_level,
                     data_type, owner, is_mandatory, allowed_values)
                VALUES
                    (:wid, :tid, :bname, :tname, :defn,
                     CAST(:syns AS jsonb), :dom, CAST(:links AS jsonb), 'manual', :trust,
                     :dtype, :own, :mand, CAST(:avals AS jsonb))
                RETURNING {_RETURNING_COLS}
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
                "trust": payload.trust_level,
                "dtype": payload.data_type,
                "own": payload.owner,
                "mand": payload.is_mandatory,
                "avals": json.dumps(payload.allowed_values) if payload.allowed_values else None,
            },
        )
        db.commit()
        return _row_to_response(result.fetchone())

    # -- Read one ---

    def get_term(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
    ) -> GlossaryTermResponse | None:
        result = db.execute(
            text(f"""
                SELECT {_SELECT_COLS}
                FROM control.metadata_term_index t
                WHERE t.term_id = :term_id AND t.tenant_id = :tid
            """),
            {"term_id": str(term_id), "tid": str(tenant_id)},
        )
        row = result.fetchone()
        return _row_to_response(row) if row else None

    # -- List / Search ---

    def list_terms(
        self,
        db: Session,
        tenant_id: UUID,
        search: str | None = None,
        domain: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> GlossaryListResponse:
        page = max(1, page)
        page_size = min(max(1, page_size), 200)
        offset = (page - 1) * page_size

        where_clauses = ["t.tenant_id = :tid"]
        params: dict = {"tid": str(tenant_id), "lim": page_size, "off": offset}

        if domain:
            where_clauses.append("t.domain = :domain")
            params["domain"] = domain

        if search:
            where_clauses.append(
                "(t.business_name ILIKE :search OR t.technical_name ILIKE :search "
                "OR t.definition ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        where_sql = " AND ".join(where_clauses)

        count_result = db.execute(
            text(f"SELECT COUNT(*) FROM control.metadata_term_index t WHERE {where_sql}"),
            params,
        )
        total = count_result.scalar() or 0

        result = db.execute(
            text(f"""
                SELECT {_SELECT_COLS}
                FROM control.metadata_term_index t
                WHERE {where_sql}
                ORDER BY t.created_at DESC
                LIMIT :lim OFFSET :off
            """),
            params,
        )
        items = [_row_to_response(r) for r in result.fetchall()]
        return GlossaryListResponse(items=items, total=total, page=page, page_size=page_size)

    # -- Update ---

    def update_term(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
        payload: GlossaryTermUpdate,
    ) -> GlossaryTermResponse | None:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return self.get_term(db, tenant_id, term_id)

        set_parts = []
        params: dict = {"term_id": str(term_id), "tid": str(tenant_id)}

        for field, value in updates.items():
            if field == "synonyms":
                set_parts.append(f"{field} = CAST(:{field} AS jsonb)")
                params[field] = json.dumps(value)
            elif field == "linked_asset_ids":
                set_parts.append(f"{field} = CAST(:{field} AS jsonb)")
                params[field] = json.dumps(value)
            elif field == "allowed_values":
                set_parts.append(f"{field} = CAST(:{field} AS jsonb)")
                params[field] = json.dumps(value) if value is not None else None
            else:
                set_parts.append(f"{field} = :{field}")
                params[field] = value

        set_parts.append("updated_at = now()")
        set_sql = ", ".join(set_parts)

        result = db.execute(
            text(f"""
                UPDATE control.metadata_term_index
                SET {set_sql}
                WHERE term_id = :term_id AND tenant_id = :tid
                RETURNING {_RETURNING_COLS}
            """),
            params,
        )
        db.commit()
        row = result.fetchone()
        return _row_to_response(row) if row else None

    # -- Delete ---

    def delete_term(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
    ) -> bool:
        result = db.execute(
            text("""
                DELETE FROM control.metadata_term_index
                WHERE term_id = :term_id AND tenant_id = :tid
            """),
            {"term_id": str(term_id), "tid": str(tenant_id)},
        )
        db.commit()
        return result.rowcount > 0

    # -- CSV Import ---

    def import_csv(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        file_content: str,
    ) -> GlossaryImportResult:
        reader = csv.DictReader(io.StringIO(file_content))
        imported = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            business_name = (row.get("Business Term") or row.get("business_name") or "").strip()
            technical_name = (
                row.get("Technical Column") or row.get("technical_name") or ""
            ).strip()

            if not business_name:
                errors.append({"row": row_num, "reason": "Missing required field: business_name"})
                skipped += 1
                continue

            try:
                synonyms_raw = row.get("Synonyms") or row.get("synonyms") or ""
                synonyms = (
                    [s.strip() for s in synonyms_raw.split(",") if s.strip()]
                    if synonyms_raw
                    else []
                )

                allowed_raw = row.get("Allowed Values") or row.get("allowed_values") or ""
                allowed_values = (
                    [s.strip() for s in allowed_raw.split(",") if s.strip()]
                    if allowed_raw
                    else None
                )

                is_mandatory_raw = (
                    (row.get("Mandatory") or row.get("is_mandatory") or "").strip().lower()
                )
                is_mandatory = is_mandatory_raw in ("yes", "true", "1")

                payload = GlossaryTermCreate(
                    business_name=business_name,
                    technical_name=technical_name or None,
                    definition=(row.get("Description") or row.get("definition") or "").strip()
                    or None,
                    domain=(row.get("Domain") or row.get("domain") or "").strip() or None,
                    synonyms=synonyms,
                    data_type=(row.get("Data Type") or row.get("data_type") or "").strip() or None,
                    owner=(row.get("Owner") or row.get("owner") or "").strip() or None,
                    is_mandatory=is_mandatory,
                    allowed_values=allowed_values,
                )

                # Upsert by tenant + business_name
                existing = db.execute(
                    text("""
                        SELECT term_id FROM control.metadata_term_index
                        WHERE tenant_id = :tid AND business_name = :bname
                        LIMIT 1
                    """),
                    {"tid": str(tenant_id), "bname": business_name},
                ).fetchone()

                if existing:
                    self.update_term(
                        db,
                        tenant_id,
                        existing.term_id,
                        GlossaryTermUpdate(
                            **payload.model_dump(exclude={"trust_level", "linked_asset_ids"})
                        ),
                    )
                else:
                    self.create_term(db, workspace_id, tenant_id, payload)
                imported += 1

            except Exception as e:
                errors.append({"row": row_num, "reason": str(e)})
                skipped += 1

        return GlossaryImportResult(imported=imported, skipped=skipped, errors=errors)

    # -- CSV Export ---

    def export_csv(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> str:
        listing = self.list_terms(db, tenant_id, page_size=200)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Business Term",
                "Technical Column",
                "Data Type",
                "Domain",
                "Description",
                "Synonyms",
                "Mandatory",
                "Owner",
                "Allowed Values",
            ]
        )
        for t in listing.items:
            writer.writerow(
                [
                    t.business_name,
                    t.technical_name or "",
                    t.data_type or "",
                    t.domain or "",
                    t.definition or "",
                    ", ".join(t.synonyms) if t.synonyms else "",
                    "Yes" if t.is_mandatory else "No",
                    t.owner or "",
                    ", ".join(t.allowed_values) if t.allowed_values else "",
                ]
            )
        return output.getvalue()

    # -- Tenant-scoped aliases (F130) ------------------------------------
    # The glossary is tenant-scoped: all workspaces in a tenant share the
    # same terms. These `*_for_tenant` wrappers expose that scope as the
    # primary, named entry point for callers that operate on a tenant
    # directly (NL Rule Builder, tenant glossary API, cross-workspace UI).

    def list_terms_for_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        search: str | None = None,
        domain: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> GlossaryListResponse:
        return self.list_terms(
            db,
            tenant_id,
            search=search,
            domain=domain,
            page=page,
            page_size=page_size,
        )

    def get_term_for_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
    ) -> GlossaryTermResponse | None:
        return self.get_term(db, tenant_id, term_id)

    def create_term_for_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        workspace_id: UUID,
        payload: GlossaryTermCreate,
    ) -> GlossaryTermResponse:
        return self.create_term(db, workspace_id, tenant_id, payload)

    def update_term_for_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
        payload: GlossaryTermUpdate,
    ) -> GlossaryTermResponse | None:
        return self.update_term(db, tenant_id, term_id, payload)

    def delete_term_for_tenant(
        self,
        db: Session,
        tenant_id: UUID,
        term_id: UUID,
    ) -> bool:
        return self.delete_term(db, tenant_id, term_id)
