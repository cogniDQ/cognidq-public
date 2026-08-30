"""
F001 — Correlation ID + Structured Request Logging Middleware  (Packet 9)
==========================================================================

Implements TDD §8.2.

Responsibilities
-----------------
1. **Correlation ID generation** — A UUID v4 is generated *server-side* for
   every inbound request.  The ``X-Correlation-Id`` request header is
   intentionally *ignored*; callers cannot inject a correlation ID.

2. **Request-state injection** — The correlation ID is stored on
   ``request.state.correlation_id`` so any downstream handler or dependency
   can read it.

3. **Structured log emission** — On request completion a single INFO-level
   log entry is emitted containing all fields mandated by TDD §8.2:
     ``correlation_id``, ``actor_id``, ``actor_role``, ``tenant_id``,
     ``operation``, ``outcome``, ``error_code``.
   Log emission failure is silently swallowed — it MUST NOT affect the
   HTTP response.

4. **Response header** — ``X-Correlation-Id: <uuid-v4>`` is appended to
   every HTTP response, regardless of status code.

5. **Unauthorized metric** — When ``POST /api/v1/tenants`` returns 401 or
   403 (auth guard rejected the request before the handler ran), the
   ``tenant_create_failure_count{failure_reason="unauthorized"}`` counter
   is incremented (fire-and-forget).

Security notes
--------------
* The JWT value is never read or written here.
* ``actor_id`` and ``actor_role`` are read from ``request.state.actor``
  which is set by ``get_actor_context`` only after the JWT is validated —
  the raw token string never touches this module.
* ``tenant_id`` is extracted from the URL path via a regex that only
  accepts the UUID v4 hex format; no user-controlled string is logged
  verbatim without sanitisation.
"""

from __future__ import annotations

import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.tenants.metrics import emit_tenant_create_failure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path / operation inference helpers
# ---------------------------------------------------------------------------

_TENANTS_BASE = "/api/v1/tenants"

# Pattern matching the UUID v4 segment in a URL path (case-insensitive hex)
_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"

# Ordered list of (compiled_key_regex, operation_name) pairs.
# The key is  "<METHOD> <path>".  Checked in order; first match wins.
_OPERATION_PATTERNS: list = [
    (
        re.compile(rf"^GET {re.escape(_TENANTS_BASE)}/{_UUID_PATTERN}/audit-logs$", re.I),
        "list_audit_logs",
    ),
    (
        re.compile(rf"^POST {re.escape(_TENANTS_BASE)}/{_UUID_PATTERN}/status$", re.I),
        "change_status",
    ),
    (re.compile(rf"^GET {re.escape(_TENANTS_BASE)}/{_UUID_PATTERN}$", re.I), "get_tenant_detail"),
    (re.compile(rf"^PATCH {re.escape(_TENANTS_BASE)}/{_UUID_PATTERN}$", re.I), "update_tenant"),
    (re.compile(rf"^POST {re.escape(_TENANTS_BASE)}$"), "create_tenant"),
    (re.compile(rf"^GET {re.escape(_TENANTS_BASE)}$"), "list_tenants"),
]

# Extracts the tenant UUID v4 from a path like /api/v1/tenants/<uuid>[/...]
_TENANT_ID_RE = re.compile(
    rf"/api/v1/tenants/({_UUID_PATTERN})(?:/|$)",
    re.I,
)


def _infer_operation(method: str, path: str) -> str:
    """Return a human-readable operation name for the request, or ``"unknown"``."""
    key = f"{method.upper()} {path}"
    for pattern, name in _OPERATION_PATTERNS:
        if pattern.match(key):
            return name
    return "unknown"


def _extract_tenant_id(path: str) -> str | None:
    """Return the UUID v4 tenant_id from ``path``, or ``None`` if absent."""
    m = _TENANT_ID_RE.search(path)
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Generate a UUID v4 correlation ID per request; emit structured logs.

    Safe for all response types used by F001 (``JSONResponse``).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ------------------------------------------------------------------
        # 1. Generate server-side correlation ID — NEVER read from headers
        # ------------------------------------------------------------------
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # ------------------------------------------------------------------
        # 2. Process the request pipeline (dependencies + handler)
        # ------------------------------------------------------------------
        response: Response = await call_next(request)

        # ------------------------------------------------------------------
        # 3. Fire unauthorized metric for tenant creation auth failures
        # ------------------------------------------------------------------
        if (
            request.method.upper() == "POST"
            and request.url.path == _TENANTS_BASE
            and response.status_code in (401, 403)
        ):
            try:
                emit_tenant_create_failure("unauthorized")
            except Exception:  # pragma: no cover
                pass

        # ------------------------------------------------------------------
        # 4. Emit structured per-request log (TDD §8.2) — fire-and-forget
        # ------------------------------------------------------------------
        try:
            actor = getattr(request.state, "actor", None)
            error_code: str | None = getattr(request.state, "error_code", None)
            tenant_id: str | None = (
                # Handlers may set request.state.log_tenant_id explicitly to
                # override the path-extraction heuristic.
                getattr(request.state, "log_tenant_id", None)
                or _extract_tenant_id(request.url.path)
            )
            operation = _infer_operation(request.method, request.url.path)
            outcome = "success" if response.status_code < 400 else "failure"

            logger.info(
                "request_completed  correlation_id=%s  actor_id=%s  actor_role=%s  "
                "tenant_id=%s  operation=%s  outcome=%s  error_code=%s  status=%s",
                correlation_id,
                str(actor.actor_id) if actor else "unauthenticated",
                actor.actor_role if actor else "none",
                tenant_id or "none",
                operation,
                outcome,
                error_code or "none",
                response.status_code,
            )
        except Exception:  # pragma: no cover
            # Structured log failure MUST NOT affect the HTTP response.
            pass

        # ------------------------------------------------------------------
        # 5. Append X-Correlation-Id to every response
        # ------------------------------------------------------------------
        response.headers["X-Correlation-Id"] = correlation_id
        return response
