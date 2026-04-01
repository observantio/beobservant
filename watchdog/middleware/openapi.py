"""
OpenAPI customization wiring for the Watchdog FastAPI app.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def _ensure_cookie_security_scheme(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    if not isinstance(components, dict):
        return
    security_schemes = components.setdefault("securitySchemes", {})
    if not isinstance(security_schemes, dict):
        return
    security_schemes.setdefault(
        "WatchdogCookieAuth",
        {
            "type": "apiKey",
            "in": "cookie",
            "name": "watchdog_token",
            "description": "Authenticate using the watchdog_token cookie (same token as Bearer).",
        },
    )


def _normalize_operation_security(operation: dict[str, Any]) -> None:
    security = operation.get("security")
    if not isinstance(security, list):
        return

    has_bearer = any(isinstance(req, dict) and "HTTPBearer" in req for req in security)
    has_cookie = any(isinstance(req, dict) and "WatchdogCookieAuth" in req for req in security)

    if has_cookie and not has_bearer:
        operation["security"] = [{"HTTPBearer": []}]
    elif has_bearer and has_cookie:
        operation["security"] = [req for req in security if isinstance(req, dict) and "HTTPBearer" in req]


def _apply_inferred_responses(path: str, method: str, operation: dict[str, Any]) -> None:
    responses = operation.setdefault("responses", {})
    if not isinstance(responses, dict):
        return

    security = operation.get("security")
    is_secured = isinstance(security, list) and len(security) > 0
    has_path_params = "{" in path and "}" in path
    has_request_body = "requestBody" in operation
    upper_method = method.upper()

    inferred: dict[str, dict[str, str]] = {}

    if is_secured:
        inferred["401"] = {"description": "Unauthorized"}
        inferred["403"] = {"description": "Forbidden"}

    if has_request_body or upper_method in {"POST", "PUT", "PATCH", "DELETE"}:
        inferred["400"] = {"description": "Bad Request"}

    if has_path_params:
        inferred["404"] = {"description": "Not Found"}

    if path.startswith("/api/auth/login") or path.startswith("/api/auth/register") or path.startswith("/api/auth/oidc/"):
        inferred["429"] = {"description": "Too Many Requests"}

    if path.startswith("/api/auth/login") or path.startswith("/api/auth/register"):
        inferred["403"] = {"description": "Forbidden"}

    if path.startswith("/api/auth/oidc/exchange"):
        inferred["401"] = {"description": "Unauthorized"}

    if path.startswith("/api/alertmanager/"):
        inferred["401"] = {"description": "Unauthorized"}
        inferred["403"] = {"description": "Forbidden"}

    for code, response in inferred.items():
        responses.setdefault(code, response)


def install_custom_openapi(app: FastAPI) -> None:
    def custom_openapi() -> Any:
        if app.openapi_schema:
            return app.openapi_schema

        schema_value: Any = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        if not isinstance(schema_value, dict):
            return schema_value
        schema = schema_value

        _ensure_cookie_security_scheme(schema)

        paths = schema.get("paths")
        if isinstance(paths, dict):
            for path, path_item in paths.items():
                if not isinstance(path_item, dict):
                    continue
                for method, operation in path_item.items():
                    if not isinstance(operation, dict):
                        continue
                    _normalize_operation_security(operation)
                    _apply_inferred_responses(path, method, operation)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
