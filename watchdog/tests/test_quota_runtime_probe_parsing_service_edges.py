"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from tests._env import ensure_test_env

ensure_test_env()

from db_models import Base, Tenant, User, UserApiKey
from models.access.auth_models import Role, TokenData
from services.quota_service import parsing as parsing_module
from services.quota_service.parsing import (
    compute_remaining,
    extract_from_text,
    extract_nested_numeric,
    extract_path,
    extract_prom_result,
    extract_tenant_scoped_numeric,
    format_with_tenant,
    prom_query_url,
    response_payload,
)
from services.quota_service.runtime_probe import NativeQuotaFetchParams, QuotaProbe, RuntimeQuotaProbe
from services.quota_service.service import QuotaService, RuntimeQuotaResolveParams
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class _Resp:
    def __init__(self, payload=None, *, text="", status_error: Exception | None = None):
        self._payload = payload
        self.text = text
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _error_response(status_code: int) -> _Resp:
    request = httpx.Request("GET", "http://quota.test")
    response = httpx.Response(status_code, request=request)
    return _Resp(status_error=httpx.HTTPStatusError("bad", request=request, response=response))


def _httpx_module_for(responder):
    class _Client:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            return await responder(url, **kwargs)

    return SimpleNamespace(AsyncClient=_Client, HTTPError=httpx.HTTPError)


def _probe_with(responder, *, cfg_overrides=None) -> RuntimeQuotaProbe:
    cfg = SimpleNamespace(
        LOKI_URL="http://loki:3100",
        TEMPO_URL="http://tempo:3200",
        QUOTA_USAGE_WINDOW_SECONDS=300,
        QUOTA_NATIVE_TIMEOUT_SECONDS=2.0,
        QUOTA_PROMETHEUS_TIMEOUT_SECONDS=2.0,
        QUOTA_PROMETHEUS_BASE_URL="http://mimir:9009",
        QUOTA_NATIVE_ENABLED=True,
        QUOTA_PROMETHEUS_ENABLED=True,
    )
    for key, value in (cfg_overrides or {}).items():
        setattr(cfg, key, value)

    return RuntimeQuotaProbe(
        config_getter=lambda: cfg,
        httpx_getter=lambda: _httpx_module_for(responder),
    )


def _mk_token() -> TokenData:
    return TokenData(
        user_id="u1",
        username="user-1",
        tenant_id="tenant-1",
        org_id="org-1",
        role=Role.USER,
        permissions=[],
    )


def _session_with_seed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Tenant(id="tenant-1", name="Tenant1", display_name="Tenant1", is_active=True))
    session.add(
        User(
            id="u1",
            tenant_id="tenant-1",
            username="user-1",
            email="u1@example.com",
            hashed_password="x",
            org_id="org-1",
            is_active=True,
        )
    )
    session.add(
        UserApiKey(
            id="k1",
            tenant_id="tenant-1",
            user_id="u1",
            name="Key-1",
            key="org-1",
            is_default=True,
            is_enabled=True,
        )
    )
    session.commit()
    return session


def test_parsing_helpers_edge_paths():
    assert format_with_tenant("limit_{tenant_id}", "org-a") == "limit_org-a"
    assert format_with_tenant("limit_{tenant}", "org-a") == "limit_{tenant}"

    assert extract_path({"a": {"b": True}}, "a.b") == 1.0
    assert extract_path({"a": {"b": "3.5"}}, "a.b") == 3.5
    assert extract_path({"a": {"b": "NaN-ish"}}, "a.b") is None
    assert extract_path({"a": {"b": 4}}, "a.b") == 4.0
    assert extract_path({"a": {}}, "a.b") is None

    assert extract_from_text("\nmax_streams_per_user: 42\n", "max_streams_per_user") == 42.0
    assert extract_from_text("\nmax_streams_per_user: none\n", "max_streams_per_user") is None
    assert extract_from_text("", "max_streams_per_user") is None

    class _BadJson:
        text = "raw: 1"

        def json(self):
            raise ValueError("boom")

    assert response_payload(_BadJson()) == {"__raw_text": "raw: 1"}
    assert response_payload(SimpleNamespace(text="")) == {}
    assert response_payload(SimpleNamespace(json=lambda: [1, 2])) == [1, 2]
    assert response_payload(SimpleNamespace(json=lambda: "plain-text", text="fallback")) == {"__raw_text": "fallback"}

    payload = {
        "tenant-a": {"streams": "7"},
        "runtime_config": {"overrides": {"tenant-b": {"streams": 9}}},
    }
    assert extract_tenant_scoped_numeric(payload, tenant_id="tenant-a", key_candidates=["streams"]) == 7.0
    assert extract_tenant_scoped_numeric(payload, tenant_id="tenant-b", key_candidates=["streams"]) == 9.0
    assert extract_tenant_scoped_numeric([], tenant_id="tenant-a", key_candidates=["streams"]) is None

    assert extract_nested_numeric({"data": {"x": "2"}}, ["missing", "data.x"]) == 2.0
    assert compute_remaining(10, 3) == 7.0
    assert compute_remaining(1, 3) == 0.0
    assert compute_remaining(None, 3) is None

    assert prom_query_url(SimpleNamespace(QUOTA_PROMETHEUS_BASE_URL="")) == ""
    assert (
        prom_query_url(SimpleNamespace(QUOTA_PROMETHEUS_BASE_URL="http://mimir/api/v1/query"))
        == "http://mimir/api/v1/query"
    )
    assert (
        prom_query_url(SimpleNamespace(QUOTA_PROMETHEUS_BASE_URL="http://mimir/prometheus"))
        == "http://mimir/prometheus/api/v1/query"
    )
    assert (
        prom_query_url(SimpleNamespace(QUOTA_PROMETHEUS_BASE_URL="http://mimir"))
        == "http://mimir/prometheus/api/v1/query"
    )

    assert extract_prom_result({"data": {"result": [{"value": [123, "9.25"]}]}}) == 9.25
    assert extract_prom_result([]) is None
    assert extract_prom_result({"data": []}) is None
    assert extract_prom_result({"data": {"result": ["bad"]}}) is None
    assert extract_prom_result({"data": {"result": [{"value": {"ts": 1}}]}}) is None
    assert extract_prom_result({"data": {"result": []}}) is None
    assert extract_prom_result({"data": {"result": [{"value": [123, "bad"]}]}}) is None
    assert extract_path({"a": {"b": object()}}, "a.b") is None


def test_extract_from_text_valueerror_path(monkeypatch):
    class _Match:
        def group(self, _index: int) -> str:
            return "not-a-number"

    class _Pattern:
        def search(self, _text: str):
            return _Match()

    monkeypatch.setattr(parsing_module.re, "compile", lambda _pattern: _Pattern())
    assert extract_from_text("anything", "k") is None


def test_quota_probe_dataclass_flags():
    complete = QuotaProbe(source="native", limit=10.0, used=3.0)
    partial = QuotaProbe(source="native", limit=10.0, used=None)
    empty = QuotaProbe(source="none", limit=None, used=None)

    assert complete.complete() is True
    assert partial.complete() is False
    assert partial.any_value() is True
    assert empty.any_value() is False


@pytest.mark.asyncio
async def test_runtime_probe_payload_extractors_and_candidate_paths():
    async def _unused(_url, **_kwargs):
        return _Resp({})

    probe = _probe_with(_unused)

    assert probe.loki_limit_from_payload({"cfg": {"limit": 20}}, "cfg.limit", "org-a") == 20.0
    assert probe.loki_limit_from_payload({"__raw_text": "max_global_streams_per_user: 30"}, "", "org-a") == 30.0
    assert probe.loki_limit_from_payload({"org-a": {"max_streams_per_user": 8}}, "", "org-a") == 8.0
    assert probe.loki_limit_from_payload({"__raw_text": "unrelated: 1"}, "", "org-a") is None
    assert probe.tempo_limit_from_payload({"limits": {"max_traces_per_user": 11}}, "", "org-a") == 11.0
    assert probe.tempo_limit_from_payload({"org-a": {"max_traces_per_user": 13}}, "", "org-a") == 13.0
    assert probe.tempo_limit_from_payload({"__raw_text": "max_bytes_per_trace: 27"}, "", "org-a") == 27.0
    assert probe.tempo_limit_from_payload({"__raw_text": "other: 4"}, "", "org-a") is None
    assert probe.loki_limit_from_payload([1, 2, 3], "", "org-a") is None
    assert probe.tempo_limit_from_payload([1, 2, 3], "", "org-a") is None
    assert probe.loki_used_from_payload({"org-a": {"streams": 6}}, "", "org-a") == 6.0
    assert probe.tempo_used_from_payload({"usage": {"active_traces": "7"}}, "", "org-a") == 7.0
    assert probe.tempo_used_from_payload({"org-a": {"active_traces": 9}}, "", "org-a") == 9.0

    assert probe.candidate_native_paths(service_name="loki", configured_path="/config") == [
        "/config",
        "/loki/api/v1/status/limits",
        "/loki/api/v1/status/config",
    ]
    assert probe.candidate_native_paths(service_name="tempo", configured_path="") == [
        "/status/overrides",
        "/api/status/overrides",
        "/status/config",
        "/api/status/config",
    ]


@pytest.mark.asyncio
async def test_fetch_loki_used_streams_series_then_stats_then_none():
    calls = {"n": 0}

    async def _series_first(url, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp({"data": [{"stream": 1}, {"stream": 2}]})
        return _Resp({"streams": 9})

    probe = _probe_with(_series_first)
    assert await probe.fetch_loki_used_streams(tenant_id="org-a") == 2.0

    calls["n"] = 0

    async def _stats_fallback(url, **_kwargs):
        calls["n"] += 1
        if "/series" in url:
            return _Resp({"data": "unexpected"})
        return _Resp({"stats": {"streams": 5}})

    probe2 = _probe_with(_stats_fallback)
    assert await probe2.fetch_loki_used_streams(tenant_id="org-a") == 5.0

    async def _none_paths(url, **_kwargs):
        if "/series" in url:
            return _Resp({"data": "unexpected"})
        return _Resp({"stats": {"streams": "bad"}})

    probe3 = _probe_with(_none_paths)
    assert await probe3.fetch_loki_used_streams(tenant_id="org-a") is None

    async def _list_payload(url, **_kwargs):
        if "/series" in url:
            return _Resp([1, 2, 3])
        return _Resp({"streams": 2})

    probe4 = _probe_with(_list_payload)
    assert await probe4.fetch_loki_used_streams(tenant_id="org-a") == 2.0


@pytest.mark.asyncio
async def test_fetch_tempo_used_traces_all_paths():
    async def _primary_success(url, **_kwargs):
        return _Resp({"traces": [{"id": 1}, {"id": 2}, {"id": 3}]})

    probe = _probe_with(_primary_success)
    assert await probe.fetch_tempo_used_traces(tenant_id="org-a") == 3.0

    state = {"i": 0}

    async def _secondary_success(url, **_kwargs):
        state["i"] += 1
        if state["i"] == 1:
            return _error_response(500)
        return _Resp({"traces": [{"id": 1}]})

    probe2 = _probe_with(_secondary_success)
    assert await probe2.fetch_tempo_used_traces(tenant_id="org-a") == 1.0

    async def _usage_success(url, **_kwargs):
        if "/api/search" in url:
            return _error_response(500)
        if url.endswith("/status/usage"):
            return _Resp({"usage": {"active_traces": 4}})
        return _Resp({"usage": {"active_traces": 8}})

    probe3 = _probe_with(_usage_success)
    assert await probe3.fetch_tempo_used_traces(tenant_id="org-a") == 4.0

    async def _all_fail(url, **_kwargs):
        return _error_response(500)

    probe4 = _probe_with(_all_fail)
    assert await probe4.fetch_tempo_used_traces(tenant_id="org-a") is None


@pytest.mark.asyncio
async def test_fetch_native_quota_paths():
    probe_disabled = _probe_with(lambda _u, **_k: _Resp({}), cfg_overrides={"QUOTA_NATIVE_ENABLED": False})
    out = await probe_disabled.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="loki",
            base_url="http://loki:3100",
            path_template="/x",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out.source == "none"

    probe_no_paths = _probe_with(lambda _u, **_k: _Resp({}))
    out2 = await probe_no_paths.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="other",
            base_url="http://x",
            path_template="",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out2.source == "none"

    async def _generic(url, **_kwargs):
        return _Resp({"limit": 10, "used": 4})

    probe_generic = _probe_with(_generic)
    out3 = await probe_generic.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="other",
            base_url="http://x",
            path_template="/quota",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out3.source == "native"
    assert out3.limit == 10.0 and out3.used == 4.0

    seq = {"n": 0}

    async def _partial(url, **_kwargs):
        seq["n"] += 1
        if seq["n"] == 1:
            return _Resp({"limit": 12})
        return _error_response(500)

    probe_partial = _probe_with(_partial)
    out4 = await probe_partial.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="other",
            base_url="http://x",
            path_template="/quota",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out4.limit == 12.0 and out4.used is None

    async def _all_errors(url, **_kwargs):
        return _error_response(500)

    probe_errors = _probe_with(_all_errors)
    out5 = await probe_errors.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="other",
            base_url="http://x",
            path_template="/quota",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out5.message == "Other runtime quota endpoint unavailable"


@pytest.mark.asyncio
async def test_fetch_native_quota_handles_fallback_exceptions(monkeypatch):
    async def _payload(url, **_kwargs):
        return _Resp({"limit": 30})

    probe = _probe_with(_payload)

    async def _boom_loki(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(probe, "fetch_loki_used_streams", _boom_loki)
    out = await probe.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="loki",
            base_url="http://loki:3100",
            path_template="/quota",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out.limit == 30.0 and out.used is None

    async def _boom_tempo(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(probe, "fetch_tempo_used_traces", _boom_tempo)
    out2 = await probe.fetch_native_quota(
        NativeQuotaFetchParams(
            service_name="tempo",
            base_url="http://tempo:3200",
            path_template="/quota",
            tenant_id="org-a",
            limit_field="limit",
            used_field="used",
        )
    )
    assert out2.limit == 30.0 and out2.used is None


@pytest.mark.asyncio
async def test_prometheus_probe_paths(monkeypatch):
    async def _prom(url, **kwargs):
        q = (kwargs.get("params") or {}).get("query", "")
        if "limit" in q:
            return _Resp({"data": {"result": [{"value": [1, "100"]}]}})
        if "used" in q:
            return _Resp({"data": {"result": [{"value": [1, "40"]}]}})
        return _Resp({"data": {"result": []}})

    probe = _probe_with(_prom)

    assert await probe.query_prometheus_value("", "org-a") is None
    assert await probe.query_prometheus_value('loki_limit{tenant_id="{tenant_id}"}', "org-a") == 100.0

    out = await probe.fetch_prometheus_quota(
        service_name="loki",
        tenant_id="org-a",
        limit_query='loki_limit{tenant_id="{tenant_id}"}',
        used_query='loki_used{tenant_id="{tenant_id}"}',
    )
    assert out.source == "prometheus" and out.limit == 100.0 and out.used == 40.0

    probe_disabled = _probe_with(_prom, cfg_overrides={"QUOTA_PROMETHEUS_ENABLED": False})
    out2 = await probe_disabled.fetch_prometheus_quota(
        service_name="loki",
        tenant_id="org-a",
        limit_query="x",
        used_query="y",
    )
    assert out2.source == "none"

    probe_no_url = _probe_with(_prom, cfg_overrides={"QUOTA_PROMETHEUS_BASE_URL": ""})
    out3 = await probe_no_url.fetch_prometheus_quota(
        service_name="loki",
        tenant_id="org-a",
        limit_query="x",
        used_query="y",
    )
    assert out3.source == "none"

    out4 = await probe.fetch_prometheus_quota(
        service_name="loki",
        tenant_id="org-a",
        limit_query="",
        used_query="",
    )
    assert out4.source == "none"

    async def _raise(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(probe, "query_prometheus_value", _raise)
    out5 = await probe.fetch_prometheus_quota(
        service_name="tempo",
        tenant_id="org-a",
        limit_query="limit",
        used_query="used",
    )
    assert out5.message == "Tempo quota fallback unavailable"


@pytest.mark.asyncio
async def test_quota_service_resolve_runtime_quota_degraded_messages():
    db = _session_with_seed()

    @contextmanager
    def _fake_db():
        yield db

    class _Probe:
        def __init__(self, native, prom):
            self.native = native
            self.prom = prom

        async def fetch_native_quota(self, *_args, **_kwargs):
            return self.native

        async def fetch_prometheus_quota(self, **_kwargs):
            return self.prom

    cfg = SimpleNamespace(
        MAX_API_KEYS_PER_USER=10,
        DEFAULT_ORG_ID="org-default",
        LOKI_URL="http://loki:3100",
        TEMPO_URL="http://tempo:3200",
        LOKI_QUOTA_NATIVE_PATH="/x",
        LOKI_QUOTA_NATIVE_LIMIT_FIELD="limit",
        LOKI_QUOTA_NATIVE_USED_FIELD="used",
        LOKI_QUOTA_PROM_LIMIT_QUERY="",
        LOKI_QUOTA_PROM_USED_QUERY="",
        TEMPO_QUOTA_NATIVE_PATH="/x",
        TEMPO_QUOTA_NATIVE_LIMIT_FIELD="limit",
        TEMPO_QUOTA_NATIVE_USED_FIELD="used",
        TEMPO_QUOTA_PROM_LIMIT_QUERY="",
        TEMPO_QUOTA_PROM_USED_QUERY="",
    )

    svc_usage_only = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(QuotaProbe("native", None, 7.0), QuotaProbe("none", None, None)),
    )
    out1 = await svc_usage_only._resolve_runtime_quota(
        RuntimeQuotaResolveParams(
            service_name="loki",
            base_url="http://loki:3100",
            native_path="/x",
            native_limit_field="limit",
            native_used_field="used",
            prom_limit_query="",
            prom_used_query="",
            tenant_id="org-1",
        )
    )
    assert out1.status == "degraded"
    assert "usage is available" in str(out1.message)

    svc_limit_only = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(QuotaProbe("native", 11.0, None), QuotaProbe("none", None, None)),
    )
    out2 = await svc_limit_only._resolve_runtime_quota(
        RuntimeQuotaResolveParams(
            service_name="tempo",
            base_url="http://tempo:3200",
            native_path="/x",
            native_limit_field="limit",
            native_used_field="used",
            prom_limit_query="",
            prom_used_query="",
            tenant_id="org-1",
        )
    )
    assert out2.status == "degraded"
    assert "limit is available" in str(out2.message)

    svc_mixed_partial = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(QuotaProbe("native", 15.0, None), QuotaProbe("prometheus", None, 6.0)),
    )
    out3 = await svc_mixed_partial._resolve_runtime_quota(
        RuntimeQuotaResolveParams(
            service_name="loki",
            base_url="http://loki:3100",
            native_path="/x",
            native_limit_field="limit",
            native_used_field="used",
            prom_limit_query="ql",
            prom_used_query="qu",
            tenant_id="org-1",
        )
    )
    assert out3.status == "degraded"
    assert out3.source == "native"
    assert out3.message == "Partial quota data available from upstream"

    svc_none = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(QuotaProbe("native", None, None), QuotaProbe("prometheus", None, None)),
    )
    out4 = await svc_none._resolve_runtime_quota(
        RuntimeQuotaResolveParams(
            service_name="tempo",
            base_url="http://tempo:3200",
            native_path="/x",
            native_limit_field="limit",
            native_used_field="used",
            prom_limit_query="ql",
            prom_used_query="qu",
            tenant_id="org-1",
        )
    )
    assert out4.status == "unavailable"
    assert out4.source == "none"

    svc_with_messages = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(
            QuotaProbe("native", None, 3.0, message="native unavailable"),
            QuotaProbe("prometheus", None, None, message="prom unavailable"),
        ),
    )
    out5 = await svc_with_messages._resolve_runtime_quota(
        RuntimeQuotaResolveParams(
            service_name="loki",
            base_url="http://loki:3100",
            native_path="/x",
            native_limit_field="limit",
            native_used_field="used",
            prom_limit_query="ql",
            prom_used_query="qu",
            tenant_id="org-1",
        )
    )
    assert out5.status == "degraded"
    assert out5.message == "native unavailable; prom unavailable"


@pytest.mark.asyncio
async def test_quota_service_get_quotas_resolves_scope_and_api_key_count():
    db = _session_with_seed()

    @contextmanager
    def _fake_db():
        yield db

    captured = {}

    class _Probe:
        async def fetch_native_quota(self, params: NativeQuotaFetchParams):
            captured.setdefault("native", []).append(params.tenant_id)
            return QuotaProbe("native", 20.0, 5.0)

        async def fetch_prometheus_quota(self, **kwargs):
            captured.setdefault("prom", []).append(kwargs["tenant_id"])
            return QuotaProbe("none", None, None)

    cfg = SimpleNamespace(
        MAX_API_KEYS_PER_USER=2,
        DEFAULT_ORG_ID="org-default",
        LOKI_URL="http://loki:3100",
        TEMPO_URL="http://tempo:3200",
        LOKI_QUOTA_NATIVE_PATH="/x",
        LOKI_QUOTA_NATIVE_LIMIT_FIELD="limit",
        LOKI_QUOTA_NATIVE_USED_FIELD="used",
        LOKI_QUOTA_PROM_LIMIT_QUERY="",
        LOKI_QUOTA_PROM_USED_QUERY="",
        TEMPO_QUOTA_NATIVE_PATH="/x",
        TEMPO_QUOTA_NATIVE_LIMIT_FIELD="limit",
        TEMPO_QUOTA_NATIVE_USED_FIELD="used",
        TEMPO_QUOTA_PROM_LIMIT_QUERY="",
        TEMPO_QUOTA_PROM_USED_QUERY="",
    )

    service = QuotaService(
        config_getter=lambda: cfg,
        db_session_factory=lambda: _fake_db(),
        runtime_probe=_Probe(),
    )

    token = _mk_token()
    out = await service.get_quotas(token, tenant_scope="scope-override")
    assert out.api_keys.current == 1
    assert out.api_keys.max == 2
    assert out.api_keys.remaining == 1
    assert captured["native"] == ["scope-override", "scope-override"]
