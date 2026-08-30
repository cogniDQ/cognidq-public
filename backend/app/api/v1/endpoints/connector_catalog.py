"""
F-CONN-CORE — Connector Catalog endpoints.

Read-only endpoints that expose the connector registry to the frontend so the
catalog and credential-form renderer can be driven by data instead of
hard-coded source-type branches.

Routes:
    GET  /api/v1/connectors                 — list all connector specs (filterable)
    GET  /api/v1/connectors/{type}          — single connector spec

Auth: any authenticated user (catalog is non-sensitive metadata, but we still
require a valid JWT to avoid unauthenticated catalog scraping).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    get_actor_context,
)
from app.services.datasources.connectors.registry import (
    ConnectorCategory,
    ConnectorPriority,
    ConnectorStatus,
    registry,
)

router = APIRouter(
    prefix="/connectors",
    tags=["connectors"],
)


def _parse_enum(value: str | None, enum_cls, field_name: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(e.value for e in enum_cls)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}. Must be one of: {valid}",
        )


@router.get("", status_code=status.HTTP_200_OK)
async def list_connectors(
    category: str | None = Query(None, description="Filter by category."),
    priority: str | None = Query(None, description="Filter by priority (P0/P1)."),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by lifecycle status.",
    ),
    local_only: bool | None = Query(
        None,
        description="If true, only locally testable connectors. If false, only cloud-required.",
    ),
    actor: ActorContext = Depends(get_actor_context),
):
    """List all known connectors, optionally filtered."""
    cat = _parse_enum(category, ConnectorCategory, "category")
    pri = _parse_enum(priority, ConnectorPriority, "priority")
    sta = _parse_enum(status_filter, ConnectorStatus, "status")

    specs = registry.list(
        category=cat,
        priority=pri,
        status=sta,
        local_only=local_only,
    )
    return {"items": [s.to_dict() for s in specs], "total": len(specs)}


@router.get("/{connector_type}", status_code=status.HTTP_200_OK)
async def get_connector(
    connector_type: str,
    actor: ActorContext = Depends(get_actor_context),
):
    """Return a single connector spec by type id."""
    spec = registry.get(connector_type)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "UNKNOWN_CONNECTOR_TYPE",
                    "message": f"Unknown connector type: {connector_type!r}",
                    "fields": None,
                }
            },
        )
    return spec.to_dict()
