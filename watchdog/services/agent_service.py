"""
Lightweight service class that delegates the core work to helper functions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from custom_types.json import JSONDict

import httpx

from models.observability.agent_models import AgentHeartbeat, AgentInfo

from services.agent.helpers import (
    KeyActivity,
    KeyVolumePoint,
    update_agent_registry,
    extract_metrics_count,
    extract_metrics_series,
    query_key_activity,
    query_key_volume_series,
)

class AgentService:
    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def update_from_heartbeat(self, heartbeat: AgentHeartbeat) -> None:
        update_agent_registry(self._agents, heartbeat)

    def list_agents(self) -> list[AgentInfo]:
        return sorted(self._agents.values(), key=lambda a: a.last_seen, reverse=True)

    @staticmethod
    def extract_metrics_count(payload: JSONDict) -> int:
        return extract_metrics_count(payload)

    @staticmethod
    def extract_metrics_series(payload: JSONDict) -> list[KeyVolumePoint]:
        return extract_metrics_series(payload)

    async def key_activity(self, key_value: str, mimir_client: httpx.AsyncClient) -> KeyActivity:
        return await query_key_activity(key_value, mimir_client)

    async def key_volume_series(
        self,
        key_value: str,
        mimir_client: httpx.AsyncClient,
        *,
        minutes: int = 60,
        step_seconds: int = 300,
    ) -> list[KeyVolumePoint]:
        return await query_key_volume_series(
            key_value,
            mimir_client,
            minutes=minutes,
            step_seconds=step_seconds,
        )
