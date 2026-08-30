"""
F134 P04 — Public demo request endpoints (unauthenticated)

Routes:
    POST   /api/v1/demo-requests
    GET    /api/v1/demo-request-status/{public_status_token}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services.sandbox.demo_request_service import (
    DemoRequestService,
    emit_request_received_email,
)
from app.services.sandbox.validation.demo_request_validation import validate_demo_request

router = APIRouter(tags=["demo-sandbox-public"])


# ── helpers ────────────────────────────────────────────────────────────────────


def _validation_error_response(errors) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "fields": [{"field": f, "message": m} for f, m in errors],
            }
        },
    )


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── POST /api/v1/demo-requests ─────────────────────────────────────────────────


@router.post("/demo-requests", status_code=status.HTTP_201_CREATED)
def create_demo_request(
    body: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Public unauthenticated endpoint for prospect demo requests.

    Returns:
        201 Created  — new request accepted
        200 OK       — duplicate active request (status="duplicate")
        422          — validation errors
    """
    # --- field validation (pure, DB-free) ---
    errors = validate_demo_request(
        work_email=body.get("work_email", ""),
        first_name=body.get("first_name", ""),
        last_name=body.get("last_name", ""),
        company_name=body.get("company_name", ""),
        team_size=body.get("team_size", ""),
        primary_use_case=body.get("primary_use_case", ""),
        consent=body.get("consent", False),
        country=body.get("country"),
    )
    if errors:
        return _validation_error_response(errors)

    svc = DemoRequestService(db)

    # --- BR-001 duplicate check ---
    existing = svc.find_active_by_email(body["work_email"].strip())
    if existing:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "duplicate",
                "request_id": str(existing["id"]),
            },
        )

    # --- create ---
    row = svc.create(
        work_email=body["work_email"].strip(),
        first_name=body["first_name"].strip(),
        last_name=body["last_name"].strip(),
        company_name=body["company_name"].strip(),
        team_size=body["team_size"],
        primary_use_case=body["primary_use_case"].strip(),
        consent=body["consent"],
        job_title=body.get("job_title"),
        country=body.get("country"),
        stack=body.get("stack"),
        heard_about_us=body.get("heard_about_us"),
        source_ip=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )

    # --- fire-and-forget email (stub for P04; wired in P08) ---
    emit_request_received_email(row)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "request_id": str(row["id"]),
            "public_status_token": row["public_status_token"],
            "status": row["status"],
            "is_personal_email": row["is_personal_email"],
        },
    )


# ── GET /api/v1/demo-request-status/{token} ────────────────────────────────────


@router.get("/demo-request-status/{public_status_token}", status_code=status.HTTP_200_OK)
def get_demo_request_status(
    public_status_token: str,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Anonymous status-poll endpoint.

    Returns 200 with status fields, or 404 if token is unknown.
    """
    svc = DemoRequestService(db)
    row = svc.get_status(public_status_token)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "request_id": str(row["id"]),
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "decided_at": row["decided_at"].isoformat() if row.get("decided_at") else None,
            "is_personal_email": row["is_personal_email"],
        },
    )
