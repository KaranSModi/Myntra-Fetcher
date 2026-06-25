"""Tests for Myntra SSR parser."""

import pytest

from app.integrations.myntra.exceptions import MyntraBlockedError, MyntraParseError
from app.integrations.myntra.parser import extract_myx_json

SAMPLE_HTML = (
    "<html><body>\n<script>window.__myx = "
    '{"pdpData":{"id":123,"name":"Sample Product"}};'
    "</script>\n</body></html>\n"
) + ("<!-- padding -->" * 400)


def test_extract_myx_json_success() -> None:
    payload = extract_myx_json(SAMPLE_HTML)
    assert payload["pdpData"]["id"] == 123
    assert payload["pdpData"]["name"] == "Sample Product"


def test_extract_myx_json_blocked_page() -> None:
    with pytest.raises(MyntraBlockedError):
        extract_myx_json("<html><body>Oops! Something went wrong</body></html>")


def test_extract_myx_json_missing_marker() -> None:
    html = "<html><body><div>no data</div></body></html>" * 200
    with pytest.raises(MyntraParseError):
        extract_myx_json(html)
