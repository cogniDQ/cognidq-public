"""
Excel Parser

Parse Excel files (.xlsx, .xls) with sheet detection.
"""

import time
from typing import BinaryIO

import pandas as pd

from .base import BaseParser, ParseResult


class ExcelParser(BaseParser):
    """Parser for Excel files."""

    def __init__(self, max_sample_size: int = 10000, sheet_name: str | None = None):
        super().__init__(max_sample_size)
        self.sheet_name = sheet_name or 0  # Default to first sheet

    def parse(self, file: BinaryIO, filename: str) -> ParseResult:
        """
        Parse Excel file.

        Args:
            file: Binary file object
            filename: Original filename

        Returns:
            ParseResult with parsed data and metadata
        """
        start_time = time.time()

        # Get file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        try:
            # Determine engine based on file extension
            engine = "openpyxl" if filename.endswith(".xlsx") else "xlrd"

            # Read Excel file
            df = pd.read_excel(
                file, sheet_name=self.sheet_name, nrows=self.max_sample_size, engine=engine
            )

            # Handle empty DataFrame
            if df.empty:
                raise ValueError("Excel file is empty or could not be parsed")

            # Treat empty / whitespace-only strings as NULL so completeness checks
            # correctly count them as missing values.
            # Use cell-wise processing to avoid col.str.strip() returning NaN for
            # non-string cells (e.g. integers in mixed-type object columns).
            def _normalize_cell(x):
                if isinstance(x, str):
                    stripped = x.strip()
                    return None if stripped == "" else stripped
                return x  # leave numbers, None, NaN untouched

            for col_name in df.select_dtypes(include="object").columns:
                df[col_name] = df[col_name].apply(_normalize_cell)

            # Create column metadata
            columns = self.create_column_metadata(df)

            # Calculate parse time
            parse_time = time.time() - start_time

            return ParseResult(
                data=df,
                columns=columns,
                row_count=len(df),
                file_size=file_size,
                encoding=None,
                parse_time=parse_time,
            )

        except Exception as e:
            raise ValueError(f"Failed to parse Excel file: {str(e)}")
