"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")
from datetime import datetime, timezone, timedelta

import pytest

from models.observability.agent_models import AgentHeartbeat, AgentInfo
from services.agent_service import AgentService
from services.agent import helpers

def test_update_registry_new_and_existing():
    registry: dict[str, AgentInfo] = {}
    now = datetime.now(timezone.utc)
    hb = AgentHeartbeat(name="a", tenant_id="t", timestamp=now, attributes={"host.name": "h"}, signal="s")
    helpers.update_agent_registry(registry, hb)
    assert "t:a" in registry
    info = registry["t:a"]
    assert info.name == "a"
    assert info.host_name == "h"
    assert info.signals == ["s"]
    later = now + timedelta(seconds=5)
    hb2 = AgentHeartbeat(name="a", tenant_id="t", timestamp=later, attributes={}, signal="s2")
    helpers.update_agent_registry(registry, hb2)
    info2 = registry["t:a"]
    assert info2.last_seen == later
    assert "s2" in info2.signals

    hb3 = AgentHeartbeat(name="a", tenant_id="t", timestamp=later, attributes={"host.name": "updated-host"}, signal=None)
    helpers.update_agent_registry(registry, hb3)
    assert registry["t:a"].host_name == "updated-host"


def test_extract_metrics_count():
    assert helpers.extract_metrics_count({}) == 0
    payload = {"data": {"result": [{"value": [123, "7.0"]}]}}
    assert helpers.extract_metrics_count(payload) == 7


def test_extract_metrics_series():
    payload = {
        "data": {
            "result": [
                {
                    "values": [
                        [1711000000, "2"],
                        ["1711000300", "5.0"],
                        [1711000600, "bad"],
                    ]
                }
            ]
        }
    }
    assert helpers.extract_metrics_series(payload) == [
        {"ts": 1711000000, "value": 2},
        {"ts": 1711000300, "value": 5},
    ]


def test_mimir_prometheus_url_helper():
    assert helpers.mimir_prometheus_url("http://mimir", "api/v1/query") == "http://mimir/prometheus/api/v1/query"
    assert helpers.mimir_prometheus_url("http://mimir/prometheus", "api/v1/query_range") == "http://mimir/prometheus/api/v1/query_range"


class DummyClient:
    def __init__(self, payload, by_path=None):
        self.payload = payload
        self.by_path = by_path or {}
        self.last_url = None
        self.request_urls = []

    async def get(self, url, params=None, headers=None):
        self.last_url = url
        self.request_urls.append(str(url))
        payload = self.payload
        for path, override in self.by_path.items():
            if path in str(url):
                payload = override
                break

        class Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                pass

            def json(self):
                return self._data

        return Resp(payload)


@pytest.mark.asyncio
async def test_query_key_activity_success():
    payload = {"data": {"result": [{"value": [0, "3"]}]}}
    client = DummyClient(
        payload,
        by_path={
            "/label/instance/values": {"data": ["inst-a", "inst-b"]},
            "/label/host.name/values": {"data": ["host-a", "host-b", "host-c"]},
        },
    )
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"]
    assert result["metrics_count"] == 3
    assert result["agent_estimate"] == 2
    assert result["host_estimate"] == 3
    assert any(url.endswith("/prometheus/api/v1/query") for url in client.request_urls)


@pytest.mark.asyncio
async def test_service_wrapper_methods():
    svc = AgentService()
    hb = AgentHeartbeat(name="a", tenant_id="t")
    svc.update_from_heartbeat(hb)
    agents = svc.list_agents()
    assert len(agents) == 1
    assert svc.extract_metrics_count({}) == 0
    assert svc.extract_metrics_series({}) == []
    client = DummyClient({"data": {"result": []}})
    result = await svc.key_activity("k", client)
    assert not result["metrics_active"]
    assert result["metrics_count"] == 0


@pytest.mark.asyncio
async def test_query_key_volume_series_success():
    payload = {
        "data": {
            "result": [
                {
                    "values": [
                        [1711000000, "3"],
                        [1711000300, "6"],
                    ]
                }
            ]
        }
    }
    client = DummyClient(payload)
    result = await helpers.query_key_volume_series("key", client)
    assert result == [
        {"ts": 1711000000, "value": 3},
        {"ts": 1711000300, "value": 6},
    ]
    assert client.last_url.endswith("/prometheus/api/v1/query_range")
