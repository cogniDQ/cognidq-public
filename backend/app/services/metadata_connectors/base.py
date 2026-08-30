"""
F108 — MetadataConnector Abstract Base Class.

All metadata connector implementations must subclass this ABC and implement
the required search/fetch methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MetadataConnector(ABC):
    """Abstract interface for external metadata source connectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    # ── connection lifecycle ────────────────────────────────────────────

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Test connectivity.  Returns (success, message, details)."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / session."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down connection / session."""
        ...

    # ── search operations (federated / real-time) ───────────────────────

    @abstractmethod
    async def search_terms(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Search for business/glossary terms matching *query*.

        Each dict should follow the MetadataTermResponse-compatible shape:
            business_name, technical_name, definition, synonyms, domain,
            linked_asset_ids, source, trust_level
        """
        ...

    @abstractmethod
    async def search_datasets(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Search for datasets matching *query*.

        Each dict should follow the MetadataAsset-compatible shape:
            asset_type='dataset', name, display_name, description,
            business_domain, source_table, source_id
        """
        ...

    @abstractmethod
    async def search_columns(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Search for columns/fields matching *query*."""
        ...

    # ── detail fetch operations ─────────────────────────────────────────

    @abstractmethod
    async def get_term_details(self, term_id: str) -> dict[str, Any] | None:
        """Return full details for a glossary term."""
        ...

    @abstractmethod
    async def get_linked_assets(self, term_id: str) -> list[dict[str, Any]]:
        """Return physical assets linked to a glossary term."""
        ...

    # ── bulk sync operations ────────────────────────────────────────────

    @abstractmethod
    async def get_all_terms(self) -> list[dict[str, Any]]:
        """Return all terms for full/scheduled sync."""
        ...

    @abstractmethod
    async def get_all_datasets(self) -> list[dict[str, Any]]:
        """Return all datasets for full/scheduled sync."""
        ...
