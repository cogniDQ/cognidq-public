"""Utilities for loading glossary context for NL rule parsing (F122 P01)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.glossary import GlossaryTermResponse
from app.services.glossary.service import GlossaryService

logger = logging.getLogger(__name__)


@dataclass
class GlossaryPromptTerm:
    """Compact glossary term representation for prompt context."""

    term_id: UUID
    business_name: str
    technical_name: str | None
    synonyms: list[str]
    definition: str | None
    data_type: str | None
    domain: str | None
    linked_asset_ids: list[str]
    relevance_score: float


class GlossaryTermLoader:
    """Loads and formats glossary terms for parser prompt enrichment."""

    def __init__(self, glossary_service: GlossaryService | None = None) -> None:
        self.glossary_service = glossary_service or GlossaryService()

    def load_glossary_for_rule(
        self,
        db: Session,
        workspace_id: UUID,
        rule_text: str,
        max_terms: int = 20,
        page_size: int = 200,
        tenant_id: UUID | None = None,
    ) -> list[GlossaryPromptTerm]:
        """Load and rank glossary terms relevant to the provided rule text.

        The glossary is tenant-scoped: all workspaces in a tenant share the
        same terms. If ``tenant_id`` is not supplied, it is resolved from the
        provided ``workspace_id``.

        This method is intentionally fail-open: if glossary loading fails, return
        an empty list so the parser can continue using dataset metadata only.
        """
        if not rule_text or not rule_text.strip():
            return []

        safe_max_terms = max(1, min(max_terms, 50))
        safe_page_size = max(1, min(page_size, 200))

        try:
            effective_tenant_id = tenant_id or self._resolve_tenant_id(db, workspace_id)
            if effective_tenant_id is None:
                return []

            result = self.glossary_service.list_terms_for_tenant(
                db=db,
                tenant_id=effective_tenant_id,
                page=1,
                page_size=safe_page_size,
            )
            if not result.items:
                return []

            scored_terms: list[GlossaryPromptTerm] = []
            for term in result.items:
                score = self._compute_term_relevance_score(term, rule_text)
                if score <= 0.0:
                    continue
                scored_terms.append(
                    GlossaryPromptTerm(
                        term_id=term.term_id,
                        business_name=term.business_name,
                        technical_name=term.technical_name,
                        synonyms=term.synonyms or [],
                        definition=term.definition,
                        data_type=term.data_type,
                        domain=term.domain,
                        linked_asset_ids=term.linked_asset_ids or [],
                        relevance_score=score,
                    )
                )

            scored_terms.sort(key=lambda t: (-t.relevance_score, t.business_name.lower()))
            return scored_terms[:safe_max_terms]
        except Exception as exc:  # pragma: no cover - safety net path
            logger.warning(
                "Failed to load glossary terms for workspace %s; parsing will continue without glossary context: %s",
                workspace_id,
                exc,
            )
            return []

    @staticmethod
    def _resolve_tenant_id(db: Session, workspace_id: UUID) -> UUID | None:
        """Look up the tenant_id that owns the given workspace.

        The glossary is tenant-scoped, so we need the workspace's tenant to
        load terms shared by every workspace in that tenant.
        """
        row = db.execute(
            text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid LIMIT 1"),
            {"wid": str(workspace_id)},
        ).fetchone()
        if not row or not row.tenant_id:
            return None
        tid = row.tenant_id
        return tid if isinstance(tid, UUID) else UUID(str(tid))

    def _compute_term_relevance_score(self, term: GlossaryTermResponse, rule_text: str) -> float:
        """Compute deterministic relevance score in [0.0, 1.0]."""
        rule_tokens = self._tokenize(rule_text)
        if not rule_tokens:
            return 0.0

        business_tokens = self._tokenize(term.business_name)
        technical_tokens = self._tokenize(term.technical_name or "")
        definition_tokens = self._tokenize(term.definition or "")
        synonym_tokens = self._tokenize(" ".join(term.synonyms or []))
        domain_tokens = self._tokenize(term.domain or "")

        business_or_synonym = max(
            self._token_overlap(rule_tokens, business_tokens),
            self._token_overlap(rule_tokens, synonym_tokens),
        )
        technical = self._token_overlap(rule_tokens, technical_tokens)
        definition = self._token_overlap(rule_tokens, definition_tokens)
        domain = self._token_overlap(rule_tokens, domain_tokens)

        # Weighted sum favors business and synonym language.
        score = (
            (0.45 * business_or_synonym)
            + (0.25 * technical)
            + (0.20 * definition)
            + (0.10 * domain)
        )
        return max(0.0, min(1.0, round(score, 4)))

    def format_glossary_for_prompt(
        self, terms: Iterable[GlossaryPromptTerm], max_chars: int = 3000
    ) -> str:
        """Render glossary terms into a bounded prompt section."""
        terms_list = list(terms)
        if not terms_list:
            return ""

        section_lines = ["BUSINESS GLOSSARY (relevant terms):", ""]
        for idx, term in enumerate(terms_list, start=1):
            synonyms = ", ".join(term.synonyms) if term.synonyms else "-"
            linked_assets = ", ".join(term.linked_asset_ids) if term.linked_asset_ids else "-"

            candidate_lines = [
                f"{idx}. Business Name: {term.business_name}",
                f"   Term ID: {term.term_id}",
                f"   Technical Name: {term.technical_name or '-'}",
                f"   Synonyms: {synonyms}",
                f"   Definition: {term.definition or '-'}",
                f"   Data Type: {term.data_type or '-'}",
                f"   Domain: {term.domain or '-'}",
                f"   Linked Assets: {linked_assets}",
                f"   Relevance: {term.relevance_score}",
                "",
            ]

            candidate_block = "\n".join(candidate_lines)
            current = "\n".join(section_lines)
            if len(current) + len(candidate_block) > max_chars:
                break
            section_lines.extend(candidate_lines)

        return "\n".join(section_lines).strip()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        if not text:
            return set()
        return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}

    @classmethod
    def _token_overlap(cls, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        exact_overlap = len(left.intersection(right)) / len(right)

        # Partial token support for abbreviations and variants (e.g. emp_email vs email)
        partial_hits = 0
        for token in right:
            if any((token in ltok) or (ltok in token) for ltok in left):
                partial_hits += 1
        partial_overlap = partial_hits / len(right)

        return max(exact_overlap, 0.6 * partial_overlap)
