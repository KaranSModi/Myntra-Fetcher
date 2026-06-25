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
