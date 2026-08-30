"""
F108 — Connector Registry.

Singleton registry that maps connector type names to their implementation classes.
Connector implementations register themselves at import time.
"""

from __future__ import annotations

import logging

from app.services.metadata_connectors.base import MetadataConnector

logger = logging.getLogger(__name__)


class _RegistryMeta:
    """Internal storage for registered connector classes."""

    _connectors: dict[str, type[MetadataConnector]] = {}


class ConnectorRegistry:
    """Static registry of available MetadataConnector implementations."""

    @staticmethod
    def register(type_name: str, cls: type[MetadataConnector]) -> None:
        """Register a connector class under *type_name*."""
        _RegistryMeta._connectors[type_name] = cls
        logger.info("Registered metadata connector type: %s → %s", type_name, cls.__name__)

    @staticmethod
    def get(type_name: str) -> type[MetadataConnector] | None:
        """Return the connector class for *type_name*, or None."""
        return _RegistryMeta._connectors.get(type_name)

    @staticmethod
    def list_types() -> list[str]:
        """Return all registered connector type names."""
        return sorted(_RegistryMeta._connectors.keys())

    @staticmethod
    def list_all() -> dict[str, type[MetadataConnector]]:
        """Return the full type→class mapping."""
        return dict(_RegistryMeta._connectors)

    @staticmethod
    def clear() -> None:
        """Remove all registrations (useful in tests)."""
        _RegistryMeta._connectors.clear()
