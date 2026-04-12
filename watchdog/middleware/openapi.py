"""
OpenAPI customization wiring for the Watchdog FastAPI app.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from http import HTTPStatus
import re
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

JSON_SCHEMA_DIALECT = "https://spec.openapis.org/oas/3.1/dialect/base"
_METHOD_ACTIONS: dict[str, str] = {
    "GET": "Retrieve",
    "POST": "Create",
    "PUT": "Replace",
    "PATCH": "Update",
    "DELETE": "Delete",
}
_GENERIC_DESCRIPTION_PATTERN = re.compile(r"^Handles [A-Z]+ requests for `/.+`\.$")
_NON_OPERATION_KEYS = {"summary", "description", "parameters", "servers"}
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
_UNTYPED_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"$ref": "#/components/schemas/JSONValue"},
}


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


def _ensure_alertmanager_security(path: str, operation: dict[str, Any]) -> None:
    if not path.startswith("/api/alertmanager/"):
        return
    if path == "/api/alertmanager/public/rules":
        return
    security = operation.get("security")
    if isinstance(security, list) and len(security) > 0:
        return
    operation["security"] = [{"HTTPBearer": []}]


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
        inferred["429"] = {"description": "Too Many Requests"}

    if has_request_body or upper_method in {"POST", "PUT", "PATCH", "DELETE"}:
        inferred["400"] = {"description": "Bad Request"}

    if has_path_params:
        inferred["404"] = {"description": "Not Found"}

    if (
        path.startswith("/api/auth/login")
        or path.startswith("/api/auth/register")
        or path.startswith("/api/auth/oidc/")
    ):
        inferred["429"] = {"description": "Too Many Requests"}

    if path.startswith("/api/auth/login") or path.startswith("/api/auth/register"):
        inferred["403"] = {"description": "Forbidden"}

    if path.startswith("/api/auth/oidc/exchange"):
        inferred["401"] = {"description": "Unauthorized"}

    if path.startswith("/api/alertmanager/") and path != "/api/alertmanager/public/rules":
        inferred["401"] = {"description": "Unauthorized"}
        inferred["403"] = {"description": "Forbidden"}

    if path.startswith("/api/resolver/"):
        inferred["502"] = {"description": "Bad Gateway"}

    if path == "/api/grafana/auth":
        inferred["400"] = {"description": "Bad Request"}
        inferred["403"] = {"description": "Forbidden"}
        inferred["429"] = {"description": "Too Many Requests"}

    if path == "/api/grafana/dashboards/search":
        inferred["400"] = {"description": "Bad Request"}

    if path == "/api/grafana/datasources" and upper_method == "POST":
        inferred["409"] = {"description": "Conflict"}

    if path == "/api/grafana/folders" and upper_method == "POST":
        inferred["409"] = {"description": "Conflict"}

    for code, response in inferred.items():
        responses.setdefault(code, response)


def _status_description(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return f"HTTP {status_code}"


def _summary_from_operation(operation: dict[str, Any], method: str, path: str) -> str:
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        return operation_id.replace("_", " ").strip().title()

    action = _METHOD_ACTIONS.get(method.upper(), method.upper())
    resource = path.strip("/").split("/")[-1] if path.strip("/") else "root"
    resource = resource.split(":")[0].replace("{", "").replace("}", "").replace("_", " ").replace("-", " ").strip()
    resource = resource or "resource"
    return f"{action} {resource.title()}"


def _ensure_operation_docs(path: str, method: str, operation: dict[str, Any]) -> None:
    if not isinstance(operation.get("summary"), str) or not operation.get("summary", "").strip():
        operation["summary"] = _summary_from_operation(operation, method, path)

    description = operation.get("description")
    if isinstance(description, str):
        desc = description.strip()
        if _GENERIC_DESCRIPTION_PATTERN.match(desc):
            operation.pop("description", None)
    elif description is not None:
        operation.pop("description", None)

    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return

    for code, response in responses.items():
        if not isinstance(response, dict):
            continue
        if not str(code).startswith("2"):
            continue
        current = response.get("description")
        if isinstance(current, str) and current.strip() and current.strip() != "Successful Response":
            continue
        response["description"] = _status_description(int(str(code))) if str(code).isdigit() else "Success"


def _iter_method_operations(paths: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    ops: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            ops.append((path, method.lower(), operation))
    return ops


def _sanitize_operation_id_suffix(path: str) -> str:
    cleaned = path.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace(":", "_").replace("-", "_")
    return cleaned or "root"


def _dedupe_operation_ids(paths: dict[str, Any]) -> None:
    id_to_ops: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, method, operation in _iter_method_operations(paths):
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id.strip():
            continue
        id_to_ops.setdefault(operation_id, []).append((path, method, operation))

    for operation_id, ops in id_to_ops.items():
        if len(ops) <= 1:
            continue
        for path, method, operation in ops:
            suffix = _sanitize_operation_id_suffix(path)
            operation["operationId"] = f"{operation_id}_{method}_{suffix}"


def _walk_mutate_json(node: Any, mutate: Any) -> None:
    if isinstance(node, dict):
        mutate(node)
        for value in list(node.values()):
            _walk_mutate_json(value, mutate)
    elif isinstance(node, list):
        for item in node:
            _walk_mutate_json(item, mutate)


def _ensure_jsonvalue_alias(schema: dict[str, Any]) -> None:
    components = schema.get("components")
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return
    json_output = schemas.get("JSONValue-Output")
    if "JSONValue" not in schemas and isinstance(json_output, dict):
        schemas["JSONValue"] = dict(json_output)


def _retarget_jsonvalue_refs(schema: dict[str, Any]) -> None:
    def mutate(node: dict[str, Any]) -> None:
        ref = node.get("$ref")
        if ref == "#/components/schemas/JSONValue-Output":
            node["$ref"] = "#/components/schemas/JSONValue"
        additional = node.get("additionalProperties")
        if additional is True:
            node["additionalProperties"] = {"$ref": "#/components/schemas/JSONValue"}

    _walk_mutate_json(schema, mutate)


def _harden_response_schemas(paths: dict[str, Any]) -> None:
    for _, _, operation in _iter_method_operations(paths):
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            continue
        for response in responses.values():
            if not isinstance(response, dict):
                continue
            content = response.get("content")
            if not isinstance(content, dict):
                continue
            for media in content.values():
                if not isinstance(media, dict):
                    continue
                raw_schema = media.get("schema")
                if not isinstance(raw_schema, dict):
                    continue
                if raw_schema == {}:
                    media["schema"] = dict(_UNTYPED_OBJECT_SCHEMA)
                    continue
                if _looks_untyped_schema(raw_schema):
                    raw_schema.update(dict(_UNTYPED_OBJECT_SCHEMA))


def _looks_untyped_schema(raw_schema: dict[str, Any]) -> bool:
    signal_keys = {"type", "$ref", "anyOf", "oneOf", "allOf", "items", "properties", "additionalProperties"}
    return not any(key in raw_schema for key in signal_keys)


def _remove_noisy_titles(schema: dict[str, Any]) -> None:
    def mutate(node: dict[str, Any]) -> None:
        title = node.get("title")
        if isinstance(title, str) and title.startswith("Response "):
            node.pop("title", None)

    _walk_mutate_json(schema, mutate)


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
            _dedupe_operation_ids(paths)
            for path, path_item in paths.items():
                if not isinstance(path_item, dict):
                    continue
                for method, operation in path_item.items():
                    if not isinstance(operation, dict):
                        continue
                    _ensure_alertmanager_security(path, operation)
                    _normalize_operation_security(operation)
                    _apply_inferred_responses(path, method, operation)
                    _ensure_operation_docs(path, method, operation)
            _harden_response_schemas(paths)

        _ensure_jsonvalue_alias(schema)
        _retarget_jsonvalue_refs(schema)
        _remove_noisy_titles(schema)

        schema["jsonSchemaDialect"] = JSON_SCHEMA_DIALECT
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
