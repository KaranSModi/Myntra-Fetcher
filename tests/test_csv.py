"""Tests for CSV parsing."""

import pytest

from app.services.fetch_service import FetchService


def test_parse_product_ids_deduplicates() -> None:
    csv_bytes = b"product_id\n100\n100\n200\n"
    service = FetchService()
    ids, warnings = service.parse_product_ids(csv_bytes)
    assert ids == ["100", "200"]
    assert any("duplicate" in warning.lower() for warning in warnings)


def test_parse_product_ids_requires_column() -> None:
    service = FetchService()
    with pytest.raises(ValueError):
        service.parse_product_ids(b"id\n1\n")
