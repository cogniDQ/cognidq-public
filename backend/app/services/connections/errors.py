"""
F130 — ConnectionAPIError and error codes for the Connections service.
"""

from __future__ import annotations

# Error code constants
CONNECTION_NOT_FOUND = "CONNECTION_NOT_FOUND"
CONNECTION_IN_USE = "CONNECTION_IN_USE"
DUPLICATE_CONNECTION_NAME = "DUPLICATE_CONNECTION_NAME"
IMMUTABLE_FIELD = "IMMUTABLE_FIELD"
FORBIDDEN = "FORBIDDEN"
INVALID_WORKSPACE = "INVALID_WORKSPACE"

# F-CONN-CORE — codes aligned with full_p0_p1_structured_data_connections_spec §13.4
CONNECTION_AUTH_FAILED = "CONNECTION_AUTH_FAILED"
CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
CONNECTION_NETWORK_ERROR = "CONNECTION_NETWORK_ERROR"
CONNECTION_PERMISSION_DENIED = "CONNECTION_PERMISSION_DENIED"
CONNECTION_INVALID_CONFIG = "CONNECTION_INVALID_CONFIG"
UNKNOWN_CONNECTOR_TYPE = "UNKNOWN_CONNECTOR_TYPE"
RBAC_FORBIDDEN = "RBAC_FORBIDDEN"
TENANT_ISOLATION_VIOLATION = "TENANT_ISOLATION_VIOLATION"


class ConnectionAPIError(Exception):
    """Structured error for Connections API responses.

    Serialized by the exception handler as:
        {"error": {"code": "...", "message": "...", "fields": [...]}}
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: list | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
