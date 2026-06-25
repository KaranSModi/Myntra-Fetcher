"""Myntra integration exceptions."""


class MyntraError(Exception):
    """Base exception for Myntra integration errors."""


class MyntraBlockedError(MyntraError):
    """Raised when Myntra returns a bot block or maintenance page."""


class MyntraNotFoundError(MyntraError):
    """Raised when a product page cannot be found."""


class MyntraParseError(MyntraError):
    """Raised when SSR JSON cannot be parsed from the HTML response."""
