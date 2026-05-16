"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests._env import ensure_test_env

ensure_test_env()

from config import config
from routers import internal_router
from services.internal_service import InternalService


class DummyAuthService:
    def validate_otlp_token(self, token, *, suppress_errors=True):
        return "org123" if token == "good" else None


@pytest.fixture(autouse=True)
def patch_auth_service(monkeypatch):
    monkeypatch.setattr(internal_router, "internal_service", InternalService(auth_service=DummyAuthService()))
    monkeypatch.setattr(config, "SKIP_STARTUP_DB_INIT", True)
    monkeypatch.setattr(InternalService, "_get_internal_token", lambda self: "secret")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(internal_router.router)
    return TestClient(app)


def test_missing_header(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.get("/api/internal/otlp/validate?token=good")
    assert resp.status_code == 422


def test_service_token_not_configured(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", None)
    monkeypatch.setattr(InternalService, "_get_internal_token", lambda self: "")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "whatever"},
        json={"token": "good"},
    )
    assert resp.status_code == 500


def test_bad_header(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.get(
        "/api/internal/otlp/validate?token=good",
        headers={"X-Internal-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_invalid_token(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.get(
        "/api/internal/otlp/validate?token=bad",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 410


def test_query_path_disabled(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.get(
        "/api/internal/otlp/validate?token=good",
        headers={"X-Internal-Token": "secret"},
    )
    assert resp.status_code == 410


def test_success_post_body(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"org_id": "org123"}


def test_success_post_header_token(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret", "X-OTLP-Token": "good"},
        json={},
    )
    assert resp.status_code == 200
    assert resp.json() == {"org_id": "org123"}


def test_post_invalid_token(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "bad"},
    )
    assert resp.status_code == 404


def test_post_db_error_maps_to_503(monkeypatch, client):
    class FailingAuthService:
        def validate_otlp_token(self, token, *, suppress_errors=True):
            raise RuntimeError("db down")

    monkeypatch.setattr(internal_router, "internal_service", InternalService(auth_service=FailingAuthService()))
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Auth database unavailable"


def test_post_invalid_token_encoding_returns_400(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={
            "X-Internal-Token": "secret",
            "Content-Type": "application/json",
        },
        content=b'{"token":"bad\\ud800token"}',
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid token encoding"


def test_post_rejects_unknown_payload_fields(monkeypatch, client):
    monkeypatch.setattr(config, "GATEWAY_INTERNAL_SERVICE_TOKEN", "secret")
    resp = client.post(
        "/api/internal/otlp/validate",
        headers={"X-Internal-Token": "secret"},
        json={"token": "good", "unexpected": {}},
    )
    assert resp.status_code == 422
