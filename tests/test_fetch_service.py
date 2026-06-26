"""Tests for fetch service retry helpers."""

from app.schemas.product import JobStatus, ProductFetchResult, ProductResultStatus
from app.services.fetch_service import FetchService
from app.services.job_store import JobRecord


def _make_job() -> JobRecord:
    job = JobRecord(job_id="test-job", status=JobStatus.COMPLETED, product_ids=["1", "2", "3", "4"])
    job.results = [
        ProductFetchResult(product_id="1", status=ProductResultStatus.SUCCESS),
        ProductFetchResult(product_id="2", status=ProductResultStatus.FAILED),
        ProductFetchResult(product_id="3", status=ProductResultStatus.PARTIAL),
        ProductFetchResult(product_id="4", status=ProductResultStatus.FAILED),
    ]
    job.success_count = 1
    job.partial_count = 1
    job.failed_count = 2
    job.processed = 4
    return job


def test_count_retriable_products_includes_partial_by_default() -> None:
    service = FetchService()
    job = _make_job()

    assert service.count_retriable_products(job) == 3


def test_count_retriable_products_can_exclude_partial() -> None:
    service = FetchService()
    job = _make_job()

    assert service.count_retriable_products(job, include_partial=False) == 2


def test_recalculate_counts() -> None:
    service = FetchService()
    job = _make_job()
    job.results[1] = ProductFetchResult(product_id="2", status=ProductResultStatus.SUCCESS)
    job.results[3] = ProductFetchResult(product_id="4", status=ProductResultStatus.PARTIAL)

    service._recalculate_counts(job)

    assert job.success_count == 2
    assert job.partial_count == 2
    assert job.failed_count == 0
