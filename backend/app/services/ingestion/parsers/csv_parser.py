"""
CSV Parser

Parse CSV files with automatic encoding detection and type inference.
"""

import time
from typing import BinaryIO

import chardet
import pandas as pd

from .base import BaseParser, ParseResult


class CSVParser(BaseParser):
    """Parser for CSV files."""

    def __init__(
        self,
        max_sample_size: int = 10000,
        delimiter: str | None = None,
        encoding: str | None = None,
    ):
        super().__init__(max_sample_size)
        self.delimiter = delimiter
        self.encoding = encoding

    def detect_encoding(self, file: BinaryIO) -> str:
        """
        Detect file encoding using chardet.

        Args:
            file: Binary file object

        Returns:
            Detected encoding (e.g., 'utf-8', 'latin-1')
        """
        # Read first 10KB for detection
        raw_data = file.read(10240)
        file.seek(0)  # Reset file pointer

        result = chardet.detect(raw_data)
        encoding = result.get("encoding", "utf-8")

        # Fallback to utf-8 if detection fails
        if not encoding or result.get("confidence", 0) < 0.7:
            encoding = "utf-8"

        return encoding

    def detect_delimiter(self, file: BinaryIO, encoding: str) -> str:
        """
        Detect CSV delimiter by trying common delimiters.

        Args:
            file: Binary file object
            encoding: File encoding

        Returns:
            Detected delimiter (default: ',')
        """
        # Read first few lines
        sample = file.read(4096).decode(encoding, errors="ignore")
        file.seek(0)

        # Try common delimiters
        delimiters = [",", ";", "\t", "|"]
        delimiter_counts = {}

        for delim in delimiters:
            count = sample.count(delim)
            if count > 0:
                delimiter_counts[delim] = count

        if delimiter_counts:
            # Return delimiter with highest count
            return max(delimiter_counts, key=delimiter_counts.get)

        return ","  # Default to comma

    def parse(self, file: BinaryIO, filename: str) -> ParseResult:
        """
        Parse CSV file with automatic encoding and delimiter detection.

        Args:
            file: Binary file object
            filename: Original filename

        Returns:
            ParseResult with parsed data and metadata
        """
        start_time = time.time()

        # Get file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        # Detect encoding if not provided
        encoding = self.encoding
        if not encoding:
            encoding = self.detect_encoding(file)

        # Detect delimiter if not provided
        delimiter = self.delimiter
        if not delimiter:
            delimiter = self.detect_delimiter(file, encoding)

        try:
            # First, count total rows efficiently
            file.seek(0)
            total_rows = sum(1 for _ in file) - 1  # Subtract header row
            file.seek(0)

            # Parse CSV sample for profiling
            df = pd.read_csv(
                file,
                encoding=encoding,
                delimiter=delimiter,
                nrows=self.max_sample_size,
                on_bad_lines="skip",
                engine="python",  # More flexible parser
            )

            # Handle empty DataFrame
            if df.empty:
                raise ValueError("CSV file is empty or could not be parsed")

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
                row_count=total_rows,  # Use actual row count, not sample size
                file_size=file_size,
                encoding=encoding,
                parse_time=parse_time,
            )

        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")
