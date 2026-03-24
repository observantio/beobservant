"""
Router for OTLP agent management, including listing known agents, checking active agents per API key, and receiving heartbeat payloads.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import asyncio

import httpx
from fastapi import APIRouter, Request, Depends
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
    instance_ids_by_tenant: dict[str, set[str]] = {}
    for agent in recent_agents:
        if not agent.host_name:
            pass
        else:
            host_names_by_tenant.setdefault(agent.tenant_id, set()).add(agent.host_name)
        raw_attributes = getattr(agent, "attributes", {})
        attributes = raw_attributes if isinstance(raw_attributes, dict) else {}
        candidate_ids = [
            attributes.get("service.instance.id"),
            attributes.get("service.instance_id"),
            attributes.get("instance_id"),
        ]
        for candidate in candidate_ids:
            value = str(candidate or "").strip()
            if value:
                instance_ids_by_tenant.setdefault(agent.tenant_id, set()).add(value)

    activity: list[dict[str, object]] = []
    for key, result in zip(api_keys, results):
        if isinstance(result, BaseException):
            activity.append({
                "name": key.name,
                "is_enabled": key.is_enabled,
                "active": False,
                "success": False,
                "clean": False,
                "host_names": [],
                "metrics_active": False,
                "metrics_count": 0,
                "instance_ids": [],
            })
            continue

        active = bool(result.get("metrics_active"))
        host_names = sorted(host_names_by_tenant.get(key.key, set()))
        result_instance_ids = result.get("instance_ids")
        combined_instance_ids = {
            str(v).strip()
            for v in (result_instance_ids if isinstance(result_instance_ids, list) else [])
            if str(v).strip()
        }
        combined_instance_ids.update(instance_ids_by_tenant.get(key.key, set()))
        activity.append({
            **result,
            "name": key.name,
            "is_enabled": key.is_enabled,
            "active": active,
            "success": True,
            "clean": active,
            "host_names": host_names,
            "instance_ids": sorted(combined_instance_ids),
        })

    return activity


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
