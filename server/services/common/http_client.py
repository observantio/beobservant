"""Shared HTTP client factory for service-layer integrations."""

import httpx


def create_async_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
