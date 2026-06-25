"""Persistent job storage for fetch runs."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import settings
from app.schemas.product import JobStatus, ProductFetchResult

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    product_ids: list[str]
    results: list[ProductFetchResult] = field(default_factory=list)
    processed: int = 0
    success_count: int = 0
    partial_count: int = 0
    failed_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "total": len(self.product_ids),
            "processed": self.processed,
            "success_count": self.success_count,
            "partial_count": self.partial_count,
            "failed_count": self.failed_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    def to_document(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "product_ids": self.product_ids,
            "results": [result.model_dump() for result in self.results],
            "processed": self.processed,
            "success_count": self.success_count,
            "partial_count": self.partial_count,
            "failed_count": self.failed_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    @classmethod
    def from_document(cls, payload: dict[str, Any]) -> JobRecord:
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        completed_at = None
        if payload.get("completed_at"):
            completed_at = datetime.fromisoformat(payload["completed_at"])
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)

        results = [ProductFetchResult(**item) for item in payload.get("results", [])]
        return cls(
            job_id=payload["job_id"],
            status=JobStatus(payload["status"]),
            product_ids=payload.get("product_ids", []),
            results=results,
            processed=payload.get("processed", 0),
            success_count=payload.get("success_count", 0),
            partial_count=payload.get("partial_count", 0),
            failed_count=payload.get("failed_count", 0),
            created_at=created_at,
            completed_at=completed_at,
            error=payload.get("error"),
        )


class JobStore:
    """Thread-safe job registry with JSON file persistence."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._data_dir = data_dir or Path("data/jobs")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing_jobs()

    def _job_path(self, job_id: str) -> Path:
        return self._data_dir / f"{job_id}.json"

    def _load_existing_jobs(self) -> None:
        for path in self._data_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                job = JobRecord.from_document(payload)
                self._jobs[job.job_id] = job
            except Exception:
                logger.exception("Failed to load persisted job from %s", path)

    def _persist(self, job: JobRecord) -> None:
        path = self._job_path(job.job_id)
        path.write_text(json.dumps(job.to_document(), indent=2), encoding="utf-8")

    def create_job(self, product_ids: list[str]) -> JobRecord:
        job = JobRecord(job_id=str(uuid.uuid4()), status=JobStatus.PENDING, product_ids=product_ids)
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job

        path = self._job_path(job_id)
        if not path.exists():
            return None

        try:
            job = JobRecord.from_document(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            logger.exception("Failed to read job %s from disk", job_id)
            return None

        with self._lock:
            self._jobs[job_id] = job
        return job

    def update(self, job: JobRecord) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())

        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.to_summary() for job in jobs[:limit]]


job_store = JobStore()
