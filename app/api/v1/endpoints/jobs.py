"""Job endpoints for CSV upload and result retrieval."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.product import JobResponse, JobStatus
from app.services.fetch_service import fetch_service
from app.services.job_store import job_store

router = APIRouter()


@router.get("", response_model=JobResponse)
async def list_jobs(limit: int = 20) -> JobResponse:
    """Return recently saved fetch jobs."""
    jobs = job_store.list_jobs(limit=limit)
    return JobResponse(
        message="Jobs listed.",
        data={"jobs": jobs},
        meta={"count": len(jobs)},
    )


@router.post("", response_model=JobResponse)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> JobResponse:
    """Upload a CSV file and start an asynchronous fetch job."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = await file.read()
    try:
        product_ids, warnings = fetch_service.parse_product_ids(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_store.create_job(product_ids)
    background_tasks.add_task(fetch_service.process_job, job.job_id)

    return JobResponse(
        message="Fetch job created.",
        data={"job": job.to_summary()},
        errors=warnings,
        meta={"poll_url": f"/api/v1/jobs/{job.job_id}"},
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Return job status and results."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobResponse(
        message="Job fetched.",
        data={
            "job": job.to_summary(),
            "results": [result.model_dump() for result in job.results],
        },
    )


@router.post("/{job_id}/retry-failed", response_model=JobResponse)
async def retry_failed_products(
    job_id: str,
    background_tasks: BackgroundTasks,
    include_partial: bool = True,
) -> JobResponse:
    """Re-fetch failed (and optionally partial) products for a completed job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running.")
    if job.status == JobStatus.PENDING:
        raise HTTPException(status_code=409, detail="Job has not finished its initial run yet.")

    retriable_count = fetch_service.count_retriable_products(job, include_partial=include_partial)
    if retriable_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No failed or partial products are available to retry.",
        )

    background_tasks.add_task(fetch_service.retry_failed_products, job_id, include_partial=include_partial)

    return JobResponse(
        message="Retry started for failed products.",
        data={"job": job.to_summary()},
        meta={
            "poll_url": f"/api/v1/jobs/{job_id}",
            "retriable_count": retriable_count,
            "include_partial": include_partial,
        },
    )


@router.get("/{job_id}/download")
async def download_job(job_id: str) -> JSONResponse:
    """Download the full job output as JSON."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in {JobStatus.COMPLETED, JobStatus.FAILED}:
        raise HTTPException(status_code=409, detail="Job is still running.")

    payload: dict[str, Any] = {
        "job": job.to_summary(),
        "results": [result.model_dump() for result in job.results],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="myntra-fetch-{job_id}.json"'},
    )
