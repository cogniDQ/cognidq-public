"""
File Upload Service

Handle file uploads with validation, parsing, and temporary storage.
"""

import io
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

from .parsers.base import ParseResult
from .parsers.csv_parser import CSVParser
from .parsers.excel_parser import ExcelParser
from .parsers.json_parser import JSONParser
from .parsers.parquet_parser import ParquetParser

settings = get_settings()

# Initialize MinIO client if using MinIO storage (connection deferred until first use)
minio_client = None
_minio_bucket_ensured = False
if settings.STORAGE_TYPE == "minio":
    try:
        from minio import Minio

        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    except ImportError:
        print("WARNING: minio package not installed. Install with: pip install minio")
        minio_client = None


def _ensure_minio_bucket() -> None:
    """Lazily ensure the MinIO bucket exists (called on first upload)."""
    global _minio_bucket_ensured
    if minio_client is not None and not _minio_bucket_ensured:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
        _minio_bucket_ensured = True


class FileUploadService:
    """Service for handling file uploads and parsing."""

    # Supported file formats
    SUPPORTED_FORMATS = {
        ".csv": "csv",
        ".txt": "csv",
        ".tsv": "csv",
        ".xlsx": "excel",
        ".xls": "excel",
        ".json": "json",
        ".jsonl": "json",
        ".parquet": "parquet",
    }

    # Maximum file size (100 MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self, upload_dir: str | None = None):
        """
        Initialize file upload service.

        Args:
            upload_dir: Directory to store uploaded files (temp storage)
        """
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR or "/tmp/dq_uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def validate_file(self, file: UploadFile) -> str:
        """
        Validate uploaded file format and size.

        Args:
            file: Uploaded file

        Returns:
            File type (csv, excel, json, parquet)

        Raises:
            HTTPException: If file is invalid
        """
        # Check file extension
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()

        if ext not in self.SUPPORTED_FORMATS:
            supported = ", ".join(self.SUPPORTED_FORMATS.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {ext}. Supported formats: {supported}",
            )

        return self.SUPPORTED_FORMATS[ext]

    async def save_upload(self, file: UploadFile) -> str:
        """
        Save uploaded file to storage (MinIO or local).

        Args:
            file: Uploaded file

        Returns:
            Path/key to saved file

        Raises:
            HTTPException: If file size exceeds limit
        """
        # Generate unique filename
        file_id = str(uuid.uuid4())
        ext = Path(file.filename or "").suffix.lower()
        original_filename = file.filename or f"file{ext}"
        filename = f"{file_id}{ext}"

        # Read file content to check size
        file_content = await file.read()
        total_size = len(file_content)

        if total_size > self.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum limit of {self.MAX_FILE_SIZE // (1024 * 1024)} MB",
            )

        # Save to MinIO or local storage
        if settings.STORAGE_TYPE == "minio" and minio_client:
            try:
                _ensure_minio_bucket()
                # Upload to MinIO with metadata
                minio_client.put_object(
                    settings.MINIO_BUCKET,
                    filename,
                    io.BytesIO(file_content),
                    length=total_size,
                    content_type=file.content_type or "application/octet-stream",
                    metadata={"original-filename": original_filename, "file-id": file_id},
                )
                return f"minio://{settings.MINIO_BUCKET}/{filename}"
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {str(e)}")
        else:
            # Save to local filesystem
            temp_path = self.upload_dir / filename
            with open(temp_path, "wb") as f:
                f.write(file_content)
            return str(temp_path)

    def get_file_stream(self, file_path: str) -> BinaryIO:
        """
        Get file stream from storage (MinIO or local).

        Args:
            file_path: File path or MinIO key

        Returns:
            File-like object
        """
        if file_path.startswith("minio://"):
            # Extract bucket and object name
            path_parts = file_path.replace("minio://", "").split("/", 1)
            bucket = path_parts[0]
            object_name = path_parts[1]

            # Get file from MinIO
            response = minio_client.get_object(bucket, object_name)
            return io.BytesIO(response.read())
        else:
            # Local file
            return open(file_path, "rb")

    def parse_file(self, file_path: str, file_type: str, original_filename: str) -> ParseResult:
        """
        Parse uploaded file based on its type.

        Args:
            file_path: Path to saved file or MinIO key
            file_type: File type (csv, excel, json, parquet)
            original_filename: Original filename

        Returns:
            ParseResult with data and metadata

        Raises:
            ValueError: If parsing fails
        """
        with self.get_file_stream(file_path) as f:
            if file_type == "csv":
                parser = CSVParser()
                return parser.parse(f, original_filename)
            elif file_type == "excel":
                parser = ExcelParser()
                return parser.parse(f, original_filename)
            elif file_type == "json":
                parser = JSONParser()
                return parser.parse(f, original_filename)
            elif file_type == "parquet":
                parser = ParquetParser()
                return parser.parse(f, original_filename)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

    async def upload_and_parse(self, file: UploadFile) -> dict[str, Any]:
        """
        Upload and parse file in one operation.

        Args:
            file: Uploaded file

        Returns:
            Dictionary with parse results and file info

        Raises:
            HTTPException: If upload or parsing fails
        """
        # Validate file
        file_type = self.validate_file(file)

        # Save file
        file_path = await self.save_upload(file)

        try:
            # Parse file
            result = self.parse_file(file_path, file_type, file.filename or "")

            # Return results
            return {
                "file_id": Path(file_path).stem,
                "file_path": file_path,
                "original_filename": file.filename,
                "file_type": file_type,
                **result.to_dict(),
            }

        except Exception as e:
            # Clean up file on error
            Path(file_path).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    def cleanup_file(self, file_path: str) -> None:
        """
        Delete file from storage (MinIO or local).

        Args:
            file_path: Path to file or MinIO key to delete
        """
        try:
            if file_path.startswith("minio://"):
                # Extract bucket and object name
                path_parts = file_path.replace("minio://", "").split("/", 1)
                bucket = path_parts[0]
                object_name = path_parts[1]
                # Delete from MinIO
                if minio_client:
                    minio_client.remove_object(bucket, object_name)
            else:
                # Delete local file
                Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass  # Ignore cleanup errors

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up old temporary files.

        Args:
            max_age_hours: Maximum age of files to keep (in hours)

        Returns:
            Number of files deleted
        """
        import time

        deleted = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        for file_path in self.upload_dir.glob("*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        deleted += 1
                    except Exception:
                        pass

        return deleted
