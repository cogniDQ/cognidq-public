"""
Base Parser Interface

Abstract base class for all file parsers.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, BinaryIO

import numpy as np
import pandas as pd


class ColumnMetadata:
    """Metadata about a column in the parsed file."""

    def __init__(
        self,
        name: str,
        inferred_type: str,
        nullable: bool = True,
        sample_values: list[Any] | None = None,
        null_count: int = 0,
        unique_count: int | None = None,
    ):
        self.name = name
        self.inferred_type = inferred_type
        self.nullable = nullable
        self.sample_values = sample_values or []
        self.null_count = null_count
        self.unique_count = unique_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inferred_type": self.inferred_type,
            "nullable": bool(self.nullable),  # Ensure Python bool
            "sample_values": self.sample_values,
            "null_count": int(self.null_count),  # Ensure Python int
            "unique_count": int(self.unique_count) if self.unique_count is not None else None,
        }


class ParseResult:
    """Result of parsing a file."""

    def __init__(
        self,
        data: pd.DataFrame,
        columns: list[ColumnMetadata],
        row_count: int,
        file_size: int,
        encoding: str | None = None,
        parse_time: float | None = None,
    ):
        self.data = data
        self.columns = columns
        self.row_count = row_count
        self.file_size = file_size
        self.encoding = encoding
        self.parse_time = parse_time

    def to_dict(self) -> dict[str, Any]:
        # Convert DataFrame to dict, replacing NaN/Inf with None
        sample_df = self.data.head(100)
        # Replace NaN and Inf values with None
        sample_df = sample_df.replace([np.nan, np.inf, -np.inf], None)
        sample_data = sample_df.to_dict(orient="records")

        return {
            "columns": [col.to_dict() for col in self.columns],
            "row_count": self.row_count,
            "file_size": self.file_size,
            "encoding": self.encoding,
            "parse_time": self.parse_time,
            "sample_data": sample_data,
        }


class BaseParser(ABC):
    """Abstract base class for file parsers."""

    def __init__(self, max_sample_size: int = 10000):
        self.max_sample_size = max_sample_size

    @abstractmethod
    def parse(self, file: BinaryIO, filename: str) -> ParseResult:
        """
        Parse a file and return structured data with metadata.

        Args:
            file: File-like object to parse
            filename: Original filename

        Returns:
            ParseResult with data and metadata
        """
        pass

    def infer_column_type(self, series: pd.Series) -> str:
        """
        Infer the data type of a pandas Series.

        Returns:
            One of: integer, float, boolean, date, datetime, string
        """
        # Check for numeric types
        if pd.api.types.is_integer_dtype(series):
            return "integer"
        elif pd.api.types.is_float_dtype(series):
            return "float"
        elif pd.api.types.is_bool_dtype(series):
            return "boolean"
        elif pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"

        # For object types, try to infer more specific types
        if series.dtype == "object":
            # Sample non-null values
            non_null = series.dropna()
            if len(non_null) == 0:
                return "string"

            sample = non_null.head(100)

            # Try to parse as datetime
            try:
                pd.to_datetime(sample, errors="raise")
                return "datetime"
            except (ValueError, TypeError):
                pass

            # Check if all values are boolean-like
            if sample.isin(
                ["true", "false", "True", "False", "TRUE", "FALSE", "1", "0", 1, 0]
            ).all():
                return "boolean"

            # Check if all values are numeric
            try:
                numeric = pd.to_numeric(sample, errors="raise")
                if (numeric % 1 == 0).all():
                    return "integer"
                return "float"
            except (ValueError, TypeError):
                pass

        return "string"

    def create_column_metadata(self, df: pd.DataFrame) -> list[ColumnMetadata]:
        """
        Create metadata for all columns in the DataFrame.

        Args:
            df: Parsed DataFrame

        Returns:
            List of ColumnMetadata objects
        """
        metadata = []

        for column in df.columns:
            series = df[column]

            # Get basic stats
            null_count = int(series.isna().sum())  # Convert numpy int to Python int
            nullable = bool(null_count > 0)  # Convert numpy bool to Python bool
            unique_count = int(series.nunique())  # Convert numpy int to Python int

            # Get sample values (non-null, unique)
            sample_values = series.dropna().unique()[:5].tolist()

            # Convert to native Python types for JSON serialization
            sample_values = [self._convert_to_native_type(val) for val in sample_values]

            metadata.append(
                ColumnMetadata(
                    name=str(column),
                    inferred_type=self.infer_column_type(series),
                    nullable=nullable,
                    sample_values=sample_values,
                    null_count=null_count,
                    unique_count=unique_count,
                )
            )

        return metadata

    def _convert_to_native_type(self, val: Any) -> Any:
        """Convert pandas/numpy types to native Python types."""
        if pd.isna(val):
            return None
        if isinstance(val, (pd.Timestamp, datetime)):
            return val.isoformat()
        if isinstance(val, (np.bool_, bool)):
            return bool(val)
        if isinstance(val, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(val)
        if isinstance(val, (np.floating, np.float64, np.float32, np.float16)):
            float_val = float(val)
            # Handle NaN and Inf values
            if np.isnan(float_val) or np.isinf(float_val):
                return None
            return float_val
        if hasattr(val, "item"):  # other numpy types
            return val.item()
        return val
