"""
Lightweight service class that delegates the core work to helper functions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import threading
from typing import cast

import httpx
from config import config
from custom_types.json import JSONDict, JSONValue
from models.observability.agent_models import AgentHeartbeat, AgentInfo
from services.agent.helpers import (
    KeyActivity,
    KeyVolumePoint,
    extract_metrics_count,
    extract_metrics_series,
    query_key_activity,
    query_key_volume_series,
    update_agent_registry,
)
from services.common.ttl_cache import TTLCache


class AgentService:
    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._registry_lock = threading.Lock()
        self._cache_ttl_seconds = max(1, int(config.SERVICE_CACHE_TTL_SECONDS))
        self._key_activity_cache = TTLCache()
        self._key_volume_cache = TTLCache()

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        with self._registry_lock:
            update_agent_registry(self._agents, heartbeat)

    def list_agents(self) -> list[AgentInfo]:
        with self._registry_lock:
            agents = list(self._agents.values())
        return sorted(agents, key=lambda a: a.last_seen, reverse=True)

    @staticmethod
    def extract_metrics_count(payload: JSONDict) -> int:
        return extract_metrics_count(payload)

    @staticmethod
    def extract_metrics_series(payload: JSONDict) -> list[KeyVolumePoint]:
        return extract_metrics_series(payload)

    async def key_activity(self, key_value: str, mimir_client: httpx.AsyncClient) -> KeyActivity:
        cache_key = f"activity:{key_value}"
        cached = await self._key_activity_cache.get(cache_key)
        if isinstance(cached, dict):
            return cast(KeyActivity, cached)
        result = await query_key_activity(key_value, mimir_client)
        await self._key_activity_cache.set(cache_key, cast(JSONValue, result), self._cache_ttl_seconds)
        return result

    async def key_volume_series(
        self,
        key_value: str,
        mimir_client: httpx.AsyncClient,
        *,
        minutes: int = 60,
        step_seconds: int = 300,
    ) -> list[KeyVolumePoint]:
        cache_key = f"volume:{key_value}:{minutes}:{step_seconds}"
        cached = await self._key_volume_cache.get(cache_key)
        if isinstance(cached, list):
            return cast(list[KeyVolumePoint], cached)
        result = await query_key_volume_series(
            key_value,
            mimir_client,
            minutes=minutes,
            step_seconds=step_seconds,
        )
        await self._key_volume_cache.set(cache_key, cast(JSONValue, result), self._cache_ttl_seconds)
        return result
