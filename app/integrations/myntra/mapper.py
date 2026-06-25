"""Map raw Myntra JSON into domain models."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from app.core.config import settings

IMAGE_TEMPLATE_DEFAULTS = {"height": "720", "qualityPercentage": "90", "width": "540"}


def normalize_image_url(url: str | None) -> str | None:
    """Convert Myntra CDN template URLs into usable HTTPS image links."""
    if not url:
        return None
    normalized = url.replace("http://", "https://")
    replacements = {
        "($height)": IMAGE_TEMPLATE_DEFAULTS["height"],
        "($qualityPercentage)": IMAGE_TEMPLATE_DEFAULTS["qualityPercentage"],
        "($width)": IMAGE_TEMPLATE_DEFAULTS["width"],
        "(${height})": IMAGE_TEMPLATE_DEFAULTS["height"],
        "(${qualityPercentage})": IMAGE_TEMPLATE_DEFAULTS["qualityPercentage"],
        "(${width})": IMAGE_TEMPLATE_DEFAULTS["width"],
    }
    for token, value in replacements.items():
        normalized = normalized.replace(token, value)
    return normalized


def slugify_article_type(value: str) -> str:
    """Convert article type labels into URL slug candidates."""
    slug = value.strip().lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def resolve_category_slug(pdp_data: dict[str, Any]) -> str | None:
    """
    Resolve the category listing slug used for sponsored ad results.

  Priority:
    1. Last crossLinks entry (e.g. handbags?f=Gender:women -> handbags)
    2. analytics.articleType slugified (e.g. Handbags -> handbags)
    """
    cross_links = pdp_data.get("crossLinks") or []
    for link in reversed(cross_links):
        url = (link or {}).get("url") or ""
        if "?" in url:
            url = url.split("?", 1)[0]
        if url and not url.startswith("http"):
            return url.strip("/").lower()

    analytics = pdp_data.get("analytics") or {}
    article_type = analytics.get("articleType")
    if article_type:
        return slugify_article_type(str(article_type))
    return None


def build_category_label(pdp_data: dict[str, Any]) -> str | None:
    """Build a human-readable category breadcrumb from analytics fields."""
    analytics = pdp_data.get("analytics") or {}
    parts = [
        analytics.get("masterCategory"),
        analytics.get("subCategory"),
        analytics.get("articleType"),
    ]
    cleaned = [str(part).strip() for part in parts if part]
    return " > ".join(cleaned) if cleaned else None


def extract_description(pdp_data: dict[str, Any]) -> str | None:
    """Extract the primary product description from PDP descriptors or details."""
    for descriptor in pdp_data.get("descriptors") or []:
        if (descriptor or {}).get("title") == "description":
            description = (descriptor or {}).get("description")
            if description:
                return _strip_html(str(description))

    for detail in pdp_data.get("productDetails") or []:
        title = ((detail or {}).get("title") or "").lower()
        if "product details" in title:
            description = (detail or {}).get("description")
            if description:
                return _strip_html(str(description))
    return None


def extract_images(pdp_data: dict[str, Any], limit: int = 2) -> list[str]:
    """Return up to `limit` normalized product image URLs."""
    images: list[str] = []
    for album in (pdp_data.get("media") or {}).get("albums") or []:
        for image in album.get("images") or []:
            url = normalize_image_url(image.get("src") or image.get("imageURL"))
            if url and url not in images:
                images.append(url)
            if len(images) >= limit:
                return images
    return images


def map_pdp_product(pdp_data: dict[str, Any], product_id: str) -> dict[str, Any]:
    """Map pdpData into the structured product payload."""
    ratings = pdp_data.get("ratings") or {}
    rating_value = ratings.get("averageRating")
    rating_count = ratings.get("totalCount")
    seller = pdp_data.get("selectedSeller") or {}
    price = seller.get("discountedPrice") or pdp_data.get("mrp")
    mrp = pdp_data.get("mrp")

    return {
        "product_id": str(pdp_data.get("id") or product_id),
        "title": pdp_data.get("name"),
        "description": extract_description(pdp_data),
        "images": extract_images(pdp_data, limit=2),
        "price": float(price) if price is not None else None,
        "mrp": float(mrp) if mrp is not None else None,
        "rating": float(rating_value) if rating_value is not None else None,
        "rating_count": int(rating_count) if rating_count is not None else None,
        "category": build_category_label(pdp_data),
        "category_slug": resolve_category_slug(pdp_data),
        "product_url": urljoin(settings.myntra_base_url + "/", str(product_id)),
        "category_url": None,
    }


def map_category_ad(raw_ad: dict[str, Any]) -> dict[str, Any]:
    """Map a plaProducts entry into a category ad result."""
    image = None
    search_image = raw_ad.get("searchImage")
    if isinstance(search_image, dict):
        image = normalize_image_url(search_image.get("src") or search_image.get("imageURL"))
    elif isinstance(search_image, str):
        image = normalize_image_url(search_image)
    if not image:
        image = normalize_image_url(raw_ad.get("defaultImageUrl") or raw_ad.get("searchImage"))

    rating = raw_ad.get("rating")
    rating_count = raw_ad.get("ratingCount")

    return {
        "product_id": str(raw_ad.get("productId") or ""),
        "title": raw_ad.get("productName") or raw_ad.get("product"),
        "price": raw_ad.get("price"),
        "mrp": raw_ad.get("mrp"),
        "rating": float(rating) if rating else None,
        "rating_count": int(rating_count) if rating_count else None,
        "image": image,
        "product_url": urljoin(
            settings.myntra_base_url + "/",
            str(raw_ad.get("landingPageUrl") or "").lstrip("/"),
        ),
        "is_sponsored": bool(raw_ad.get("isPLA")),
    }


def map_category_ads(search_data: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Return the first `limit` sponsored PLA products from a category page."""
    results = (search_data.get("searchData") or {}).get("results") or {}
    pla_products = results.get("plaProducts") or []
    ads: list[dict[str, Any]] = []

    for item in pla_products:
        if not item:
            continue
        if item.get("isPLA") is False and not item.get("productId"):
            continue
        ads.append(map_category_ad(item))
        if len(ads) >= limit:
            break
    return ads


def _resolve_default_size(pdp_data: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the default purchasable size using buy-button seller order when available."""
    sizes = pdp_data.get("sizes") or []
    if not sizes:
        return None

    buy_orders = pdp_data.get("buyButtonSellerOrder") or []
    default_sku = buy_orders[0].get("skuId") if buy_orders else None
    if default_sku is not None:
        for size in sizes:
            if size.get("skuId") == default_sku:
                return size

    for size in sizes:
        if size.get("available"):
            return size
    return sizes[0]


def _resolve_seller_partner_id(pdp_data: dict[str, Any], size: dict[str, Any]) -> int | str | None:
    buy_orders = pdp_data.get("buyButtonSellerOrder") or []
    default_sku = size.get("skuId")
    for order in buy_orders:
        if order.get("skuId") == default_sku:
            return order.get("sellerPartnerId")

    if buy_orders:
        return buy_orders[0].get("sellerPartnerId")

    selected = pdp_data.get("selectedSeller") or {}
    return selected.get("sellerPartnerId")


def _resolve_warehouses(size: dict[str, Any], seller_partner_id: int | str | None) -> list[str]:
    warehouses: list[str] = []
    for seller_data in size.get("sizeSellerData") or []:
        if seller_partner_id and seller_data.get("sellerPartnerId") != seller_partner_id:
            continue
        warehouses.extend(str(code) for code in seller_data.get("warehouses") or [])
    return warehouses


def build_serviceability_v2_item(pdp_data: dict[str, Any]) -> dict[str, Any] | None:
    """Build the v2 serviceability/check payload item that returns promiseDate."""
    size = _resolve_default_size(pdp_data)
    if not size:
        return None

    sku_id = size.get("skuId")
    if not sku_id:
        return None

    seller_partner_id = _resolve_seller_partner_id(pdp_data, size)
    procurement_map = (pdp_data.get("serviceability") or {}).get("procurementTimeInDays") or {}
    procurement_days = 0
    if seller_partner_id is not None:
        procurement_days = procurement_map.get(str(seller_partner_id), 0)

    warehouses = _resolve_warehouses(size, seller_partner_id)
    flags = pdp_data.get("flags") or {}
    analytics = pdp_data.get("analytics") or {}
    price = (pdp_data.get("selectedSeller") or {}).get("discountedPrice") or pdp_data.get("mrp") or 0
    launch_date = (pdp_data.get("serviceability") or {}).get("launchDate") or ""

    return {
        "itemReferenceId": str(seller_partner_id or ""),
        "skuId": str(sku_id),
        "codValue": int(price or 0),
        "itemValue": int(price or 0),
        "isHazmat": bool(flags.get("isHazmat", False)),
        "isLarge": bool(flags.get("isLarge", False)),
        "isJewellery": bool(flags.get("isJewellery", False)),
        "isFragile": bool(flags.get("isFragile", False)),
        "codEnabled": bool(flags.get("codEnabled", True)),
        "openBoxPickupEnabled": bool(flags.get("openBoxPickupEnabled", True)),
        "tryAndBuyEnabled": bool(flags.get("tryAndBuyEnabled", False)),
        "isReturnable": bool(flags.get("isReturnable", True)),
        "procurementTimeInDays": int(procurement_days or 0),
        "launchDate": launch_date,
        "availableInWarehouses": warehouses or ["60132"],
        "articleType": analytics.get("articleType") or "",
    }


def parse_delivery_promise(body: dict[str, Any]) -> tuple[bool | None, str | None, int | None]:
    """
    Parse delivery promise from gateway v2 serviceability response.

    Returns serviceable flag, UI-style delivery text, and estimated day count.
    """
    serviceable = body.get("serviceable")
    promise_entry: dict[str, Any] | None = None

    for item in body.get("itemServiceabilityEntries") or []:
        if item.get("serviceable") is False:
            serviceable = False
        for entry in item.get("serviceabilityEntries") or []:
            if entry.get("serviceType") != "DELIVERY":
                continue
            if entry.get("promiseDate"):
                if (
                    promise_entry is None
                    or entry.get("shippingMethod") == "NORMAL"
                    or (
                        promise_entry.get("shippingMethod") != "NORMAL"
                        and entry.get("shippingMethod") == "EXPRESS"
                    )
                ):
                    promise_entry = entry

    if serviceable is False:
        return False, "Unfortunately we do not ship to your pincode", None

    if not promise_entry:
        if serviceable is True:
            return True, "Serviceable", None
        return serviceable, None, None

    promise_ms = promise_entry.get("promiseDate")
    delivery_text = None
    estimated_days = None

    if promise_ms:
        promise_dt = datetime.fromtimestamp(int(promise_ms) / 1000, tz=timezone.utc).astimezone(
            ZoneInfo("Asia/Kolkata")
        )
        delivery_text = f"Get it by {promise_dt.strftime('%a, %b %d')}"

        now_ist = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        estimated_days = max((promise_dt.date() - now_ist.date()).days, 0)

    tags = promise_entry.get("preferredDeliveryTags") or {}
    tag_text = tags.get("promiseTag")
    if tag_text and not delivery_text:
        delivery_text = tag_text

    if tag_text:
        match = re.search(r"(\d+)\s*Day", str(tag_text), re.IGNORECASE)
        if match:
            estimated_days = int(match.group(1))

    return serviceable, delivery_text, estimated_days


def build_serviceability_item(pdp_data: dict[str, Any]) -> dict[str, Any] | None:
    """Build the v3 serviceability/check payload item from PDP data."""
    size = _resolve_default_size(pdp_data)
    if not size:
        return None

    sku_id = size.get("skuId")
    if not sku_id:
        return None

    seller_partner_id = _resolve_seller_partner_id(pdp_data, size)
    procurement_map = (pdp_data.get("serviceability") or {}).get("procurementTimeInDays") or {}
    procurement_days = 0
    if seller_partner_id is not None:
        procurement_days = procurement_map.get(str(seller_partner_id), 0)

    warehouses = _resolve_warehouses(size, seller_partner_id)
    flags = pdp_data.get("flags") or {}
    analytics = pdp_data.get("analytics") or {}
    price = (pdp_data.get("selectedSeller") or {}).get("discountedPrice") or pdp_data.get("mrp") or 0

    return {
        "itemReferenceId": str(seller_partner_id or ""),
        "skuId": str(sku_id),
        "procurementTimeInDays": int(procurement_days or 0),
        "availableInWarehouses": warehouses or ["60132"],
        "itemValue": int(price or 0),
        "isHazmat": bool(flags.get("isHazmat", False)),
        "isLarge": bool(flags.get("isLarge", False)),
        "isJewellery": bool(flags.get("isJewellery", False)),
        "isFragile": bool(flags.get("isFragile", False)),
        "codValue": int(price or 0),
        "codEnabled": bool(flags.get("codEnabled", True)),
        "tryAndBuyEnabled": bool(flags.get("tryAndBuyEnabled", False)),
        "isExchangeable": bool(flags.get("isExchangeable", True)),
        "isReturnable": bool(flags.get("isReturnable", True)),
        "openBoxPickupEnabled": bool(flags.get("openBoxPickupEnabled", True)),
        "articleType": analytics.get("articleType") or "",
        "measurementModeEnabled": bool(flags.get("measurementModeEnabled", False)),
        "sampleModeEnabled": bool(flags.get("sampleModeEnabled", False)),
        "articleGender": analytics.get("gender") or "",
    }


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()
