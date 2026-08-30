"""
F001 — List Tenants query transfer objects and parameter validation
===================================================================

Contains:
    ListTenantsQuery      — Immutable parameter set after parsing and validation.
    TenantListItemDTO     — Abbreviated 8-field tenant record for list responses.
    escape_ilike_term     — Escapes ILIKE metacharacters (%, _, \\) in a search term.
    parse_list_tenants_query — Validates raw query-parameter strings and produces a
                               ListTenantsQuery; raises TenantAPIError on violation.

Multi-value filtering note (MVP constraint):
    Only single-value filtering is supported.  When the caller supplies the same
    query parameter more than once (e.g. ``?status=active&status=draft``), FastAPI
    (with ``Optional[str]`` typing) forwards only the first value; subsequent
    values are silently ignored.  This is consistent behaviour and is documented
    here rather than in scattered handler code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.validators import VALID_PLANS, VALID_REGIONS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All four lifecycle statuses are valid filter values for the list endpoint.
VALID_STATUSES: frozenset[str] = frozenset({"draft", "active", "suspended", "archived"})

_VALID_SORT_FIELDS: frozenset[str] = frozenset({"created_at", "updated_at"})
_VALID_SORT_DIRS: frozenset[str] = frozenset({"asc", "desc"})

_DEFAULT_SORT_BY = "created_at"
_DEFAULT_SORT_DIR = "desc"
_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 100
_MIN_PAGE_SIZE = 1


# ---------------------------------------------------------------------------
# Transfer objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListTenantsQuery:
    """Validated and normalised query parameters for GET /api/v1/tenants."""

    status: str | None  # None = no filter; lowercase enum string when set
    region: str | None  # None = no filter
    plan: str | None  # None = no filter
    q: str | None  # None = no search; raw (not ILIKE-escaped); escaping in repo
    sort_by: str  # "created_at" | "updated_at"
    sort_dir: str  # "asc" | "desc"
    include_archived: bool  # False → exclude archived from data and meta.total
    page: int  # ≥ 1
    page_size: int  # 1–100


@dataclass(frozen=True)
class TenantListItemDTO:
    """Abbreviated 8-field tenant record returned in the list response (TDD §3.3)."""

    tenant_id: str
    tenant_name: str
    tenant_slug: str
    status: str
    region: str
    plan: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ILIKE metacharacter escaper (TDD §3.3 + packet task 3)
# ---------------------------------------------------------------------------


def escape_ilike_term(term: str) -> str:
    """Escape ILIKE metacharacters so they are treated as literals in PostgreSQL.

    PostgreSQL ILIKE uses ``\\`` as the default escape prefix.  Substitution
    order matters: the backslash itself must be replaced first.

    Args:
        term: Raw search string (may contain ``%``, ``_``, ``\\``).

    Returns:
        Escaped string suitable for embedding inside an ILIKE ``'%<term>%'``
        pattern with the default PostgreSQL escape character.

    Examples::

        escape_ilike_term("50% off")   # → "50\\% off"
        escape_ilike_term("a_b")       # → "a\\_b"
        escape_ilike_term("C:\\\\dir") # → "C:\\\\\\\\dir"
    """
    term = term.replace("\\", "\\\\")  # \ → \\   (must be first)
    term = term.replace("%", "\\%")  # % → \%
    term = term.replace("_", "\\_")  # _ → \_
    return term


# ---------------------------------------------------------------------------
# Query parameter parser / validator (TDD §3.3 + packet task 2)
# ---------------------------------------------------------------------------


def parse_list_tenants_query(
    *,
    status: str | None = None,
    region: str | None = None,
    plan: str | None = None,
    q: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    include_archived_str: str | None = None,
    page_str: str | None = None,
    page_size_str: str | None = None,
) -> ListTenantsQuery:
    """Parse and validate raw HTTP query-parameter strings.

    All semantic validation is performed here so the endpoint handler stays
    thin, and the validator can be unit-tested without an HTTP client.

    Raises:
        TenantAPIError(422, "invalid_sort_field"): ``sort_by`` is not in the
            allowed column set.
        TenantAPIError(422, "validation_error"): any other invalid parameter
            (non-integer type, out-of-range value, unrecognised enum value,
            invalid boolean string).
    """
    # ------------------------------------------------------------------
    # page — must be an integer ≥ 1 (TDD §3.3)
    # ------------------------------------------------------------------
    if page_str is None or page_str.strip() == "":
        page = _DEFAULT_PAGE
    else:
        try:
            page = int(page_str.strip())
        except ValueError:
            raise TenantAPIError(
                422,
                "validation_error",
                "page must be an integer.",
                [{"field": "page", "reason": "invalid_type"}],
            )
        if page < 1:
            raise TenantAPIError(
                422,
                "validation_error",
                "page must be \u2265 1.",
                [{"field": "page", "reason": "min_value"}],
            )

    # ------------------------------------------------------------------
    # page_size — integer from 1 to 100 inclusive (TDD §3.3)
    # ------------------------------------------------------------------
    if page_size_str is None or page_size_str.strip() == "":
        page_size = _DEFAULT_PAGE_SIZE
    else:
        try:
            page_size = int(page_size_str.strip())
        except ValueError:
            raise TenantAPIError(
                422,
                "validation_error",
                "page_size must be an integer.",
                [{"field": "page_size", "reason": "invalid_type"}],
            )
        if page_size < _MIN_PAGE_SIZE or page_size > _MAX_PAGE_SIZE:
            raise TenantAPIError(
                422,
                "validation_error",
                f"page_size must be between {_MIN_PAGE_SIZE} and {_MAX_PAGE_SIZE}.",
                [{"field": "page_size", "reason": "out_of_range"}],
            )

    # ------------------------------------------------------------------
    # sort_by — allowed values: created_at, updated_at (TDD §3.3)
    # ------------------------------------------------------------------
    if sort_by is None or sort_by.strip() == "":
        resolved_sort_by = _DEFAULT_SORT_BY
    else:
        resolved_sort_by = sort_by.strip().lower()
        if resolved_sort_by not in _VALID_SORT_FIELDS:
            raise TenantAPIError(
                422,
                "invalid_sort_field",
                f"sort_by must be one of: {', '.join(sorted(_VALID_SORT_FIELDS))}.",
            )

    # ------------------------------------------------------------------
    # sort_dir — allowed values: asc, desc (TDD §3.3)
    # ------------------------------------------------------------------
    if sort_dir is None or sort_dir.strip() == "":
        resolved_sort_dir = _DEFAULT_SORT_DIR
    else:
        resolved_sort_dir = sort_dir.strip().lower()
        if resolved_sort_dir not in _VALID_SORT_DIRS:
            raise TenantAPIError(
                422,
                "validation_error",
                "sort_dir must be 'asc' or 'desc'.",
                [{"field": "sort_dir", "reason": "invalid_value"}],
            )

    # ------------------------------------------------------------------
    # status filter — optional; must be a valid tenant_status_enum value
    # ------------------------------------------------------------------
    resolved_status: str | None = None
    if status is not None and status.strip():
        resolved_status = status.strip().lower()
        if resolved_status not in VALID_STATUSES:
            raise TenantAPIError(
                422,
                "validation_error",
                f"status must be one of: {', '.join(sorted(VALID_STATUSES))}.",
                [{"field": "status", "reason": "invalid_value"}],
            )

    # ------------------------------------------------------------------
    # region filter — optional; must be a valid tenant_region_enum value
    # ------------------------------------------------------------------
    resolved_region: str | None = None
    if region is not None and region.strip():
        resolved_region = region.strip().lower()
        if resolved_region not in VALID_REGIONS:
            raise TenantAPIError(
                422,
                "validation_error",
                f"region must be one of: {', '.join(sorted(VALID_REGIONS))}.",
                [{"field": "region", "reason": "invalid_value"}],
            )

    # ------------------------------------------------------------------
    # plan filter — optional; must be a valid tenant_plan_enum value
    # ------------------------------------------------------------------
    resolved_plan: str | None = None
    if plan is not None and plan.strip():
        resolved_plan = plan.strip().lower()
        if resolved_plan not in VALID_PLANS:
            raise TenantAPIError(
                422,
                "validation_error",
                f"plan must be one of: {', '.join(sorted(VALID_PLANS))}.",
                [{"field": "plan", "reason": "invalid_value"}],
            )

    # ------------------------------------------------------------------
    # q — optional full-text search term; whitespace-only → absent
    # ------------------------------------------------------------------
    resolved_q: str | None = None
    if q is not None:
        stripped_q = q.strip()
        if stripped_q:
            resolved_q = stripped_q  # raw value; ILIKE escaping is done in the repo

    # ------------------------------------------------------------------
    # include_archived — boolean string; default False
    # ------------------------------------------------------------------
    if include_archived_str is None or include_archived_str.strip() == "":
        include_archived = False
    else:
        lowered = include_archived_str.strip().lower()
        if lowered in ("true", "1"):
            include_archived = True
        elif lowered in ("false", "0"):
            include_archived = False
        else:
            raise TenantAPIError(
                422,
                "validation_error",
                "include_archived must be 'true' or 'false'.",
                [{"field": "include_archived", "reason": "invalid_value"}],
            )

    return ListTenantsQuery(
        status=resolved_status,
        region=resolved_region,
        plan=resolved_plan,
        q=resolved_q,
        sort_by=resolved_sort_by,
        sort_dir=resolved_sort_dir,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
    )
