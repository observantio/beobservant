"""
Gateway authentication and rate limiting service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from ipaddress import ip_address, ip_network
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

import db_models
from . import config as gw_config
from .rate_limit import make_default_rate_limiter
from .token_cache import TokenCache

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    pass


def _parse_networks(allowlist: str) -> list:
    networks = []
    for entry in (e.strip() for e in allowlist.split(",") if e.strip()):
        if "/" not in entry:
            addr = ip_address(entry)
            prefix = "32" if addr.version == 4 else "128"
            entry = f"{entry}/{prefix}"
        networks.append(ip_network(entry, strict=False))
    return networks


_VALID_TOKEN_STMT = (
    select(db_models.UserApiKey.key)
    .join(db_models.User, db_models.User.id == db_models.UserApiKey.user_id)
    .join(db_models.Tenant, db_models.Tenant.id == db_models.User.tenant_id)
    .where(
        or_(
            db_models.UserApiKey.otlp_token == None,
            db_models.UserApiKey.key == None,
        ),
        db_models.UserApiKey.is_enabled.is_(True),
        db_models.User.is_active.is_(True),
        db_models.Tenant.is_active.is_(True),
    )
    .limit(1)
)


class GatewayAuthService:
    __slots__ = ("_rate_limiter", "_networks", "_token_cache")

    def __init__(
        self,
        *,
        rate_limit_per_minute: Optional[int] = None,
        ip_allowlist: Optional[str] = None,
        token_cache_ttl: Optional[int] = None,
        rate_limit_backend: Optional[str] = None,
        rate_limit_redis_url: Optional[str] = None,
    ) -> None:
        self._rate_limiter = make_default_rate_limiter(
            rate_limit_per_minute if rate_limit_per_minute is not None else gw_config.RATE_LIMIT_PER_MINUTE,
            rate_limit_backend if rate_limit_backend is not None else gw_config.RATE_LIMIT_BACKEND,
            rate_limit_redis_url if rate_limit_redis_url is not None else gw_config.RATE_LIMIT_REDIS_URL,
        )
        self._networks = _parse_networks(
            ip_allowlist if ip_allowlist is not None else gw_config.IP_ALLOWLIST
        )
        self._token_cache = TokenCache(
            token_cache_ttl if token_cache_ttl is not None else gw_config.TOKEN_CACHE_TTL
        )

    @staticmethod
    def _client_ip(request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
        return request.client.host if request.client else "unknown"

    @staticmethod
    def extract_otlp_token(value: Optional[str]) -> str:
        return (value or "").strip()

    def enforce_ip_allowlist(self, request: Request) -> None:
        if not self._networks:
            if not gw_config.ALLOWLIST_FAIL_OPEN:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")
            return

        raw_ip = self._client_ip(request)
        try:
            addr = ip_address(raw_ip)
        except ValueError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid client IP")

        if not any(addr in net for net in self._networks):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Source IP not allowed")

    def enforce_rate_limit(self, request: Request) -> None:
        self._rate_limiter.enforce(self._client_ip(request))

    def validate_otlp_token(self, token: str) -> Optional[str]:
        if not token:
            return None

        hit, cached = self._token_cache.get(token)
        if hit:
            return cached

        stmt = (
            select(db_models.UserApiKey.key)
            .join(db_models.User, db_models.User.id == db_models.UserApiKey.user_id)
            .join(db_models.Tenant, db_models.Tenant.id == db_models.User.tenant_id)
            .where(
                or_(
                    db_models.UserApiKey.otlp_token == token,
                    db_models.UserApiKey.key == token,
                ),
                db_models.UserApiKey.is_enabled.is_(True),
                db_models.User.is_active.is_(True),
                db_models.Tenant.is_active.is_(True),
            )
            .limit(1)
        )

        try:
            with db_models.SessionLocal() as db:
                result = db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            logger.warning("Database error validating OTLP token", exc_info=True)
            raise DatabaseUnavailable from exc

        self._token_cache.set(token, result)
        return result

    def health(self) -> dict:
        try:
            with db_models.SessionLocal() as db:
                db.execute(
                    select(func.count()).select_from(db_models.UserApiKey).limit(1)
                )
            return {"status": "healthy", "service": "gateway-auth-service"}
        except Exception:
            return {"status": "unhealthy", "service": "gateway-auth-service"}