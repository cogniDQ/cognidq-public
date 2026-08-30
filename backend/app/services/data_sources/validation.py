"""
F004 — Pure validation layer for Data Source operations
=========================================================

All functions are database-free and I/O-free. They accept raw Python
values and return lists of field-level error dicts. Callers collect all
errors before returning (not fail-fast).

Constants used both here and in the service layer are re-exported from
``models.py`` via this module for a single import point.
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.data_sources.models import (
    BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS,
    IMMUTABLE_FIELDS,
    JDBC_SOURCE_TYPES,
    SUPPORTED_SOURCE_TYPES,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_CONNECTION_MODES = frozenset({"direct", "agent"})
VALID_ENVIRONMENTS = frozenset({"development", "staging", "production"})
VALID_STATUSES = frozenset({"active", "archived"})

_MAX_SOURCE_NAME_LEN = 100
_MAX_DESCRIPTION_LEN = 500

# RFC1918 + loopback patterns for SSRF prevention
_PRIVATE_IP_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    errors: list[dict[str, str]]

    @property
    def is_valid(self) -> bool:
        return not self.errors


# ─────────────────────────────────────────────────────────────────────────────
# Individual validators
# ─────────────────────────────────────────────────────────────────────────────


def validate_source_name(value: Any) -> list[dict[str, str]]:
    """source_name: non-empty string, max 100 chars, after strip."""
    errors: list[dict[str, str]] = []
    if not isinstance(value, str):
        return [{"field": "source_name", "message": "Must be a string."}]
    stripped = value.strip()
    if not stripped:
        errors.append({"field": "source_name", "message": "Cannot be empty."})
    elif len(stripped) > _MAX_SOURCE_NAME_LEN:
        errors.append(
            {
                "field": "source_name",
                "message": f"Exceeds maximum length of {_MAX_SOURCE_NAME_LEN} characters.",
            }
        )
    return errors


def validate_source_type(value: Any) -> list[dict[str, str]]:
    """source_type must be one of SUPPORTED_SOURCE_TYPES."""
    if value not in SUPPORTED_SOURCE_TYPES:
        return [
            {
                "field": "source_type",
                "message": (
                    f"Unsupported source type '{value}'. Allowed: {sorted(SUPPORTED_SOURCE_TYPES)}."
                ),
            }
        ]
    return []


def validate_connection_mode(value: Any) -> list[dict[str, str]]:
    """connection_mode must be 'direct' or 'agent'."""
    if value not in VALID_CONNECTION_MODES:
        return [
            {
                "field": "connection_mode",
                "message": f"Must be one of: {sorted(VALID_CONNECTION_MODES)}.",
            }
        ]
    return []


def validate_environment(value: Any) -> list[dict[str, str]]:
    """environment must be 'development', 'staging', or 'production'."""
    if value not in VALID_ENVIRONMENTS:
        return [
            {
                "field": "environment",
                "message": f"Must be one of: {sorted(VALID_ENVIRONMENTS)}.",
            }
        ]
    return []


def validate_description(value: Any) -> list[dict[str, str]]:
    """description: optional str; if present, max 500 chars."""
    if value is None:
        return []
    if not isinstance(value, str):
        return [{"field": "description", "message": "Must be a string."}]
    if len(value) > _MAX_DESCRIPTION_LEN:
        return [
            {
                "field": "description",
                "message": f"Exceeds maximum length of {_MAX_DESCRIPTION_LEN} characters.",
            }
        ]
    return []


def validate_host_not_private(host: str) -> list[dict[str, str]]:
    """
    SSRF prevention: reject RFC1918 and loopback addresses in 'direct' mode.
    Accepts both IP addresses and hostnames.
    For hostnames that cannot be resolved at validation time, skip network check.
    """
    # Try as IP address first
    try:
        ip = ipaddress.ip_address(host)
        for network in _PRIVATE_IP_NETWORKS:
            if ip in network:
                return [
                    {
                        "field": "credentials.host",
                        "message": (
                            "Private or loopback addresses are not allowed "
                            "for direct-mode connections."
                        ),
                    }
                ]
        return []
    except ValueError:
        pass  # not an IP literal — proceed with hostname check

    # Block obviously private hostnames
    lower = host.lower()
    if lower in ("localhost", "localhost.localdomain"):
        return [
            {
                "field": "credentials.host",
                "message": "localhost is not allowed for direct-mode connections.",
            }
        ]
    # Block .local TLDs (mDNS, typically private)
    if lower.endswith(".local"):
        return [
            {
                "field": "credentials.host",
                "message": ".local hostnames are not allowed for direct-mode connections.",
            }
        ]
    return []


def validate_port(value: Any) -> list[dict[str, str]]:
    """port: integer 1–65535."""
    if not isinstance(value, int) or isinstance(value, bool):
        return [{"field": "credentials.port", "message": "Must be an integer."}]
    if not (1 <= value <= 65535):
        return [{"field": "credentials.port", "message": "Must be between 1 and 65535."}]
    return []


def validate_credential_structure(
    source_type: str,
    credentials: Any,
    connection_mode: str = "direct",
) -> list[dict[str, str]]:
    """
    Validate credential dict shape for a given source_type.

    * postgresql: requires host, port, database, username, password
    * mysql/mssql/oracle (JDBC): same five fields
    * snowflake: requires account, warehouse, database, username, password
    * bigquery: requires service_account_json (valid JSON, all required keys)
    * agent mode: no credential shape validation — agent handles credentials
    * host is validated for SSRF if connection_mode == 'direct' (skipped in dev)
    """
    if connection_mode == "agent":
        return []  # agent mode: server does not validate credential shape

    if not isinstance(credentials, dict):
        return [{"field": "credentials", "message": "Must be an object."}]

    # Skip SSRF host validation in development/debug mode so that localhost
    # connections can be used for local test databases.
    _check_ssrf = not getattr(settings, "DEBUG", False)

    errors: list[dict[str, str]] = []

    if source_type in (frozenset({"postgresql"}) | JDBC_SOURCE_TYPES):
        for field_name in ("host", "port", "database", "username", "password"):
            if not credentials.get(field_name):
                errors.append(
                    {
                        "field": f"credentials.{field_name}",
                        "message": "Required.",
                    }
                )
        if _check_ssrf and "host" in credentials and not errors:
            errors.extend(validate_host_not_private(credentials["host"]))
        if "port" in credentials:
            errors.extend(validate_port(credentials["port"]))

    elif source_type == "snowflake":
        for field_name in ("account", "warehouse", "database", "username", "password"):
            if not credentials.get(field_name):
                errors.append(
                    {
                        "field": f"credentials.{field_name}",
                        "message": "Required.",
                    }
                )

    elif source_type == "bigquery":
        raw = credentials.get("service_account_json")
        if not raw:
            errors.append(
                {
                    "field": "credentials.service_account_json",
                    "message": "Required.",
                }
            )
        else:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(parsed, dict):
                    raise ValueError
                missing_keys = BIGQUERY_SERVICE_ACCOUNT_REQUIRED_KEYS - set(parsed.keys())
                if missing_keys:
                    errors.append(
                        {
                            "field": "credentials.service_account_json",
                            "message": (f"Missing required keys: {sorted(missing_keys)}."),
                        }
                    )
            except (ValueError, json.JSONDecodeError):
                errors.append(
                    {
                        "field": "credentials.service_account_json",
                        "message": "Must be valid JSON.",
                    }
                )

    return errors


def validate_immutable_fields_not_changed(
    update_payload: dict[str, Any],
) -> list[dict[str, str]]:
    """
    Reject any PATCH payload that tries to change an immutable field.
    Currently: source_type.
    """
    errors: list[dict[str, str]] = []
    for field_name in IMMUTABLE_FIELDS:
        if field_name in update_payload:
            errors.append(
                {
                    "field": field_name,
                    "message": f"'{field_name}' cannot be changed after creation.",
                }
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Composite validator for create
# ─────────────────────────────────────────────────────────────────────────────


def validate_create_payload(payload: dict[str, Any]) -> ValidationResult:
    """
    Validate a data source creation payload. Returns accumulated errors.

    Required top-level keys: source_name, source_type, connection_mode,
    environment, credentials.
    Optional: description.
    """
    errors: list[dict[str, str]] = []

    errors.extend(validate_source_name(payload.get("source_name", "")))

    source_type = payload.get("source_type", "")
    errors.extend(validate_source_type(source_type))

    connection_mode = payload.get("connection_mode", "")
    errors.extend(validate_connection_mode(connection_mode))

    errors.extend(validate_environment(payload.get("environment", "")))
    errors.extend(validate_description(payload.get("description")))

    # Credential structure only validated after source_type and mode are known
    if not errors or all(e["field"] not in ("source_type", "connection_mode") for e in errors):
        errors.extend(
            validate_credential_structure(
                source_type,
                payload.get("credentials"),
                connection_mode=connection_mode,
            )
        )

    return ValidationResult(errors=errors)
