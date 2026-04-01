"""
OpenAPI middleware tests.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from fastapi import FastAPI

from middleware import openapi as openapi_middleware


def test_apply_inferred_responses_handles_non_dict_responses() -> None:
    operation: dict[str, object] = {"responses": []}
    openapi_middleware._apply_inferred_responses("/api/gateway/validate", "POST", operation)  # type: ignore[arg-type]
    assert operation["responses"] == []


def test_apply_inferred_responses_for_validate_paths() -> None:
    validate: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/gateway/validate/{path}", "DELETE", validate)  # type: ignore[arg-type]
    responses = validate["responses"]
    assert isinstance(responses, dict)
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["403"]["description"] == "Forbidden"
    assert responses["404"]["description"] == "Not Found"
    assert responses["429"]["description"] == "Too Many Requests"
    assert responses["503"]["description"] == "Service Unavailable"
    assert responses["400"]["description"] == "Bad Request"

    health: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/gateway/health", "GET", health)  # type: ignore[arg-type]
    health_responses = health["responses"]
    assert isinstance(health_responses, dict)
    assert health_responses == {}


def test_install_custom_openapi_cache_and_schema_walk(monkeypatch) -> None:
    app = FastAPI()
    app.openapi_schema = {"cached": True}
    openapi_middleware.install_custom_openapi(app)
    assert app.openapi() == {"cached": True}

    app2 = FastAPI()
    openapi_middleware.install_custom_openapi(app2)
    fake_schema = {
        "paths": {
            "/api/gateway/validate/{path}": {
                "post": {},
                "trace": "skip",
            },
            "/api/gateway/health": {"get": {}},
            "/api/gateway/skip": "skip",
        }
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: fake_schema)
    generated = app2.openapi()
    responses = generated["paths"]["/api/gateway/validate/{path}"]["post"]["responses"]
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["403"]["description"] == "Forbidden"
    assert responses["404"]["description"] == "Not Found"
    assert responses["429"]["description"] == "Too Many Requests"
    assert responses["503"]["description"] == "Service Unavailable"
    assert responses["400"]["description"] == "Bad Request"

    app3 = FastAPI()
    openapi_middleware.install_custom_openapi(app3)
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: {"paths": []})
    assert app3.openapi()["paths"] == []

