"""
OpenAPI customization wiring for the Gatekeeper FastAPI app.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_VALIDATE_PATH = "/api/gateway/validate"
_ERROR_SCHEMA_REF = "#/components/schemas/ErrorResponse"
_STANDARD_ERROR_CODES = ("400", "401", "403", "404", "429", "503")


def _ensure_error_schema(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    if not isinstance(components, dict):
        return

    component_schemas = components.setdefault("schemas", {})
    if not isinstance(component_schemas, dict):
        return

    component_schemas.setdefault(
        "ErrorResponse",
        {
            "type": "object",
            "properties": {
                "error": {
                    "type": "string",
                    "title": "Error",
                    "description": "Stable error code identifier when available.",
                },
                "message": {
                    "type": "string",
                    "title": "Message",
                    "description": "Human-readable error message.",
                },
                "request_id": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ],
                    "title": "Request Id",
                    "description": "Request correlation identifier when available.",
                },
                "detail": {
                    "type": "string",
                    "title": "Detail",
                    "description": "Legacy FastAPI error message field.",
                }
            },
            "required": ["detail"],
            "title": "ErrorResponse",
        },
    )


def _ensure_json_error_response(operation: dict[str, Any], status_code: str, description: str) -> None:
    responses = operation.setdefault("responses", {})
    if not isinstance(responses, dict):
        return

    response = responses.setdefault(status_code, {"description": description})
    if not isinstance(response, dict):
        return

    response.setdefault("description", description)
    content = response.setdefault("content", {})
    if not isinstance(content, dict):
        return

    content.setdefault(
        "application/json",
        {
            "schema": {"$ref": _ERROR_SCHEMA_REF},
        },
    )


def _ensure_validate_error_responses(operation: dict[str, Any]) -> None:
    descriptions = {
        "400": "Bad Request",
        "401": "Unauthorized",
        "403": "Forbidden",
        "404": "Not Found",
        "429": "Too Many Requests",
        "503": "Service Unavailable",
    }
    for code in _STANDARD_ERROR_CODES:
        _ensure_json_error_response(operation, code, descriptions[code])


def install_custom_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        _ensure_error_schema(schema)

        paths = schema.get("paths", {})
        if isinstance(paths, dict):
            validate_path = paths.get(_VALIDATE_PATH)
            if isinstance(validate_path, dict):
                post_op = validate_path.get("post")
                if isinstance(post_op, dict):
                    _ensure_validate_error_responses(post_op)

            # Remove stale path-variant route docs if older snapshots leaked it.
            paths.pop(f"{_VALIDATE_PATH}/{{path}}", None)
            paths.pop(f"{_VALIDATE_PATH}/{{path:path}}", None)

        schema["jsonSchemaDialect"] = JSON_SCHEMA_DIALECT
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
