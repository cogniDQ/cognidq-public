"""
JSON utilities for sanitizing data before database storage
"""

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def sanitize_for_json(data: Any) -> Any:
    """
    Recursively sanitize data for JSON serialization.

    Handles:
    - NaN, Infinity -> None
    - Decimal -> float
    - datetime/date -> ISO string
    - UUID -> string
    - bytes/memoryview -> None
    - Recursive processing of dicts and lists

    Args:
        data: Data to sanitize

    Returns:
        Sanitized data safe for JSON serialization
    """
    if data is None:
        return None

    # Handle float special values (NaN, Infinity)
    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data

    # Handle Decimal
    if isinstance(data, Decimal):
        # Convert to float first to check for special values
        float_val = float(data)
        if math.isnan(float_val) or math.isinf(float_val):
            return None
        return float_val

    # Handle datetime/date
    if isinstance(data, (datetime, date)):
        return data.isoformat()

    # Handle UUID
    if isinstance(data, UUID):
        return str(data)

    # Handle bytes/memoryview (not JSON serializable)
    if isinstance(data, (bytes, bytearray, memoryview)):
        return None

    # Handle dictionaries recursively
    if isinstance(data, dict):
        return {key: sanitize_for_json(value) for key, value in data.items()}

    # Handle lists/tuples recursively
    if isinstance(data, (list, tuple)):
        return [sanitize_for_json(item) for item in data]

    # Return all other types as-is
    return data


def sanitize_result_data(result_data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize result_data dictionary before storing to database.

    This is a convenience wrapper around sanitize_for_json specifically
    for node result data.

    Args:
        result_data: Result data dictionary

    Returns:
        Sanitized result data dictionary
    """
    return sanitize_for_json(result_data)
