"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")
os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "False")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")
from datetime import UTC, datetime, timedelta

import pytest
from models.observability.agent_models import AgentHeartbeat, AgentInfo
from services.agent import helpers
from services.agent_service import AgentService


def test_update_registry_new_and_existing():
    registry: dict[str, AgentInfo] = {}
    now = datetime.now(UTC)
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

    hb3 = AgentHeartbeat(
        name="a", tenant_id="t", timestamp=later, attributes={"host.name": "updated-host"}, signal=None
    )
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
    assert (
        helpers.mimir_prometheus_url("http://mimir/prometheus", "api/v1/query_range")
        == "http://mimir/prometheus/api/v1/query_range"
    )


def test_mimir_prometheus_url_handles_empty_base_and_suffix():
    assert helpers.mimir_prometheus_url("", "") == "/"
    assert helpers.mimir_prometheus_url("   ", "api/v1/query") == "/api/v1/query"


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


class DummyClientWithFailures:
    def __init__(self, query_payload, by_path=None, raise_paths=None):
        self.query_payload = query_payload
        self.by_path = by_path or {}
        self.raise_paths = set(raise_paths or [])
        self.request_urls = []

    async def get(self, url, params=None, headers=None):
        url_text = str(url)
        self.request_urls.append(url_text)
        for path in self.raise_paths:
            if path in url_text:
                raise RuntimeError(f"forced failure for {path}")

        payload = self.query_payload
        for path, override in self.by_path.items():
            if path in url_text:
                payload = override
                break

        class Resp:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

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
async def test_query_key_activity_uses_fallback_agent_label_candidates():
    payload = {"data": {"result": [{"value": [0, "9"]}]}}
    client = DummyClientWithFailures(
        payload,
        by_path={
            "/label/instance/values": {"data": []},
            "/label/job/values": {"data": ["job-a", "job-b", "job-c"]},
            "/label/host.name/values": {"data": ["host-a"]},
        },
    )
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"] is True
    assert result["metrics_count"] == 9
    assert result["agent_estimate"] == 3
    assert result["host_estimate"] == 1


@pytest.mark.asyncio
async def test_query_key_activity_falls_back_to_host_hostname_when_host_name_fails():
    payload = {"data": {"result": [{"value": [0, "5"]}]}}
    client = DummyClientWithFailures(
        payload,
        by_path={
            "/label/instance/values": {"data": ["inst-a"]},
            "/label/host.hostname/values": {"data": ["node-a", "node-b"]},
        },
        raise_paths={"/label/host.name/values"},
    )
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"] is True
    assert result["agent_estimate"] == 1
    assert result["host_estimate"] == 2


@pytest.mark.asyncio
async def test_query_key_activity_does_not_use_instance_for_host_estimate():
    payload = {"data": {"result": [{"value": [0, "12"]}]}}
    client = DummyClient(
        payload,
        by_path={
            "/label/instance/values": {"data": ["inst-a", "inst-b", "inst-c", "inst-d"]},
            # Simulate missing host labels in Mimir for this scope.
            "/label/host.name/values": {"data": []},
            "/label/host.hostname/values": {"data": []},
        },
    )
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"]
    assert result["agent_estimate"] == 4
    # Host estimate should remain unknown (0) instead of inflating from "instance".
    assert result["host_estimate"] == 0


@pytest.mark.asyncio
async def test_query_key_activity_skips_label_queries_when_metrics_absent():
    payload = {"data": {"result": [{"value": [0, "0"]}]}}
    client = DummyClientWithFailures(payload)
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"] is False
    assert result["metrics_count"] == 0
    assert result["agent_estimate"] == 0
    assert result["host_estimate"] == 0
    assert len(client.request_urls) == 1
    assert client.request_urls[0].endswith("/prometheus/api/v1/query")


@pytest.mark.asyncio
async def test_query_key_activity_recovers_from_agent_label_query_exception():
    payload = {"data": {"result": [{"value": [0, "4"]}]}}
    client = DummyClient(
        payload,
        by_path={
            "/label/instance/values": ["not-an-object"],
            "/label/job/values": {"data": ["job-a", "job-b"]},
            "/label/host.name/values": {"data": ["host-a"]},
        },
    )
    result = await helpers.query_key_activity("key", client)
    assert result["metrics_active"] is True
    assert result["agent_estimate"] == 2
    assert result["host_estimate"] == 1


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


@pytest.mark.asyncio
async def test_query_label_value_count_rejects_non_object_payload():
    client = DummyClient(["unexpected"])
    with pytest.raises(ValueError, match="Unexpected label values payload"):
        await helpers.query_label_value_count("tenant-a", "instance", client)


def test_extract_metrics_series_guard_branches():
    assert helpers.extract_metrics_series({"data": {"result": {"unexpected": "shape"}}}) == []
    assert helpers.extract_metrics_series({"data": {"result": [["not-a-dict"]]}}) == []
    assert helpers.extract_metrics_series({"data": {"result": [{"values": "bad"}]}}) == []
    payload = {
        "data": {
            "result": [
                {
                    "values": [
                        "skip",
                        [1711000000],
                        [1711000300, "4"],
                    ]
                }
            ]
        }
    }
    assert helpers.extract_metrics_series(payload) == [{"ts": 1711000300, "value": 4}]


@pytest.mark.asyncio
async def test_query_key_volume_series_handles_invalid_payload_and_errors():
    invalid_payload_client = DummyClient(["bad-payload"])
    assert await helpers.query_key_volume_series("tenant-a", invalid_payload_client) == []

    failing_client = DummyClientWithFailures(
        {"data": {"result": [{"values": []}]}},
        raise_paths={"/query_range"},
    )
    assert await helpers.query_key_volume_series("tenant-a", failing_client) == []


@pytest.mark.asyncio
async def test_service_wrapper_key_volume_series_path():
    svc = AgentService()
    client = DummyClient({"data": {"result": [{"values": [[1711000000, "1"]]}]}})
    points = await svc.key_volume_series("tenant-a", client)
    assert points == [{"ts": 1711000000, "value": 1}]
    cached_points = await svc.key_volume_series("tenant-a", client)
    assert cached_points == points
    assert sum(url.endswith("/api/v1/query_range") for url in client.request_urls) == 1


@pytest.mark.asyncio
async def test_service_wrapper_key_activity_uses_cache():
    svc = AgentService()
    client = DummyClient({"data": {"result": [{"value": [1711000000, "3"]}]}})

    activity = await svc.key_activity("tenant-a", client)
    assert activity["metrics_active"] is True
    assert activity["metrics_count"] == 3

    cached_activity = await svc.key_activity("tenant-a", client)
    assert cached_activity == activity
    assert sum(url.endswith("/api/v1/query") for url in client.request_urls) == 1
