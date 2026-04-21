"""
Gateway auth service entry point.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import settings
import start
from fastapi import FastAPI
from middleware.openapi import install_custom_openapi
from middleware.runtime_ssl import RuntimeSSLOptions, run_uvicorn
from models.exceptions import DatabaseUnavailable
from pydantic import BaseModel
from routers import router as gateway_router
from services.gateway_service import GatewayAuthService

assert start.__file__

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("gateway_auth")

service = GatewayAuthService()
STARTUP_CHECK_ERRORS = (RuntimeError, DatabaseUnavailable)


class HealthResponse(BaseModel):
    status: str
    service: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting standalone gateway auth service")

    max_retries = settings.GATEWAY_STARTUP_RETRIES
    backoff = settings.GATEWAY_STARTUP_BACKOFF
    attempt = 0

    while True:
        try:
            if settings.AUTH_API_URL:
                probe_token = settings.GATEWAY_STATUS_OTLP_TOKEN
                if not probe_token:
                    if settings.GATEWAY_STARTUP_CHECK_MODE == "strict":
                        raise RuntimeError(
                            "GATEWAY_STATUS_OTLP_TOKEN is required when GATEWAY_STARTUP_CHECK_MODE=strict"
                        )
                    probe_token = "__gateway_startup_probe__"
                    logger.warning(
                        "GATEWAY_STATUS_OTLP_TOKEN is not set; "
                        "using synthetic startup probe token to verify "
                        "auth API connectivity"
                    )
                service.probe_auth_api(probe_token)
            logger.info("Startup connectivity checks passed")
            break
        except STARTUP_CHECK_ERRORS as exc:
            attempt += 1
            if attempt >= max_retries:
                if settings.GATEWAY_STARTUP_CHECK_MODE == "warn":
                    logger.warning(
                        "Gateway startup check failed after %d attempts; continuing in warn mode: %s",
                        attempt,
                        exc,
                    )
                    break
                logger.exception("Gateway startup check failed after %d attempts: %s", attempt, exc)
                raise
            logger.warning(
                "Startup check failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                max_retries,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    yield


app = FastAPI(
    title="Watchdog Gateway Auth Service",
    version="0.0.5",
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
    lifespan=lifespan,
)

app.include_router(gateway_router)
install_custom_openapi(app)


@app.get(
    "/health",
    summary="Service Health",
    description="Returns a lightweight health status for gatekeeper.",
    response_description="The current health status for gatekeeper.",
    response_model=HealthResponse,
)
async def health_root() -> dict[str, str]:
    return service.health()


if __name__ == "__main__":
    ssl_options = RuntimeSSLOptions.from_settings(settings)
    if ssl_options is not None:
        logger.info("TLS enabled")

    run_uvicorn(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_ca_certs=None,
        ssl_options=ssl_options,
    )
