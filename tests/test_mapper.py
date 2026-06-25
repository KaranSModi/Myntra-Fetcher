"""Tests for Myntra data mappers."""

from app.integrations.myntra.mapper import (
    map_category_ads,
    map_pdp_product,
    resolve_category_slug,
)


def test_resolve_category_slug_from_cross_links() -> None:
    pdp = {
        "crossLinks": [
            {"title": "More Handbags by EcoRight", "url": "handbags?f=Brand:EcoRight"},
            {"title": "More Handbags", "url": "handbags?f=Gender:women"},
        ],
        "analytics": {"articleType": "Handbags"},
    }
    assert resolve_category_slug(pdp) == "handbags"


def test_map_pdp_product_core_fields() -> None:
    pdp = {
        "id": 35512522,
        "name": "EcoRight Bag",
        "ratings": {"averageRating": 4.5, "totalCount": 100},
        "analytics": {
            "masterCategory": "Accessories",
            "subCategory": "Bags",
            "articleType": "Handbags",
            "gender": "Women",
        },
        "crossLinks": [{"url": "handbags?f=Gender:women"}],
        "descriptors": [{"title": "description", "description": "A nice bag"}],
        "media": {
            "albums": [
                {
                    "images": [
                        {"src": "http://assets.myntassets.com/h_($height),q_($qualityPercentage),w_($width)/img1.jpg"}
                    ]
                }
            ]
        },
    }
    product = map_pdp_product(pdp, "35512522")
    assert product["title"] == "EcoRight Bag"
    assert product["category"] == "Accessories > Bags > Handbags"
    assert product["category_slug"] == "handbags"
    assert product["images"][0].startswith("https://")
    assert "($height)" not in product["images"][0]


def test_map_category_ads_limits_to_three() -> None:
    payload = {
        "searchData": {
            "results": {
                "plaProducts": [
                    {"productId": i, "isPLA": True, "productName": f"Ad {i}", "price": 100, "rating": 4.0}
                    for i in range(1, 6)
                ]
            }
        }
    }
    ads = map_category_ads(payload, limit=3)
    assert len(ads) == 3
    assert ads[0]["product_id"] == "1"
