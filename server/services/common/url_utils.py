"""URL validation helpers for outbound integrations."""

from urllib.parse import urlparse


def is_safe_http_url(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True
