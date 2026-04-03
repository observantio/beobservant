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


def test_ensure_error_schema_creates_component() -> None:
    schema: dict[str, object] = {}
    openapi_middleware._ensure_error_schema(schema)
    components = schema["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    error_response = schemas["ErrorResponse"]
    assert error_response["required"] == ["detail"]
    properties = error_response["properties"]
    assert properties["error"]["type"] == "string"
    assert properties["message"]["type"] == "string"
    assert properties["request_id"]["anyOf"][1]["type"] == "null"


def test_ensure_json_error_response_handles_non_dict_responses() -> None:
    operation: dict[str, object] = {"responses": []}
    openapi_middleware._ensure_json_error_response(operation, "401", "Unauthorized")  # type: ignore[arg-type]
    assert operation["responses"] == []


def test_ensure_validate_error_responses() -> None:
    operation: dict[str, object] = {}
    openapi_middleware._ensure_validate_error_responses(operation)  # type: ignore[arg-type]
    responses = operation["responses"]
    assert isinstance(responses, dict)
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["503"]["description"] == "Service Unavailable"
    assert responses["400"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorResponse"


def test_install_custom_openapi_cache_and_schema_walk(monkeypatch) -> None:
    app = FastAPI()
    app.openapi_schema = {"cached": True}
    openapi_middleware.install_custom_openapi(app)
    assert app.openapi() == {"cached": True}

    app2 = FastAPI()
    openapi_middleware.install_custom_openapi(app2)
    fake_schema = {
        "paths": {
            "/api/gateway/validate": {
                "post": {
                    "responses": {
                        "200": {"description": "OK"},
                    }
                },
                "trace": "skip",
            },
            "/api/gateway/validate/{path}": {"post": {}},
            "/api/gateway/validate/{path:path}": {"post": {}},
            "/api/gateway/health": {"get": {}},
        },
        "components": {"schemas": {}},
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: fake_schema)
    generated = app2.openapi()

    responses = generated["paths"]["/api/gateway/validate"]["post"]["responses"]
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["429"]["description"] == "Too Many Requests"
    assert responses["503"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorResponse"

    assert "/api/gateway/validate/{path}" not in generated["paths"]
    assert "/api/gateway/validate/{path:path}" not in generated["paths"]
    assert generated["jsonSchemaDialect"] == openapi_middleware.JSON_SCHEMA_DIALECT

    app3 = FastAPI()
    openapi_middleware.install_custom_openapi(app3)
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: {"paths": []})
    assert app3.openapi()["paths"] == []


def test_openapi_helper_guards_cover_remaining_branches() -> None:
    schema_bad_components = {"components": []}
    openapi_middleware._ensure_error_schema(schema_bad_components)  # type: ignore[arg-type]
    assert schema_bad_components["components"] == []

    schema_bad_schemas = {"components": {"schemas": []}}
    openapi_middleware._ensure_error_schema(schema_bad_schemas)  # type: ignore[arg-type]
    assert schema_bad_schemas["components"]["schemas"] == []

    operation_non_dict_response: dict[str, object] = {"responses": {"401": []}}
    openapi_middleware._ensure_json_error_response(operation_non_dict_response, "401", "Unauthorized")  # type: ignore[arg-type]
    assert operation_non_dict_response["responses"]["401"] == []

    operation_non_dict_content: dict[str, object] = {
        "responses": {"401": {"description": "Unauthorized", "content": []}}
    }
    openapi_middleware._ensure_json_error_response(operation_non_dict_content, "401", "Unauthorized")  # type: ignore[arg-type]
    assert operation_non_dict_content["responses"]["401"]["content"] == []


def test_install_custom_openapi_handles_non_dict_validate_shapes(monkeypatch) -> None:
    app = FastAPI()
    openapi_middleware.install_custom_openapi(app)
    schema_with_non_dict_validate = {
        "paths": {
            "/api/gateway/validate": "not-a-dict",
            "/api/gateway/validate/{path}": {"post": {}},
            "/api/gateway/validate/{path:path}": {"post": {}},
        },
        "components": {"schemas": {}},
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: schema_with_non_dict_validate)
    generated = app.openapi()
    assert "/api/gateway/validate/{path}" not in generated["paths"]
    assert "/api/gateway/validate/{path:path}" not in generated["paths"]

    app2 = FastAPI()
    openapi_middleware.install_custom_openapi(app2)
    schema_with_non_dict_post = {
        "paths": {
            "/api/gateway/validate": {"post": "not-a-dict"},
            "/api/gateway/validate/{path}": {"post": {}},
            "/api/gateway/validate/{path:path}": {"post": {}},
        },
        "components": {"schemas": {}},
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: schema_with_non_dict_post)
    generated2 = app2.openapi()
    assert generated2["paths"]["/api/gateway/validate"]["post"] == "not-a-dict"
