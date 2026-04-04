"""
Internal token validation route — consumed only by the gateway auth service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from models.internal.otlp_validate import OtlpValidateRequest

from services.internal_service import InternalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])

internal_service = InternalService()


def _verify_service_token(x_internal_token: str = Header(...)) -> None:
    internal_service.verify_service_token(x_internal_token)


@router.get(
    "/otlp/validate",
    dependencies=[Depends(_verify_service_token)],
    responses={status.HTTP_410_GONE: {"description": "Legacy query token validation is disabled; use POST endpoint"}},
)
async def validate_otlp_token_query(token: str = Query(..., min_length=1)) -> dict[str, str]:
    _ = token
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy query token validation is disabled; use POST /api/internal/otlp/validate",
    )


@router.post(
    "/otlp/validate",
    dependencies=[Depends(_verify_service_token)],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Missing or invalid token"},
        status.HTTP_404_NOT_FOUND: {"description": "OTLP token was not found"},
    },
)
async def validate_otlp_token_post(
    payload: OtlpValidateRequest,
    x_otlp_token: str | None = Header(None),
) -> dict[str, str]:
    token = (payload.token or x_otlp_token or "").strip()
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing token")
    try:
        token.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token encoding") from exc
    return internal_service.validate_token_or_404(token)
