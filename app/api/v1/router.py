"""API v1 routes."""

from fastapi import APIRouter

from app.api.v1.endpoints.jobs import router as jobs_router

api_router = APIRouter()
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
