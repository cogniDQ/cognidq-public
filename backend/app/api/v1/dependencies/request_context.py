"""
Request Context Utilities — F002 P04

Provides utilities for extracting and validating request context:
- Request ID from X-Request-ID header
- Source IP from X-Forwarded-For header

These are used for audit logging and distributed tracing.
"""

import ipaddress
import logging
import uuid

from fastapi import Header

logger = logging.getLogger(__name__)


def get_request_id(x_request_id: str | None = Header(None)) -> str:
    """
    Extract or generate request ID from X-Request-ID header.

    Rules (TDD §15 item 8, A-8):
    -  If header present and valid UUID format: use as-is
    - If header present but NOT valid UUID: silently discard and generate new UUID v4
    - If header absent: generate UUID v4

    Malformed correlation IDs are replaced, not rejected (no HTTP 400).

    Args:
        x_request_id: Value from X-Request-ID header (FastAPI injects)

    Returns:
        str: Valid UUID v4 string
    """
    if x_request_id:
        try:
            # Validate it's a proper UUID
            uuid.UUID(x_request_id)
            return x_request_id
        except ValueError:
            # Malformed UUID - silently generate new one
            logger.debug(f"Malformed X-Request-ID '{x_request_id}' discarded, generating new UUID")
            return str(uuid.uuid4())
    else:
        # No header - generate new UUID
        return str(uuid.uuid4())


def extract_source_ip(
    x_forwarded_for: str | None = Header(None), remote_addr: str | None = None
) -> str | None:
    """
    Extract source IP address from X-Forwarded-For header or remote address.

    Rules (TDD §15 item 6, MV-9):
    - Parse X-Forwarded-For header (comma-separated list)
    - Take first IP in list
    - Validate extracted value is valid IPv4 or IPv6
    - If validation fails (spoofed/malformed): return None (not arbitrary string)
    - Fall back to remote_addr when X-Forwarded-For absent
    - Return None for service-account calls without IP context

    Args:
        x_forwarded_for: Value from X-Forwarded-For header
        remote_addr: Remote address from connection (not from FastAPI Request since
                     we need this in dependency that runs before business logic)

    Returns:
        Optional[str]: Valid IP address string or None
    """
    ip_to_validate = None

    if x_forwarded_for:
        # Parse comma-separated list, take first IP
        ips = [ip.strip() for ip in x_forwarded_for.split(",")]
        if ips:
            ip_to_validate = ips[0]
    elif remote_addr:
        ip_to_validate = remote_addr

    if ip_to_validate:
        try:
            # Validate it's a proper IP address
            ipaddress.ip_address(ip_to_validate)
            return ip_to_validate
        except ValueError:
            # Malformed or spoofed IP - return None rather than storing arbitrary string
            logger.warning(f"Invalid IP address '{ip_to_validate}' rejected, storing None")
            return None

    # No IP context (e.g., service account call)
    return None


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID v4."""
    return uuid.uuid4()
