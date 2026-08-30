"""
Batch Ingestion Service

Handle scheduled batch imports, incremental loads, and data deduplication.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestionJob, IngestionJobStatus

from .file_upload import FileUploadService
from .profiler import DataProfiler


class BatchIngestionService:
    """Service for batch data ingestion."""

    def __init__(self):
        self.file_service = FileUploadService()
        self.profiler = DataProfiler()

    async def create_ingestion_job(
        self,
        db: AsyncSession,
        data_source_id: str,
        workspace_id: str,
        file_path: str,
        target_table: str,
        mode: str = "append",  # append, replace, upsert
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new ingestion job.

        Args:
            db: Database session
            data_source_id: ID of target data source
            workspace_id: Organization ID
            file_path: Path to file to ingest
            target_table: Target table name
            mode: Ingestion mode (append, replace, upsert)
            created_by: User ID who created the job

        Returns:
            Created job details
        """
        job = IngestionJob(
            id=str(uuid.uuid4()),
            data_source_id=data_source_id,
            workspace_id=workspace_id,
            file_path=file_path,
            target_table=target_table,
            mode=mode,
            status=IngestionJobStatus.PENDING,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )

        db.add(job)
        await db.commit()
        await db.refresh(job)

        return {
            "id": job.id,
            "data_source_id": job.data_source_id,
            "target_table": job.target_table,
            "mode": job.mode,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
        }

    async def get_ingestion_job(
        self, db: AsyncSession, job_id: str, workspace_id: str
    ) -> dict[str, Any] | None:
        """
        Get ingestion job details.

        Args:
            db: Database session
            job_id: Job ID
            workspace_id: Organization ID

        Returns:
            Job details or None
        """
        result = await db.execute(
            select(IngestionJob).where(
                and_(IngestionJob.id == job_id, IngestionJob.workspace_id == workspace_id)
            )
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        return {
            "id": job.id,
            "data_source_id": job.data_source_id,
            "target_table": job.target_table,
            "mode": job.mode,
            "status": job.status,
            "total_rows": job.total_rows,
            "processed_rows": job.processed_rows,
            "failed_rows": job.failed_rows,
            "error_message": job.error_message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat(),
        }

    async def list_ingestion_jobs(
        self,
        db: AsyncSession,
        workspace_id: str,
        data_source_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List ingestion jobs.

        Args:
            db: Database session
            workspace_id: Organization ID
            data_source_id: Optional filter by data source
            status: Optional filter by status
            limit: Maximum number of jobs to return

        Returns:
            List of jobs
        """
        query = select(IngestionJob).where(IngestionJob.workspace_id == workspace_id)

        if data_source_id:
            query = query.where(IngestionJob.data_source_id == data_source_id)

        if status:
            query = query.where(IngestionJob.status == status)

        query = query.order_by(IngestionJob.created_at.desc()).limit(limit)

        result = await db.execute(query)
        jobs = result.scalars().all()

        return [
            {
                "id": job.id,
                "data_source_id": job.data_source_id,
                "target_table": job.target_table,
                "mode": job.mode,
                "status": job.status,
                "total_rows": job.total_rows,
                "processed_rows": job.processed_rows,
                "failed_rows": job.failed_rows,
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ]

    async def process_job(self, db: AsyncSession, job_id: str, workspace_id: str) -> dict[str, Any]:
        """
        Process an ingestion job.

        This would typically be called by a Celery worker.

        Args:
            db: Database session
            job_id: Job ID
            workspace_id: Organization ID

        Returns:
            Job results
        """
        # Get job
        result = await db.execute(
            select(IngestionJob).where(
                and_(IngestionJob.id == job_id, IngestionJob.workspace_id == workspace_id)
            )
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job {job_id} not found")

        try:
            # Update status to running
            job.status = IngestionJobStatus.RUNNING
            job.started_at = datetime.utcnow()
            await db.commit()

            # Parse file
            # Determine file type from extension
            from pathlib import Path

            ext = Path(job.file_path).suffix.lower()
            file_type_map = {
                ".csv": "csv",
                ".txt": "csv",
                ".tsv": "csv",
                ".xlsx": "excel",
                ".xls": "excel",
                ".json": "json",
                ".jsonl": "json",
                ".parquet": "parquet",
            }
            file_type = file_type_map.get(ext, "csv")

            parse_result = self.file_service.parse_file(
                job.file_path, file_type, job.file_path.split("/")[-1]
            )

            # Profile data
            profile = self.profiler.profile_dataframe(parse_result.data)

            # Update job with totals
            job.total_rows = parse_result.row_count
            job.processed_rows = parse_result.row_count
            job.meta_data = {
                "profile": profile,
                "columns": [col.to_dict() for col in parse_result.columns],
            }

            # Mark as completed
            job.status = IngestionJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            await db.commit()

            return {
                "id": job.id,
                "status": job.status,
                "total_rows": job.total_rows,
                "processed_rows": job.processed_rows,
                "profile": profile,
            }

        except Exception as e:
            # Mark as failed
            job.status = IngestionJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()

            raise

    async def cancel_job(self, db: AsyncSession, job_id: str, workspace_id: str) -> dict[str, Any]:
        """
        Cancel a running ingestion job.

        Args:
            db: Database session
            job_id: Job ID
            workspace_id: Organization ID

        Returns:
            Updated job details
        """
        result = await db.execute(
            select(IngestionJob).where(
                and_(IngestionJob.id == job_id, IngestionJob.workspace_id == workspace_id)
            )
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in [IngestionJobStatus.PENDING, IngestionJobStatus.RUNNING]:
            raise ValueError(f"Cannot cancel job in status: {job.status}")

        job.status = IngestionJobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        await db.commit()

        return {"id": job.id, "status": job.status, "completed_at": job.completed_at.isoformat()}
