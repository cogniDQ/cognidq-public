"""
F005 — Dataset API error helpers
===================================

Defines ``DatasetAPIError`` and the exception handler following the
same error envelope pattern as F004.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# F-CONN-CORE — error codes aligned with spec §13.4
DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
DATASET_ACCESS_DENIED = "DATASET_ACCESS_DENIED"
DATASET_EMPTY = "DATASET_EMPTY"
DATASET_PREVIEW_FAILED = "DATASET_PREVIEW_FAILED"
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
FILE_PARSE_ERROR = "FILE_PARSE_ERROR"
CHECK_EXECUTION_FAILED = "CHECK_EXECUTION_FAILED"


class DatasetAPIError(Exception):
    """
    Structured HTTP error for dataset endpoints.

    Envelope: {"error": {"code": str, "message": str, "fields": list | null}}
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


class DatasetNotFoundError(Exception):
    """Raised when no dataset with the given ID exists in the workspace."""


class DatasetFieldNotFoundError(Exception):
    """Raised when no dataset field with the given ID exists."""


class DuplicateDatasetNameError(Exception):
    """Raised when dataset_name (case-insensitive) already exists in workspace."""


class DuplicatePhysicalIdentifierError(Exception):
    """Raised when physical_identifier already exists for this data source (non-archived)."""


class DuplicateFieldNameError(Exception):
    """Raised when field_name (case-insensitive) already exists in dataset."""


class InvalidStatusTransitionError(Exception):
    """Raised when a status transition is not allowed."""


class DataSourceNotActiveError(Exception):
    """Raised when a dataset operation requires the data source to be active."""


async def dataset_api_error_handler(request, exc: DatasetAPIError) -> JSONResponse:
    """FastAPI exception handler for DatasetAPIError."""
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
