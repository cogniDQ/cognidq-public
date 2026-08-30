"""Connector __init__ for easy imports."""

from app.services.datasources.connectors.base import BaseConnector
from app.services.datasources.connectors.registry import (
    ConnectorCapabilities,
    ConnectorCategory,
    ConnectorPriority,
    ConnectorRegistry,
    ConnectorSpec,
    ConnectorStatus,
    CredentialField,
    CredentialFieldType,
    registry,
)

__all__ = [
    "BaseConnector",
    "ConnectorCapabilities",
    "ConnectorCategory",
    "ConnectorPriority",
    "ConnectorRegistry",
    "ConnectorSpec",
    "ConnectorStatus",
    "CredentialField",
    "CredentialFieldType",
    "registry",
]
