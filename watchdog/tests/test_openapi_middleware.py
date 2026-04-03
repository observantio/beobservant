from __future__ import annotations

from fastapi import FastAPI

from tests._env import ensure_test_env

ensure_test_env()

from middleware import openapi as openapi_middleware


def test_ensure_cookie_security_scheme_guards_invalid_shapes() -> None:
    schema_bad_components = {"components": []}
    openapi_middleware._ensure_cookie_security_scheme(schema_bad_components)  # type: ignore[arg-type]
    assert schema_bad_components["components"] == []

    schema_bad_security = {"components": {"securitySchemes": []}}
    openapi_middleware._ensure_cookie_security_scheme(schema_bad_security)  # type: ignore[arg-type]
    assert schema_bad_security["components"]["securitySchemes"] == []

    schema: dict[str, object] = {}
    openapi_middleware._ensure_cookie_security_scheme(schema)  # type: ignore[arg-type]
    security = schema["components"]["securitySchemes"]["WatchdogCookieAuth"]  # type: ignore[index]
    assert security["type"] == "apiKey"
    assert security["in"] == "cookie"


def test_normalize_operation_security_paths() -> None:
    operation_non_list: dict[str, object] = {"security": {}}
    openapi_middleware._normalize_operation_security(operation_non_list)  # type: ignore[arg-type]
    assert operation_non_list["security"] == {}

    cookie_only: dict[str, object] = {"security": [{"WatchdogCookieAuth": []}]}
    openapi_middleware._normalize_operation_security(cookie_only)  # type: ignore[arg-type]
    assert cookie_only["security"] == [{"HTTPBearer": []}]

    both: dict[str, object] = {"security": [{"WatchdogCookieAuth": []}, {"HTTPBearer": []}, {"Other": []}]}
    openapi_middleware._normalize_operation_security(both)  # type: ignore[arg-type]
    assert both["security"] == [{"HTTPBearer": []}]

    bearer_only: dict[str, object] = {"security": [{"HTTPBearer": []}]}
    openapi_middleware._normalize_operation_security(bearer_only)  # type: ignore[arg-type]
    assert bearer_only["security"] == [{"HTTPBearer": []}]


def test_apply_inferred_responses_rules() -> None:
    op_non_dict: dict[str, object] = {"responses": []}
    openapi_middleware._apply_inferred_responses("/api/test", "GET", op_non_dict)  # type: ignore[arg-type]
    assert op_non_dict["responses"] == []

    op: dict[str, object] = {
        "security": [{"HTTPBearer": []}],
        "requestBody": {"content": {}},
    }
    openapi_middleware._apply_inferred_responses("/api/auth/login/{id}", "POST", op)  # type: ignore[arg-type]
    responses = op["responses"]
    assert isinstance(responses, dict)
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["403"]["description"] == "Forbidden"
    assert responses["400"]["description"] == "Bad Request"
    assert responses["404"]["description"] == "Not Found"
    assert responses["429"]["description"] == "Too Many Requests"

    oidc_exchange: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/auth/oidc/exchange", "GET", oidc_exchange)  # type: ignore[arg-type]
    assert oidc_exchange["responses"]["401"]["description"] == "Unauthorized"

    alertmanager: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/alertmanager/foo", "GET", alertmanager)  # type: ignore[arg-type]
    assert alertmanager["responses"]["401"]["description"] == "Unauthorized"
    assert alertmanager["responses"]["403"]["description"] == "Forbidden"

    alertmanager_public: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/alertmanager/public/rules", "GET", alertmanager_public)  # type: ignore[arg-type]
    assert "401" not in alertmanager_public["responses"]
    assert "403" not in alertmanager_public["responses"]

    grafana_auth: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/grafana/auth", "GET", grafana_auth)  # type: ignore[arg-type]
    assert grafana_auth["responses"]["400"]["description"] == "Bad Request"
    assert grafana_auth["responses"]["403"]["description"] == "Forbidden"
    assert grafana_auth["responses"]["429"]["description"] == "Too Many Requests"

    dashboards_search: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/grafana/dashboards/search", "GET", dashboards_search)  # type: ignore[arg-type]
    assert dashboards_search["responses"]["400"]["description"] == "Bad Request"

    datasources_create: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/grafana/datasources", "POST", datasources_create)  # type: ignore[arg-type]
    assert datasources_create["responses"]["409"]["description"] == "Conflict"

    folders_create: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/grafana/folders", "POST", folders_create)  # type: ignore[arg-type]
    assert folders_create["responses"]["409"]["description"] == "Conflict"

    resolver_proxy: dict[str, object] = {}
    openapi_middleware._apply_inferred_responses("/api/resolver/anomalies/traces", "POST", resolver_proxy)  # type: ignore[arg-type]
    assert resolver_proxy["responses"]["502"]["description"] == "Bad Gateway"


def test_install_custom_openapi_cache_and_non_dict_schema(monkeypatch) -> None:
    app = FastAPI()
    app.openapi_schema = {"cached": True}
    openapi_middleware.install_custom_openapi(app)
    assert app.openapi() == {"cached": True}

    app2 = FastAPI()
    openapi_middleware.install_custom_openapi(app2)
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: [])  # type: ignore[return-value]
    assert app2.openapi() == []

    app4 = FastAPI()
    openapi_middleware.install_custom_openapi(app4)
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: {"paths": []})
    assert app4.openapi()["paths"] == []

    app3 = FastAPI()
    openapi_middleware.install_custom_openapi(app3)
    fake_schema = {
        "paths": {
            "/api/auth/login/{id}": {"post": {"security": [{"WatchdogCookieAuth": []}], "requestBody": {"content": {}}}},
            "/api/skip": "skip",
            "/api/trace": {"trace": "skip"},
        }
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: fake_schema)
    generated = app3.openapi()
    responses = generated["paths"]["/api/auth/login/{id}"]["post"]["responses"]
    assert responses["401"]["description"] == "Unauthorized"
    assert responses["403"]["description"] == "Forbidden"
    assert responses["400"]["description"] == "Bad Request"
    assert responses["404"]["description"] == "Not Found"
    assert responses["429"]["description"] == "Too Many Requests"
    assert generated["paths"]["/api/auth/login/{id}"]["post"]["security"] == [{"HTTPBearer": []}]


def test_install_custom_openapi_dedupes_operation_ids_and_hardens_response_schemas(monkeypatch) -> None:
    app = FastAPI()
    openapi_middleware.install_custom_openapi(app)
    fake_schema = {
        "paths": {
            "/api/alertmanager/public/rules": {
                "get": {
                    "operationId": "alertmanager_proxy_api_alertmanager__path__post",
                    "description": "Handles GET requests for `/api/alertmanager/public/rules`.",
                    "responses": {"200": {"content": {"application/json": {"schema": {"title": "Response Foo"}}}}},
                }
            },
            "/api/alertmanager/{path}": {
                "post": {
                    "operationId": "alertmanager_proxy_api_alertmanager__path__post",
                    "responses": {"200": {"content": {"application/json": {"schema": {}}}}},
                }
            },
        },
        "components": {"schemas": {"JSONValue-Output": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        },
    }
    monkeypatch.setattr(openapi_middleware, "get_openapi", lambda **kwargs: fake_schema)
    generated = app.openapi()

    public_get = generated["paths"]["/api/alertmanager/public/rules"]["get"]
    proxy_post = generated["paths"]["/api/alertmanager/{path}"]["post"]
    assert public_get["operationId"] != proxy_post["operationId"]
    assert "security" not in public_get
    assert "description" not in public_get
    assert "title" not in public_get["responses"]["200"]["content"]["application/json"]["schema"]
    assert proxy_post["responses"]["200"]["content"]["application/json"]["schema"]["type"] == "object"
    assert generated["components"]["schemas"]["JSONValue"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_openapi_doc_helper_branches_cover_fallbacks() -> None:
    assert openapi_middleware._status_description(999) == "HTTP 999"

    operation: dict[str, object] = {
        "operationId": "list_alerts",
        "responses": {
            "200": {},
            "201": {"description": "Created"},
            "2xx": {},
        },
    }
    openapi_middleware._ensure_operation_docs("/api/alertmanager/{path:path}", "GET", operation)  # type: ignore[arg-type]
    assert operation["summary"] == "List Alerts"
    assert "description" not in operation
    responses = operation["responses"]
    assert isinstance(responses, dict)
    assert responses["200"]["description"] == "OK"
    assert responses["201"]["description"] == "Created"
    assert responses["2xx"]["description"] == "Success"

    no_operation_id: dict[str, object] = {"responses": {"200": {"description": "Successful Response"}}}
    openapi_middleware._ensure_operation_docs("/", "TRACE", no_operation_id)  # type: ignore[arg-type]
    assert no_operation_id["summary"] == "TRACE Root"

    non_dict_responses: dict[str, object] = {"responses": []}
    openapi_middleware._ensure_operation_docs("/x", "GET", non_dict_responses)  # type: ignore[arg-type]
    assert non_dict_responses["summary"] == "Retrieve X"

    prefilled: dict[str, object] = {
        "summary": "Keep Summary",
        "description": "Keep description.",
        "responses": {
            "200": "skip",
            "201": {"description": "Successful Response"},
        },
    }
    openapi_middleware._ensure_operation_docs("/api/alertmanager", "GET", prefilled)  # type: ignore[arg-type]
    assert prefilled["summary"] == "Keep Summary"
    assert prefilled["description"] == "Keep description."
    prefilled_responses = prefilled["responses"]
    assert isinstance(prefilled_responses, dict)
    assert prefilled_responses["200"] == "skip"
    assert prefilled_responses["201"]["description"] == "Created"


def test_openapi_helper_guards_cover_remaining_branches() -> None:
    operation_with_security: dict[str, object] = {"security": [{"HTTPBearer": []}]}
    openapi_middleware._ensure_alertmanager_security("/api/alertmanager/rules", operation_with_security)  # type: ignore[arg-type]
    assert operation_with_security["security"] == [{"HTTPBearer": []}]

    non_string_description: dict[str, object] = {
        "description": {"unexpected": True},
        "responses": {"200": {}},
    }
    openapi_middleware._ensure_operation_docs("/api/test", "GET", non_string_description)  # type: ignore[arg-type]
    assert "description" not in non_string_description

    assert openapi_middleware._iter_method_operations({
        "/api/test": {
            "summary": "skip",
            "x-custom": {},
            "get": "not-a-dict",
        }
    }) == []

    unique_paths: dict[str, object] = {
        "/api/test": {
            "get": {"operationId": "unique_operation"},
        }
    }
    openapi_middleware._dedupe_operation_ids(unique_paths)  # type: ignore[arg-type]
    assert unique_paths["/api/test"]["get"]["operationId"] == "unique_operation"

    openapi_middleware._ensure_jsonvalue_alias({"components": []})  # type: ignore[arg-type]

    schema_refs: dict[str, object] = {
        "$ref": "#/components/schemas/JSONValue-Output",
        "additionalProperties": True,
        "components": {"schemas": {"JSONValue-Output": {"type": "string"}}},
    }
    openapi_middleware._retarget_jsonvalue_refs(schema_refs)  # type: ignore[arg-type]
    assert schema_refs["$ref"] == "#/components/schemas/JSONValue"
    assert schema_refs["additionalProperties"] == {"$ref": "#/components/schemas/JSONValue"}

    schema_with_existing_alias = {
        "components": {
            "schemas": {
                "JSONValue": {"type": "integer"},
                "JSONValue-Output": {"type": "string"},
            }
        }
    }
    openapi_middleware._ensure_jsonvalue_alias(schema_with_existing_alias)  # type: ignore[arg-type]
    assert schema_with_existing_alias["components"]["schemas"]["JSONValue"] == {"type": "integer"}

    paths_with_guards: dict[str, object] = {
        "/api/a": {"get": {"responses": []}},
        "/api/b": {"get": {"responses": {"200": "skip"}}},
        "/api/c": {"get": {"responses": {"200": {"content": {"application/json": "skip"}}}}},
        "/api/d": {"get": {"responses": {"200": {"content": {"application/json": {"schema": "skip"}}}}}},
        "/api/e": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
            }
        },
    }
    openapi_middleware._harden_response_schemas(paths_with_guards)  # type: ignore[arg-type]
    assert paths_with_guards["/api/a"]["get"]["responses"] == []
    assert paths_with_guards["/api/b"]["get"]["responses"]["200"] == "skip"
    assert paths_with_guards["/api/e"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {"type": "object"}
