"""Standalone OTLP gateway auth service.

This service validates OTLP ingest tokens directly against PostgreSQL so nginx
can keep authenticating OTEL traffic even when the main API service is down.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from ipaddress import ip_address, ip_network
from threading import Lock
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from sqlalchemy import Boolean, Column, ForeignKey, String, and_, create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker


LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://beobservant:changeme123@localhost:5432/beobservant",
)
PORT = int(os.getenv("PORT", "4321"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("GATEWAY_RATE_LIMIT_PER_MINUTE", "300"))
IP_ALLOWLIST = (os.getenv("GATEWAY_IP_ALLOWLIST") or "").strip()

logger = logging.getLogger("gateway_auth")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    is_active = Column(Boolean, nullable=False, default=True)


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    otlp_token = Column(String, nullable=True, unique=True, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True)

    user = relationship("User")


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "10")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class TokenRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = 60
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def enforce(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._hits.setdefault(key, [])
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)

            if len(bucket) >= self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                )

            bucket.append(now)


rate_limiter = TokenRateLimiter(RATE_LIMIT_PER_MINUTE)


def _parse_ip_allowlist(allowlist: str) -> list:
    if not allowlist:
        return []

    networks = []
    for raw in allowlist.split(","):
        entry = raw.strip()
        if not entry:
            continue
        if "/" in entry:
            networks.append(ip_network(entry, strict=False))
        else:
            ip = ip_address(entry)
            suffix = 32 if ip.version == 4 else 128
            networks.append(ip_network(f"{entry}/{suffix}", strict=False))
    return networks


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _enforce_ip_allowlist(request: Request) -> None:
    networks = _parse_ip_allowlist(IP_ALLOWLIST)
    if not networks:
        return

    client = _client_ip(request)
    try:
        addr = ip_address(client)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid client IP") from exc

    if any(addr in net for net in networks):
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Source IP not allowed")


def _validate_schema_compatibility(db: Session) -> None:
    required = [
        ("users", "id"),
        ("users", "is_active"),
        ("users", "tenant_id"),
        ("tenants", "id"),
        ("tenants", "is_active"),
        ("user_api_keys", "otlp_token"),
        ("user_api_keys", "key"),
        ("user_api_keys", "is_enabled"),
        ("user_api_keys", "user_id"),
    ]

    for table, column in required:
        exists_stmt = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        )
        row = db.execute(exists_stmt, {"table_name": table, "column_name": column}).scalar()
        if not row:
            raise RuntimeError(f"Missing required DB schema: {table}.{column}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting standalone gateway auth service")
    logger.info("Database target: %s", DATABASE_URL.split("@")[-1])

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            _validate_schema_compatibility(db)
        logger.info("Database connectivity and schema checks passed")
    except Exception as exc:
        logger.exception("Gateway auth service startup check failed: %s", exc)
        raise

    yield


app = FastAPI(
    title="BeObservant Gateway Auth Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def _extract_otlp_token(request: Request) -> str:
    return (request.headers.get("x-otlp-token") or "").strip()


def _validate_otlp_token(db: Session, token: str) -> Optional[str]:
    if not token:
        return None

    stmt = (
        select(UserApiKey.key)
        .join(User, User.id == UserApiKey.user_id)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(
            and_(
                UserApiKey.otlp_token == token,
                UserApiKey.is_enabled.is_(True),
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        .limit(1)
    )

    return db.execute(stmt).scalar_one_or_none()


@app.get("/api/gateway/validate")
async def validate_otlp_token(request: Request):
    _enforce_ip_allowlist(request)
    rate_limiter.enforce(_client_ip(request))

    token = _extract_otlp_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-otlp-token header")

    token_prefix = token[:3] + "..." if len(token) > 3 else token

    try:
        with SessionLocal() as db:
            org_id = _validate_otlp_token(db, token)
    except SQLAlchemyError:
        logger.exception("Database error while validating OTLP token")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth database unavailable")

    if not org_id:
        logger.warning("OTLP token validation failed – token_prefix=%s", token_prefix)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled OTLP token")

    response = Response(status_code=200)
    response.headers["X-Org-Id"] = org_id
    return response


@app.get("/health")
async def health() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(select(func.count()).select_from(UserApiKey).limit(1))
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)
        return {"status": "unhealthy", "service": "gateway-auth-service"}
    return {"status": "healthy", "service": "gateway-auth-service"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
