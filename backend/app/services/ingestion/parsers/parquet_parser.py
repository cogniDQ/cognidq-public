"""
Parquet Parser

Parse Apache Parquet files.
"""

import time
from typing import BinaryIO

import pyarrow.parquet as pq

from .base import BaseParser, ParseResult


class ParquetParser(BaseParser):
    """Parser for Parquet files."""

    def parse(self, file: BinaryIO, filename: str) -> ParseResult:
        """
        Parse Parquet file.

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
            # Read Parquet file
            table = pq.read_table(file)

            # Convert to pandas DataFrame (with row limit)
            df = table.to_pandas()
            if len(df) > self.max_sample_size:
                df = df.head(self.max_sample_size)

            # Handle empty DataFrame
            if df.empty:
                raise ValueError("Parquet file is empty")

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
            raise ValueError(f"Failed to parse Parquet file: {str(e)}")
