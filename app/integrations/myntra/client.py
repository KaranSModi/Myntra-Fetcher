"""HTTP client for public Myntra pages and gateway APIs."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.myntra.exceptions import MyntraBlockedError, MyntraNotFoundError, MyntraParseError
from app.integrations.myntra.mapper import (
    build_serviceability_v2_item,
    map_category_ads,
    map_pdp_product,
    parse_delivery_promise,
)
from app.integrations.myntra.parser import extract_myx_json

logger = logging.getLogger(__name__)


class MyntraClient:
    """Async client for fetching and parsing Myntra public data."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._last_request_at = 0.0

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
            "Referer": settings.myntra_base_url + "/",
            "x-myntraweb": "Yes",
            "x-requested-with": "browser",
        }

    async def _throttle(self) -> None:
        async with self._semaphore:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < settings.request_delay_seconds:
                await asyncio.sleep(settings.request_delay_seconds - elapsed)
            self._last_request_at = time.monotonic()

    async def _get_html(self, path: str) -> str:
        url = path if path.startswith("http") else f"{settings.myntra_base_url.rstrip('/')}/{path.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(1, settings.max_retries + 1):
            await self._throttle()
            try:
                async with httpx.AsyncClient(
                    timeout=settings.request_timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url, headers=self._default_headers())
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("HTTP error fetching %s (attempt %s): %s", url, attempt, exc)
                await asyncio.sleep(attempt)
                continue

            if response.status_code == 404:
                raise MyntraNotFoundError(f"Product or page not found: {url}")
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = MyntraBlockedError(f"Myntra returned status {response.status_code}")
                await asyncio.sleep(attempt * 1.5)
                continue
            if response.status_code >= 400:
                raise MyntraBlockedError(f"Myntra returned status {response.status_code} for {url}")

            return response.text

        raise last_error or MyntraBlockedError(f"Failed to fetch {url}")

    async def fetch_product(self, product_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch PDP HTML and return mapped product data plus raw pdpData."""
        html = await self._get_html(str(product_id))
        try:
            payload = extract_myx_json(html)
        except MyntraParseError as exc:
            raise MyntraNotFoundError(f"Product {product_id} has no parseable PDP data.") from exc

        pdp_data = payload.get("pdpData")
        if not pdp_data:
            raise MyntraNotFoundError(f"Product {product_id} is unavailable or delisted.")

        product = map_pdp_product(pdp_data, product_id)
        if product.get("category_slug"):
            product["category_url"] = f"{settings.myntra_base_url}/{product['category_slug']}"
        return product, pdp_data

    async def fetch_category_ads(self, category_slug: str, limit: int = 3) -> list[dict[str, Any]]:
        """Fetch sponsored category ads from a category listing page."""
        html = await self._get_html(category_slug)
        payload = extract_myx_json(html)
        return map_category_ads(payload, limit=limit)

    async def check_delivery(
        self,
        pdp_data: dict[str, Any],
        pincode: str,
        cookies: httpx.Cookies | None = None,
    ) -> dict[str, Any]:
        """
        Check delivery serviceability for a pincode using Myntra gateway APIs.

        Requires cookies obtained from the initial PDP request.
        """
        item = build_serviceability_v2_item(pdp_data)
        if not item:
            return {
                "pincode": pincode,
                "serviceable": None,
                "delivery_text": None,
                "estimated_days": None,
                "error": "Could not build serviceability payload from product data.",
            }

        headers = self._default_headers()
        headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": settings.myntra_base_url,
                "Referer": f"{settings.myntra_base_url}/{pdp_data.get('id')}",
                "x-location-context": f"pincode={pincode};source=USER",
            }
        )

        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            cookies=cookies,
            follow_redirects=True,
        ) as client:
            await client.post(
                f"{settings.myntra_base_url}/gateway/v1/user/locationContext",
                headers=headers,
                json={
                    "previousContext": {"pincode": pincode, "source": "USER"},
                    "currentContext": {
                        "addressId": "",
                        "pincodeSource": [{"pincode": pincode, "source": "USER"}],
                    },
                },
            )

            response = await client.post(
                f"{settings.myntra_base_url}/gateway/v2/serviceability/check",
                headers=headers,
                json={
                    "pincode": pincode,
                    "clientId": "2297",
                    "paymentMode": "ALL",
                    "serviceType": "FORWARD",
                    "shippingMethod": "ALL",
                    "consolidationEnabled": False,
                    "nonWorkingDays": [],
                    "clientReferenceId": f"guest_{int(time.time() * 1000)}",
                    "items": [item],
                },
            )

        if response.status_code >= 400:
            return {
                "pincode": pincode,
                "serviceable": None,
                "delivery_text": None,
                "estimated_days": None,
                "error": f"Serviceability API returned status {response.status_code}",
            }

        body = response.json()
        serviceable, delivery_text, estimated_days = parse_delivery_promise(body)

        return {
            "pincode": pincode,
            "serviceable": serviceable,
            "delivery_text": delivery_text,
            "estimated_days": estimated_days,
            "error": None,
        }

    async def fetch_product_with_cookies(
        self, product_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], httpx.Cookies]:
        """Fetch PDP and retain cookies for follow-up gateway calls."""
        url = f"{settings.myntra_base_url.rstrip('/')}/{product_id}"
        await self._throttle()
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers=self._default_headers())
            if response.status_code == 404:
                raise MyntraNotFoundError(f"Product {product_id} not found.")
            if response.status_code >= 400:
                raise MyntraBlockedError(f"Myntra returned status {response.status_code}")

            payload = extract_myx_json(response.text)
            pdp_data = payload.get("pdpData")
            if not pdp_data:
                raise MyntraNotFoundError(f"Product {product_id} is unavailable.")

            product = map_pdp_product(pdp_data, product_id)
            if product.get("category_slug"):
                product["category_url"] = f"{settings.myntra_base_url}/{product['category_slug']}"
            return product, pdp_data, response.cookies
