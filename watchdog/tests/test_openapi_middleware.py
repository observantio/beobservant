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
