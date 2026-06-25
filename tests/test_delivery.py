"""Tests for delivery promise parsing."""

from app.integrations.myntra.mapper import parse_delivery_promise


def test_parse_delivery_promise_formats_get_it_by_text() -> None:
    body = {
        "pincode": "400072",
        "serviceable": True,
        "itemServiceabilityEntries": [
            {
                "itemReferenceId": "4076",
                "skuId": "101495639",
                "serviceable": True,
                "serviceabilityEntries": [
                    {
                        "serviceType": "DELIVERY",
                        "shippingMethod": "EXPRESS",
                        "promiseDate": 1782540000000,
                        "preferredDeliveryTags": {"promiseTag": "2 Day Delivery"},
                    }
                ],
            }
        ],
    }

    serviceable, delivery_text, estimated_days = parse_delivery_promise(body)
    assert serviceable is True
    assert delivery_text == "Get it by Sat, Jun 27"
    assert estimated_days == 2


def test_parse_delivery_promise_not_serviceable() -> None:
    body = {"serviceable": False, "itemServiceabilityEntries": []}
    serviceable, delivery_text, estimated_days = parse_delivery_promise(body)
    assert serviceable is False
    assert "do not ship" in (delivery_text or "").lower()
    assert estimated_days is None
