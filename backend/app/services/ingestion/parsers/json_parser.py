"""
JSON Parser

Parse JSON and JSONL (JSON Lines) files.
"""

import json
import time
from typing import BinaryIO

import pandas as pd

from .base import BaseParser, ParseResult


class JSONParser(BaseParser):
    """Parser for JSON and JSONL files."""

    def __init__(self, max_sample_size: int = 10000, is_lines: bool = False):
        super().__init__(max_sample_size)
        self.is_lines = is_lines

    def parse(self, file: BinaryIO, filename: str) -> ParseResult:
        """
        Parse JSON or JSONL file.

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
            # Auto-detect if file is JSONL based on extension
            is_lines = self.is_lines or filename.endswith(".jsonl")

            # Read and parse JSON
            content = file.read().decode("utf-8")

            if is_lines:
                # Parse JSONL (one JSON object per line)
                records = []
                for i, line in enumerate(content.strip().split("\n")):
                    if i >= self.max_sample_size:
                        break
                    if line.strip():
                        records.append(json.loads(line))
                df = pd.DataFrame(records)
            else:
                # Parse regular JSON
                data = json.loads(content)

                # Handle different JSON structures
                if isinstance(data, list):
                    df = pd.DataFrame(data[: self.max_sample_size])
                elif isinstance(data, dict):
                    # If dict contains a list, use that
                    list_keys = [k for k, v in data.items() if isinstance(v, list)]
                    if list_keys:
                        # Use the first list found
                        df = pd.DataFrame(data[list_keys[0]][: self.max_sample_size])
                    else:
                        # Convert single dict to single-row DataFrame
                        df = pd.DataFrame([data])
                else:
                    raise ValueError("JSON must be an array or object")

            # Handle empty DataFrame
            if df.empty:
                raise ValueError("JSON file is empty or could not be parsed")

            # Create column metadata
            columns = self.create_column_metadata(df)

            # Calculate parse time
            parse_time = time.time() - start_time

            return ParseResult(
                data=df,
                columns=columns,
                row_count=len(df),
                file_size=file_size,
                encoding="utf-8",
                parse_time=parse_time,
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to parse JSON file: {str(e)}")
