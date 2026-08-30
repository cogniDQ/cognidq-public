"""
F004 — Data Source API error helpers
======================================

Defines ``DataSourceAPIError`` and the exception handler registered
with the FastAPI application.  Error envelope follows the same shape
used by F002/F003:

    {"error": {"code": str, "message": str, "fields": list | null}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DataSourceAPIError(Exception):
    """
    Structured HTTP error for data source endpoints.

    Follows the project-wide error envelope:
        {"error": {"code": str, "message": str, "fields": list | null}}
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


async def data_source_api_error_handler(request, exc: DataSourceAPIError) -> JSONResponse:
    """FastAPI exception handler for DataSourceAPIError."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "fields": exc.fields,
            }
        },
    )
