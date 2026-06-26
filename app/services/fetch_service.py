"""CSV parsing and product fetch orchestration."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.integrations.myntra.client import MyntraClient
from app.integrations.myntra.exceptions import MyntraBlockedError, MyntraError, MyntraNotFoundError
from app.schemas.product import (
    CategoryAd,
    DeliveryResult,
    JobStatus,
    ProductData,
    ProductFetchResult,
    ProductResultStatus,
)
from app.services.job_store import JobRecord, job_store

logger = logging.getLogger(__name__)


class FetchService:
    """Coordinates CSV parsing and per-product Myntra fetches."""

    def __init__(self) -> None:
        self._client = MyntraClient()

    def parse_product_ids(self, file_bytes: bytes) -> tuple[list[str], list[str]]:
        """Parse and validate product IDs from an uploaded CSV file."""
        warnings: list[str] = []
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames or "product_id" not in {name.strip() for name in reader.fieldnames}:
            raise ValueError("CSV must contain a 'product_id' column.")

        raw_ids: list[str] = []
        for row in reader:
            value = (row.get("product_id") or "").strip()
            if not value:
                continue
            if not value.isdigit():
                warnings.append(f"Skipped invalid product_id value: {value}")
                continue
            raw_ids.append(value)

        if not raw_ids:
            raise ValueError("CSV does not contain any valid product IDs.")

        unique_ids = list(dict.fromkeys(raw_ids))
        if len(unique_ids) != len(raw_ids):
            warnings.append(f"Removed {len(raw_ids) - len(unique_ids)} duplicate product IDs.")
        return unique_ids, warnings

    async def process_job(self, job_id: str) -> None:
        """Process all products for a stored job."""
        job = job_store.get(job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING
        job.phase = "initial"
        job.error = None
        job_store.update(job)

        category_cache: dict[str, list[dict[str, Any]]] = {}

        try:
            for product_id in job.product_ids:
                result = await self._fetch_single_product(product_id, category_cache)
                job.results.append(result)
                job.processed += 1

                if result.status == ProductResultStatus.SUCCESS:
                    job.success_count += 1
                elif result.status == ProductResultStatus.PARTIAL:
                    job.partial_count += 1
                else:
                    job.failed_count += 1

                job_store.update(job)

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("Job %s failed unexpectedly", job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
        finally:
            job.phase = None
            self._clear_retry_progress(job)
            job_store.update(job)

    async def retry_failed_products(self, job_id: str, *, include_partial: bool = True) -> None:
        """Re-fetch products that failed or were partial in a completed job."""
        job = job_store.get(job_id)
        if not job:
            return

        retriable_ids = self._retriable_product_ids(job, include_partial=include_partial)
        if not retriable_ids:
            return

        job.status = JobStatus.RUNNING
        job.phase = "retry"
        job.error = None
        job.retry_total = len(retriable_ids)
        job.retry_processed = 0
        job.retry_current_product_id = None
        job_store.update(job)

        category_cache: dict[str, list[dict[str, Any]]] = {}
        result_index = {result.product_id: index for index, result in enumerate(job.results)}

        try:
            for product_id in retriable_ids:
                job.retry_current_product_id = product_id
                job_store.update(job)

                new_result = await self._fetch_single_product(product_id, category_cache)
                job.results[result_index[product_id]] = new_result
                job.retry_processed += 1
                job_store.update(job)

            self._recalculate_counts(job)
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("Retry for job %s failed unexpectedly", job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
        finally:
            job.phase = None
            self._clear_retry_progress(job)
            job_store.update(job)

    def count_retriable_products(self, job: JobRecord, *, include_partial: bool = True) -> int:
        """Return how many products would be retried for a job."""
        return len(self._retriable_product_ids(job, include_partial=include_partial))

    def _retriable_product_ids(self, job: JobRecord, *, include_partial: bool) -> list[str]:
        ids: list[str] = []
        for result in job.results:
            if result.status == ProductResultStatus.FAILED:
                ids.append(result.product_id)
            elif include_partial and result.status == ProductResultStatus.PARTIAL:
                ids.append(result.product_id)
        return ids

    def _clear_retry_progress(self, job: JobRecord) -> None:
        job.retry_total = 0
        job.retry_processed = 0
        job.retry_current_product_id = None

    def _recalculate_counts(self, job: JobRecord) -> None:
        job.success_count = 0
        job.partial_count = 0
        job.failed_count = 0
        for result in job.results:
            if result.status == ProductResultStatus.SUCCESS:
                job.success_count += 1
            elif result.status == ProductResultStatus.PARTIAL:
                job.partial_count += 1
            else:
                job.failed_count += 1

    async def _fetch_single_product(
        self,
        product_id: str,
        category_cache: dict[str, list[dict[str, Any]]],
    ) -> ProductFetchResult:
        errors: list[str] = []
        meta: dict[str, Any] = {"fetched_at": datetime.now(timezone.utc).isoformat()}

        try:
            if settings.enable_delivery_check:
                product_dict, pdp_data, cookies = await self._client.fetch_product_with_cookies(product_id)
            else:
                product_dict, pdp_data = await self._client.fetch_product(product_id)
                cookies = None
        except MyntraNotFoundError as exc:
            return ProductFetchResult(
                product_id=product_id,
                status=ProductResultStatus.FAILED,
                errors=[str(exc)],
                meta=meta,
            )
        except MyntraBlockedError as exc:
            return ProductFetchResult(
                product_id=product_id,
                status=ProductResultStatus.FAILED,
                errors=[f"Blocked or rate-limited: {exc}"],
                meta=meta,
            )
        except MyntraError as exc:
            return ProductFetchResult(
                product_id=product_id,
                status=ProductResultStatus.FAILED,
                errors=[str(exc)],
                meta=meta,
            )

        product = ProductData(**product_dict)
        if not product.title:
            errors.append("Title not available.")
        if not product.description:
            errors.append("Description not available.")
        if not product.images:
            errors.append("Product images not available.")
        if product.rating is None:
            errors.append("Rating not available.")
        if product.rating_count is None:
            errors.append("Rating count not available.")
        if not product.category:
            errors.append("Category not available.")

        category_ads: list[CategoryAd] = []
        slug = product.category_slug
        meta["category_slug_used"] = slug

        if slug:
            try:
                if slug not in category_cache:
                    category_cache[slug] = await self._client.fetch_category_ads(slug, limit=3)
                ads_raw = category_cache[slug]
                category_ads = [CategoryAd(**ad) for ad in ads_raw]
                if len(category_ads) < 3:
                    errors.append(
                        f"Only {len(category_ads)} sponsored ad result(s) available for category '{slug}'."
                    )
            except Exception as exc:
                errors.append(f"Category ads unavailable for '{slug}': {exc}")
        else:
            errors.append("Could not resolve category slug for sponsored ads.")

        delivery_results: list[DeliveryResult] = []
        if settings.enable_delivery_check and cookies is not None:
            for city, pincode in settings.delivery_pincodes.items():
                try:
                    delivery_raw = await self._client.check_delivery(pdp_data, pincode, cookies=cookies)
                    delivery_results.append(
                        DeliveryResult(city=city, **delivery_raw)
                    )
                    if delivery_raw.get("error"):
                        errors.append(f"Delivery check {city} ({pincode}): {delivery_raw['error']}")
                except Exception as exc:
                    delivery_results.append(
                        DeliveryResult(
                            city=city,
                            pincode=pincode,
                            error=str(exc),
                        )
                    )
                    errors.append(f"Delivery check failed for {city} ({pincode}): {exc}")

        has_core = bool(product.title)
        if not has_core:
            status = ProductResultStatus.FAILED
        elif errors:
            status = ProductResultStatus.PARTIAL
        else:
            status = ProductResultStatus.SUCCESS

        return ProductFetchResult(
            product_id=product_id,
            status=status,
            product=product,
            category_ads=category_ads,
            delivery=delivery_results,
            errors=errors,
            meta=meta,
        )


fetch_service = FetchService()
