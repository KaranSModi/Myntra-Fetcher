"""Extract embedded Myntra SSR JSON from HTML responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.integrations.myntra.exceptions import MyntraBlockedError, MyntraParseError

logger = logging.getLogger(__name__)

MYX_MARKER = "window.__myx"


def extract_myx_json(html: str) -> dict[str, Any]:
    """
    Parse the window.__myx JSON blob from a Myntra HTML page.

    Uses bracket matching instead of regex to handle deeply nested JSON safely.
    """
    if not html or len(html) < 5_000:
        raise MyntraBlockedError("Response too small; likely blocked or unavailable.")

    lowered = html.lower()
    if "something went wrong" in lowered and MYX_MARKER not in html:
        raise MyntraBlockedError("Myntra returned a maintenance or error page.")

    marker_index = html.find(MYX_MARKER)
    if marker_index < 0:
        raise MyntraParseError("window.__myx marker not found in page HTML.")

    start = html.find("{", marker_index)
    if start < 0:
        raise MyntraParseError("Could not locate JSON object start for window.__myx.")

    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(html[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blob = html[start : index + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError as exc:
                    logger.exception("Failed to decode window.__myx JSON")
                    raise MyntraParseError("Invalid JSON in window.__myx.") from exc

    raise MyntraParseError("Unterminated JSON object in window.__myx.")
