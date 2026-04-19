"""
Gateway authentication and rate limiting service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Optional

import httpx
from fastapi import HTTPException, Request, status

import settings
from models.exceptions import DatabaseUnavailable
from .rate_limit import make_default_rate_limiter
from .token_cache import make_token_cache

logger = logging.getLogger(__name__)

__all__ = ["GatewayAuthService", "DatabaseUnavailable"]


def _parse_networks(allowlist: str) -> list[IPv4Network | IPv6Network]:
    networks: list[IPv4Network | IPv6Network] = []
    for entry in (e.strip() for e in allowlist.split(",") if e.strip()):
        if "/" not in entry:
            addr = ip_address(entry)
            prefix = "32" if addr.version == 4 else "128"
            entry = f"{entry}/{prefix}"
        networks.append(ip_network(entry, strict=False))
    return networks


def _http_verify_setting() -> str | bool:
    if not settings.AUTH_API_URL.startswith("https"):
        return False
    if settings.SSL_CA_CERTS:
        return settings.SSL_CA_CERTS
    return bool(settings.SSL_VERIFY)


@dataclass(frozen=True)
class GatewayAuthConfig:
    rate_limit_per_minute: int
    ip_allowlist: str
    token_cache_ttl: int
    rate_limit_backend: str
    rate_limit_redis_url: str


def _default_gateway_auth_config() -> GatewayAuthConfig:
    return GatewayAuthConfig(
        rate_limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
        ip_allowlist=settings.IP_ALLOWLIST,
        token_cache_ttl=settings.TOKEN_CACHE_TTL,
        rate_limit_backend=settings.RATE_LIMIT_BACKEND,
        rate_limit_redis_url=settings.RATE_LIMIT_REDIS_URL,
    )


class GatewayAuthService:
    __slots__ = ("_rate_limiter", "_networks", "_token_cache", "_http_verify", "_auth_api_url")

    def __init__(
        self,
        config: GatewayAuthConfig | None = None,
        rate_limit_per_minute: int | None = None,
        ip_allowlist: str | None = None,
    ) -> None:
        current = config or _default_gateway_auth_config()
        if rate_limit_per_minute is not None or ip_allowlist is not None:
            current = GatewayAuthConfig(
                rate_limit_per_minute=(
                    rate_limit_per_minute if rate_limit_per_minute is not None else current.rate_limit_per_minute
                ),
                ip_allowlist=ip_allowlist if ip_allowlist is not None else current.ip_allowlist,
                token_cache_ttl=current.token_cache_ttl,
                rate_limit_backend=current.rate_limit_backend,
                rate_limit_redis_url=current.rate_limit_redis_url,
            )
        self._rate_limiter = make_default_rate_limiter(
            current.rate_limit_per_minute,
            current.rate_limit_backend,
            current.rate_limit_redis_url,
        )
        self._networks = _parse_networks(current.ip_allowlist)
        self._token_cache = make_token_cache(
            current.token_cache_ttl,
            settings.TOKEN_CACHE_REDIS_URL or None,
        )
        self._http_verify = _http_verify_setting()
        self._auth_api_url = settings.AUTH_API_URL

    @staticmethod
    def _trusted_proxy_peer(request: Request) -> bool:
        is_trusted = settings.TRUST_PROXY_HEADERS
        peer = request.client.host if request.client else ""
        if not peer:
            is_trusted = False
        try:
            peer_ip = ip_address(peer)
        except ValueError:
            is_trusted = False
            peer_ip = None
        if is_trusted and peer_ip is not None:
            allowed_cidrs = settings.TRUSTED_PROXY_CIDRS
            if not allowed_cidrs:
                return True
            is_trusted = False
            for cidr in allowed_cidrs:
                try:
                    if peer_ip in ip_network(cidr, strict=False):
                        is_trusted = True
                        break
                except ValueError:
                    continue
        return is_trusted

    @classmethod
    def _client_ip(cls, request: Request) -> str:
        if cls._trusted_proxy_peer(request):
            xff = request.headers.get("x-forwarded-for")
            if xff:
                first = xff.split(",", 1)[0].strip()
                if first:
                    return first
            x_real_ip = request.headers.get("x-real-ip", "").strip()
            if x_real_ip:
                return x_real_ip
        return request.client.host if request.client else "unknown"

    @staticmethod
    def extract_otlp_token(value: Optional[str]) -> str:
        return (value or "").strip()

    def enforce_ip_allowlist(self, request: Request) -> None:
        if not self._networks:
            if not settings.ALLOWLIST_FAIL_OPEN:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")
            return

        raw_ip = self._client_ip(request)
        try:
            addr = ip_address(raw_ip)
        except ValueError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid client IP") from exc

        if not any(addr in net for net in self._networks):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self._rate_limiter.enforce(self._client_ip(request))

    @staticmethod
    def _auth_request_headers(token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if settings.INTERNAL_SERVICE_TOKEN:
            headers["X-Internal-Token"] = settings.INTERNAL_SERVICE_TOKEN
        if token is not None:
            headers["X-OTLP-Token"] = token
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _extract_org_id(response: httpx.Response) -> Optional[str]:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        org_id = payload.get("org_id")
        return str(org_id).strip() if org_id else None

    def _resolve_auth_api_response(self, response: httpx.Response) -> Optional[str]:
        status_code = response.status_code
        if status_code == 200:
            return self._extract_org_id(response)
        if status_code == 404:
            return None
        raise DatabaseUnavailable(f"unexpected status {status_code}")

    def _fetch_org_from_api(self, token: str) -> Optional[str]:
        if not token:
            return None
        url = self._auth_api_url
        headers = self._auth_request_headers(token)
        try:
            with httpx.Client(timeout=2.0, verify=self._http_verify) as client:
                resp = client.post(url, headers=headers, json={"token": token})
        except httpx.HTTPError as exc:
            logger.warning("Auth API HTTP transport failure: %s", type(exc).__name__)
            raise DatabaseUnavailable from exc

        return self._resolve_auth_api_response(resp)

    def probe_auth_api(self, token: str) -> Optional[str]:
        return self._fetch_org_from_api(token)

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        hit, cached = self._token_cache.get(token)
        if hit:
            return cached

        try:
            logger.info("Token cache miss for token: %s", token[:4] + "..." if len(token) > 7 else token)
            org = self._fetch_org_from_api(token)
        except DatabaseUnavailable:
            raise
        except Exception as exc:
            if type(exc).__name__ == "DatabaseUnavailable":
                raise exc
            logger.warning("Auth API fetch unexpected error", exc_info=True)
            raise DatabaseUnavailable from exc

        self._token_cache.set(token, org)
        return org

    def health(self) -> dict[str, str]:
        return {"status": "healthy", "service": "gateway-auth-service"}
