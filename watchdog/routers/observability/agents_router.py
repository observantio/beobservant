"""
Router for OTLP agent management, including listing known agents, checking active agents per API key, and receiving heartbeat payloads.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio

import httpx
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from models.observability.agent_models import AgentHeartbeat
from services.agent_service import AgentService
from services.agent.helpers import KeyActivity
from models.access.auth_models import Permission, TokenData
from config import config

from middleware.dependencies import (
    auth_service,
    require_permission_with_scope,
    enforce_public_endpoint_security,
    enforce_header_token,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])

agent_service = AgentService()

mimir_client = httpx.AsyncClient(
    timeout=httpx.Timeout(config.DEFAULT_TIMEOUT),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

rtp = run_in_threadpool


async def close_mimir_client() -> None:
    await mimir_client.aclose()


@router.get("/")
async def list_agents(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "agents"))) -> list[dict[str, object]]:
    return [agent.model_dump() for agent in agent_service.list_agents()]


@router.get("/active")
async def list_active_agents(current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "agents"))) -> list[dict[str, object]]:
    api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)

    tasks: list[asyncio.Task[KeyActivity]] = []
    for key in api_keys:
        tasks.append(asyncio.create_task(agent_service.key_activity(key.key, mimir_client)))

    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    recent_agents = agent_service.list_agents()
    host_names_by_tenant: dict[str, set[str]] = {}
    for agent in recent_agents:
        if agent.host_name:
            host_names_by_tenant.setdefault(agent.tenant_id, set()).add(agent.host_name)

    activity: list[dict[str, object]] = []
    for key, result in zip(api_keys, results):
        if isinstance(result, BaseException):
            activity.append({
                "name": key.name,
                "tenant_id": key.key,
                "is_enabled": key.is_enabled,
                "active": False,
                "success": False,
                "clean": False,
                "host_names": [],
                "metrics_active": False,
                "metrics_count": 0,
                "agent_estimate": 0,
                "host_estimate": 0,
            })
            continue

        active = bool(result.get("metrics_active"))
        host_names = sorted(host_names_by_tenant.get(key.key, set()))
        activity.append({
            **result,
            "name": key.name,
            "tenant_id": key.key,
            "is_enabled": key.is_enabled,
            "active": active,
            "success": True,
            "clean": active,
            "host_names": host_names,
        })

    return activity


@router.get("/volume")
async def agent_metric_volume(
    tenant_id: str | None = Query(default=None),
    minutes: int = Query(default=60, ge=5, le=1440),
    step_seconds: int = Query(default=300, ge=60, le=3600),
    current_user: TokenData = Depends(require_permission_with_scope(Permission.READ_AGENTS, "agents")),
) -> dict[str, object]:
    tenant_id = tenant_id if isinstance(tenant_id, str) else None
    minutes = minutes if isinstance(minutes, int) else 60
    step_seconds = step_seconds if isinstance(step_seconds, int) else 300
    api_keys = await rtp(auth_service.list_api_keys, current_user.user_id)
    selected_key = None

    if tenant_id:
        selected_key = next((key for key in api_keys if key.key == tenant_id), None)
        if not selected_key:
            raise HTTPException(status_code=403, detail="API key scope is not available to this user")
    else:
        selected_key = next(
            (key for key in api_keys if getattr(key, "is_enabled", False)),
            None,
        ) or next((key for key in api_keys if getattr(key, "is_default", False)), None)

    if not selected_key:
        return {
            "tenant_id": "",
            "key_name": "",
            "points": [],
            "current": 0,
            "peak": 0,
            "average": 0,
        }

    points = await agent_service.key_volume_series(
        selected_key.key,
        mimir_client,
        minutes=minutes,
        step_seconds=step_seconds,
    )
    values = [point["value"] for point in points]

    return {
        "tenant_id": selected_key.key,
        "key_name": selected_key.name,
        "points": points,
        "current": values[-1] if values else 0,
        "peak": max(values) if values else 0,
        "average": int(sum(values) / len(values)) if values else 0,
    }


@router.post("/heartbeat")
async def heartbeat(request: Request, payload: AgentHeartbeat) -> dict[str, str]:
    enforce_public_endpoint_security(
        request,
        scope="agents_heartbeat",
        limit=config.RATE_LIMIT_PUBLIC_PER_MINUTE,
        window_seconds=60,
        allowlist=config.AGENT_INGEST_IP_ALLOWLIST,
    )
    enforce_header_token(
        request,
        header_name="x-agent-heartbeat-token",
        expected_token=config.AGENT_HEARTBEAT_TOKEN,
        unauthorized_detail="Invalid heartbeat token",
    )
    agent_service.update_from_heartbeat(payload)
    return {"status": "ok"}
