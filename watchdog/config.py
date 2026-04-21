"""
Configuration management for Watchdog server application.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import importlib
import logging
import os
import secrets
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from services.secrets.provider import EnvSecretProvider, SecretProvider

logger = logging.getLogger(__name__)


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _to_list(value: str | None, default: list[str] | None = None) -> list[str]:
    if value is None:
        return default or []
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed if parsed else (default or [])


def _is_placeholder(value: str | None, placeholders: list[str]) -> bool:
    if value is None:
        return True
    normalized = value.strip()
    return not normalized or normalized in placeholders


def _normalized_secret(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_weak_secret(value: str | None) -> bool:
    normalized = _normalized_secret(value)
    if not normalized:
        return True
    weak_markers = ("changeme", "replace_with", "example", "default", "secret", "password")
    return any(marker in normalized for marker in weak_markers)


def _generate_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _generate_ec_keypair() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _env_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def _is_production_env() -> bool:
    return _env_name() in {"prod", "production"}


def _slug_token(value: str | None, default: str) -> str:
    raw = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() else "-" for ch in raw]
    collapsed = "".join(chars).strip("-")
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed or default


def _populate_runtime_basics(cfg: "Config") -> None:
    cfg.APP_ENV = _env_name()
    cfg.IS_PRODUCTION = _is_production_env()

    cfg.HOST = os.getenv("HOST", "127.0.0.1")
    cfg.PORT = int(os.getenv("PORT", "4319"))
    cfg.LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
    cfg.ENABLE_API_DOCS = _to_bool(os.getenv("ENABLE_API_DOCS"), default=not cfg.IS_PRODUCTION)
    cfg.SKIP_STARTUP_DB_INIT = _to_bool(os.getenv("SKIP_STARTUP_DB_INIT"), default=False)
    cfg.DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")
    cfg.DATABASE_URL = os.getenv("DATABASE_URL", cfg.EXAMPLE_DATABASE_URL)


def _populate_service_endpoints(cfg: "Config") -> None:
    cfg.TEMPO_URL = os.getenv("TEMPO_URL", "http://tempo:3200")
    cfg.LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
    cfg.ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")
    cfg.NOTIFIER_URL = os.getenv("NOTIFIER_URL", "http://notifier:4323")
    cfg.RESOLVER_URL = os.getenv("RESOLVER_URL", "http://resolver:4322")
    cfg.GRAFANA_URL = os.getenv("GRAFANA_URL", "http://grafana:3000")
    cfg.MIMIR_URL = os.getenv("MIMIR_URL", "http://mimir:9009")
    cfg.GRAFANA_USERNAME = os.getenv("GRAFANA_USERNAME", "admin")
    cfg.GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")
    cfg.GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")


def _populate_http_client_settings(cfg: "Config") -> None:
    cfg.DEFAULT_TIMEOUT = float(os.getenv("DEFAULT_TIMEOUT", "30.0"))
    cfg.NOTIFIER_TIMEOUT_SECONDS = float(os.getenv("NOTIFIER_TIMEOUT_SECONDS", "15.0"))
    cfg.RESOLVER_TIMEOUT_SECONDS = float(os.getenv("RESOLVER_TIMEOUT_SECONDS", "20.0"))
    cfg.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    cfg.RETRY_BACKOFF = float(os.getenv("RETRY_BACKOFF", "1.0"))
    cfg.RETRY_MAX_BACKOFF = float(os.getenv("RETRY_MAX_BACKOFF", "8.0"))
    cfg.RETRY_JITTER = float(os.getenv("RETRY_JITTER", "0.1"))
    cfg.HTTP_CLIENT_MAX_CONNECTIONS = int(os.getenv("HTTP_CLIENT_MAX_CONNECTIONS", "100"))
    cfg.HTTP_CLIENT_MAX_KEEPALIVE_CONNECTIONS = int(os.getenv("HTTP_CLIENT_MAX_KEEPALIVE_CONNECTIONS", "40"))
    cfg.HTTP_CLIENT_KEEPALIVE_EXPIRY = float(os.getenv("HTTP_CLIENT_KEEPALIVE_EXPIRY", "30"))


def _populate_observability_query_settings(cfg: "Config") -> None:
    cfg.LOKI_FALLBACK_CONCURRENCY = int(os.getenv("LOKI_FALLBACK_CONCURRENCY", "4"))
    cfg.LOKI_MAX_FALLBACK_QUERIES = int(os.getenv("LOKI_MAX_FALLBACK_QUERIES", "4"))
    cfg.LOKI_VOLUME_CACHE_TTL_SECONDS = int(os.getenv("LOKI_VOLUME_CACHE_TTL_SECONDS", "30"))
    cfg.TEMPO_TRACE_FETCH_CONCURRENCY = int(os.getenv("TEMPO_TRACE_FETCH_CONCURRENCY", "8"))
    cfg.TEMPO_VOLUME_BUCKET_CONCURRENCY = int(os.getenv("TEMPO_VOLUME_BUCKET_CONCURRENCY", "8"))
    cfg.TEMPO_COUNT_QUERY_CONCURRENCY = int(os.getenv("TEMPO_COUNT_QUERY_CONCURRENCY", "4"))
    cfg.TEMPO_USE_METRICS_FOR_COUNT = _to_bool(os.getenv("TEMPO_USE_METRICS_FOR_COUNT"), default=True)
    cfg.SERVICE_CACHE_TTL_SECONDS = int(os.getenv("SERVICE_CACHE_TTL_SECONDS", "30"))
    cfg.CORS_ORIGINS = _to_list(os.getenv("CORS_ORIGINS"), default=["*"])
    cfg.CORS_ALLOW_CREDENTIALS = _to_bool(os.getenv("CORS_ALLOW_CREDENTIALS"), default=True)
    cfg.MAX_QUERY_LIMIT = int(os.getenv("MAX_QUERY_LIMIT", "1000"))
    cfg.DEFAULT_QUERY_LIMIT = int(os.getenv("DEFAULT_QUERY_LIMIT", "20"))
    cfg.MAX_API_KEYS_PER_USER = int(os.getenv("MAX_API_KEYS_PER_USER", "10"))


def _populate_quota_settings(cfg: "Config") -> None:
    cfg.QUOTA_NATIVE_ENABLED = _to_bool(os.getenv("QUOTA_NATIVE_ENABLED") or None, default=True)
    cfg.QUOTA_NATIVE_TIMEOUT_SECONDS = float(os.getenv("QUOTA_NATIVE_TIMEOUT_SECONDS", "5.0"))
    cfg.LOKI_QUOTA_NATIVE_PATH = (os.getenv("LOKI_QUOTA_NATIVE_PATH") or "/loki/api/v1/status/limits").strip()
    cfg.TEMPO_QUOTA_NATIVE_PATH = (os.getenv("TEMPO_QUOTA_NATIVE_PATH") or "/status/overrides").strip()
    cfg.LOKI_QUOTA_NATIVE_LIMIT_FIELD = (os.getenv("LOKI_QUOTA_NATIVE_LIMIT_FIELD") or "max_streams_per_user").strip()
    cfg.LOKI_QUOTA_NATIVE_USED_FIELD = (os.getenv("LOKI_QUOTA_NATIVE_USED_FIELD") or "").strip()
    cfg.TEMPO_QUOTA_NATIVE_LIMIT_FIELD = (os.getenv("TEMPO_QUOTA_NATIVE_LIMIT_FIELD") or "max_traces_per_user").strip()
    cfg.TEMPO_QUOTA_NATIVE_USED_FIELD = (os.getenv("TEMPO_QUOTA_NATIVE_USED_FIELD") or "").strip()
    cfg.QUOTA_USAGE_WINDOW_SECONDS = int(os.getenv("QUOTA_USAGE_WINDOW_SECONDS", "3600"))
    cfg.QUOTA_PROMETHEUS_ENABLED = _to_bool(os.getenv("QUOTA_PROMETHEUS_ENABLED") or None, default=True)
    cfg.QUOTA_PROMETHEUS_TIMEOUT_SECONDS = float(os.getenv("QUOTA_PROMETHEUS_TIMEOUT_SECONDS", "5.0"))
    cfg.QUOTA_PROMETHEUS_BASE_URL = (os.getenv("QUOTA_PROMETHEUS_BASE_URL") or cfg.MIMIR_URL).strip()
    cfg.LOKI_QUOTA_PROM_LIMIT_QUERY = (os.getenv("LOKI_QUOTA_PROM_LIMIT_QUERY") or "").strip()
    cfg.LOKI_QUOTA_PROM_USED_QUERY = (os.getenv("LOKI_QUOTA_PROM_USED_QUERY") or "").strip()
    cfg.TEMPO_QUOTA_PROM_LIMIT_QUERY = (os.getenv("TEMPO_QUOTA_PROM_LIMIT_QUERY") or "").strip()
    cfg.TEMPO_QUOTA_PROM_USED_QUERY = (os.getenv("TEMPO_QUOTA_PROM_USED_QUERY") or "").strip()


def _populate_gateway_limits(cfg: "Config") -> None:
    cfg.MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", "1048576"))
    cfg.MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "200"))
    cfg.CONCURRENCY_ACQUIRE_TIMEOUT = float(os.getenv("CONCURRENCY_ACQUIRE_TIMEOUT", "1.0"))
    cfg.RATE_LIMIT_USER_PER_MINUTE = int(os.getenv("RATE_LIMIT_USER_PER_MINUTE", "600"))
    cfg.RATE_LIMIT_PUBLIC_PER_MINUTE = int(os.getenv("RATE_LIMIT_PUBLIC_PER_MINUTE", "120"))
    cfg.RATE_LIMIT_LOGIN_PER_MINUTE = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
    cfg.RATE_LIMIT_REGISTER_PER_HOUR = int(os.getenv("RATE_LIMIT_REGISTER_PER_HOUR", "5"))
    cfg.RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE = int(os.getenv("RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE", "3000"))
    cfg.GRAFANA_PROXY_CACHE_TTL = int(os.getenv("GRAFANA_PROXY_CACHE_TTL", "30"))
    cfg.RATE_LIMIT_REDIS_URL = os.getenv("RATE_LIMIT_REDIS_URL", "").strip()
    cfg.TTL_CACHE_REDIS_URL = os.getenv("TTL_CACHE_REDIS_URL", "").strip()
    cfg.TTL_CACHE_KEY_PREFIX = os.getenv("TTL_CACHE_KEY_PREFIX", "watchdog:ttl").strip()


def _populate_config_services_and_http(cfg: "Config") -> None:
    _populate_runtime_basics(cfg)
    _populate_service_endpoints(cfg)
    _populate_http_client_settings(cfg)
    _populate_observability_query_settings(cfg)
    _populate_quota_settings(cfg)
    _populate_gateway_limits(cfg)


def _populate_config_network_auth_and_limits(cfg: "Config") -> None:
    cfg.TRUST_PROXY_HEADERS = _to_bool(os.getenv("TRUST_PROXY_HEADERS"), default=False)
    cfg.AUTH_PUBLIC_IP_ALLOWLIST = os.getenv("AUTH_PUBLIC_IP_ALLOWLIST")
    cfg.GATEWAY_IP_ALLOWLIST = os.getenv("GATEWAY_IP_ALLOWLIST")
    cfg.WEBHOOK_IP_ALLOWLIST = os.getenv("WEBHOOK_IP_ALLOWLIST")
    cfg.AGENT_INGEST_IP_ALLOWLIST = os.getenv("AGENT_INGEST_IP_ALLOWLIST")
    cfg.GRAFANA_PROXY_IP_ALLOWLIST = os.getenv("GRAFANA_PROXY_IP_ALLOWLIST")
    cfg.AGENT_HEARTBEAT_TOKEN = os.getenv("AGENT_HEARTBEAT_TOKEN")

    cfg.INBOUND_WEBHOOK_TOKEN = os.getenv("INBOUND_WEBHOOK_TOKEN")
    cfg.OTLP_INGEST_TOKEN = os.getenv("OTLP_INGEST_TOKEN")

    cfg.GATEWAY_INTERNAL_SERVICE_TOKEN = os.getenv("GATEWAY_INTERNAL_SERVICE_TOKEN")
    cfg.NOTIFIER_SERVICE_TOKEN = os.getenv("NOTIFIER_SERVICE_TOKEN")
    cfg.NOTIFIER_CONTEXT_SIGNING_KEY = os.getenv("NOTIFIER_CONTEXT_SIGNING_KEY")
    cfg.NOTIFIER_CONTEXT_ISSUER = os.getenv("NOTIFIER_CONTEXT_ISSUER", "watchdog-main")
    cfg.NOTIFIER_CONTEXT_AUDIENCE = os.getenv("NOTIFIER_CONTEXT_AUDIENCE", "notifier")
    cfg.NOTIFIER_CONTEXT_ALGORITHM = os.getenv("NOTIFIER_CONTEXT_ALGORITHM", "HS256").strip().upper()
    cfg.NOTIFIER_CONTEXT_TTL_SECONDS = int(os.getenv("NOTIFIER_CONTEXT_TTL_SECONDS", "90"))
    cfg.NOTIFIER_TLS_ENABLED = _to_bool(os.getenv("NOTIFIER_TLS_ENABLED"), default=False)
    cfg.NOTIFIER_CA_CERT_PATH = os.getenv("NOTIFIER_CA_CERT_PATH")

    cfg.RESOLVER_SERVICE_TOKEN = os.getenv("RESOLVER_SERVICE_TOKEN")
    cfg.RESOLVER_CONTEXT_SIGNING_KEY = os.getenv("RESOLVER_CONTEXT_SIGNING_KEY")
    cfg.RESOLVER_CONTEXT_ISSUER = os.getenv("RESOLVER_CONTEXT_ISSUER", "watchdog-main")
    cfg.RESOLVER_CONTEXT_AUDIENCE = os.getenv("RESOLVER_CONTEXT_AUDIENCE", "resolver")
    cfg.RESOLVER_CONTEXT_ALGORITHM = os.getenv("RESOLVER_CONTEXT_ALGORITHM", "HS256").strip().upper()
    cfg.RESOLVER_CONTEXT_TTL_SECONDS = int(os.getenv("RESOLVER_CONTEXT_TTL_SECONDS", "120"))
    cfg.RESOLVER_PROXY_CACHE_TTL_SECONDS = int(os.getenv("RESOLVER_PROXY_CACHE_TTL_SECONDS", "15"))
    cfg.RESOLVER_TLS_ENABLED = _to_bool(os.getenv("RESOLVER_TLS_ENABLED"), default=False)
    cfg.RESOLVER_CA_CERT_PATH = os.getenv("RESOLVER_CA_CERT_PATH")

    cfg.RESOLVER_ANALYZE_MAX_CONCURRENCY = int(os.getenv("RESOLVER_ANALYZE_MAX_CONCURRENCY", "4"))
    cfg.RESOLVER_ANALYZE_MAX_RETAINED_PER_USER = int(os.getenv("RESOLVER_ANALYZE_MAX_RETAINED_PER_USER", "50"))
    cfg.RESOLVER_ANALYZE_JOB_TTL_SECONDS = int(os.getenv("RESOLVER_ANALYZE_JOB_TTL_SECONDS", "900"))


def _populate_config_jwt_oidc_and_admin_defaults(cfg: "Config") -> None:
    cfg.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256").strip().upper()
    cfg.JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))
    cfg.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    cfg.JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY")
    cfg.JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")
    cfg.JWT_AUTO_GENERATE_KEYS = _to_bool(os.getenv("JWT_AUTO_GENERATE_KEYS"), default=not cfg.IS_PRODUCTION)

    cfg.AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "local").strip().lower()
    cfg.AUTH_PASSWORD_FLOW_ENABLED = _to_bool(os.getenv("AUTH_PASSWORD_FLOW_ENABLED"), default=False)
    cfg.OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL")
    cfg.OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID")
    cfg.OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET")
    cfg.OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
    cfg.OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL")
    cfg.OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid profile email")
    cfg.OIDC_CLOCK_SKEW_LEEWAY_SECONDS = max(
        0,
        int(os.getenv("OIDC_CLOCK_SKEW_LEEWAY_SECONDS", "60")),
    )
    cfg.OIDC_AUTO_PROVISION_USERS = _to_bool(os.getenv("OIDC_AUTO_PROVISION_USERS"), default=True)
    cfg.OIDC_AUTO_LINK_BY_EMAIL = _to_bool(os.getenv("OIDC_AUTO_LINK_BY_EMAIL"), default=True)
    cfg.OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK = _to_bool(os.getenv("OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK"), default=True)
    cfg.OIDC_REQUIRE_MFA_FOR_MEMBERS = _to_bool(os.getenv("OIDC_REQUIRE_MFA_FOR_MEMBERS"), default=False)

    cfg.SKIP_LOCAL_MFA_FOR_EXTERNAL = _to_bool(os.getenv("SKIP_LOCAL_MFA_FOR_EXTERNAL"), default=True)

    cfg.KEYCLOAK_ADMIN_URL = os.getenv("KEYCLOAK_ADMIN_URL")
    cfg.KEYCLOAK_ADMIN_REALM = os.getenv("KEYCLOAK_ADMIN_REALM")
    cfg.KEYCLOAK_ADMIN_CLIENT_ID = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID")
    cfg.KEYCLOAK_ADMIN_CLIENT_SECRET = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")
    cfg.KEYCLOAK_USER_PROVISIONING_ENABLED = _to_bool(
        os.getenv("KEYCLOAK_USER_PROVISIONING_ENABLED"),
        default=False,
    )

    cfg.DEFAULT_ADMIN_BOOTSTRAP_ENABLED = _to_bool(
        os.getenv("DEFAULT_ADMIN_BOOTSTRAP_ENABLED"),
        default=not cfg.IS_PRODUCTION,
    )
    cfg.REQUIRE_TOTP_ENCRYPTION_KEY = _to_bool(
        os.getenv("REQUIRE_TOTP_ENCRYPTION_KEY"),
        default=cfg.IS_PRODUCTION,
    )
    cfg.TRUSTED_PROXY_CIDRS = _to_list(os.getenv("TRUSTED_PROXY_CIDRS"), default=[])
    cfg.REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS = _to_bool(
        os.getenv("REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS"),
        default=cfg.IS_PRODUCTION,
    )

    cfg.FORCE_SECURE_COOKIES = _to_bool(os.getenv("FORCE_SECURE_COOKIES"), default=cfg.IS_PRODUCTION)
    cfg.ALLOWLIST_FAIL_OPEN = _to_bool(os.getenv("ALLOWLIST_FAIL_OPEN"), default=False)

    cfg.RATE_LIMIT_GC_EVERY = int(os.getenv("RATE_LIMIT_GC_EVERY", "1024"))
    cfg.RATE_LIMIT_STALE_AFTER_SECONDS = int(os.getenv("RATE_LIMIT_STALE_AFTER_SECONDS", "3600"))
    cfg.RATE_LIMIT_MAX_STATES = int(os.getenv("RATE_LIMIT_MAX_STATES", "200000"))
    cfg.RATE_LIMIT_FALLBACK_MODE = os.getenv("RATE_LIMIT_FALLBACK_MODE", "memory").strip().lower()
    cfg.PASSWORD_HASH_MAX_CONCURRENCY = int(os.getenv("PASSWORD_HASH_MAX_CONCURRENCY", "8"))
    cfg.PASSWORD_RESET_INTERVAL_DAYS = int(os.getenv("PASSWORD_RESET_INTERVAL_DAYS", "0"))
    cfg.TEMP_PASSWORD_LENGTH = int(os.getenv("TEMP_PASSWORD_LENGTH", "20"))

    cfg.DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    cfg.DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "")
    cfg.DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    cfg.DEFAULT_ADMIN_TENANT = os.getenv("DEFAULT_ADMIN_TENANT", "default")

    cfg.DEFAULT_ORG_ID = os.getenv("DEFAULT_ORG_ID", "default")
    app_org_key_default = (
        f"{_slug_token(os.getenv('APP_NAME', 'observantio'), 'observantio')}"
        f"-{_slug_token(cfg.DEFAULT_ORG_ID, 'default')}"
    )
    cfg.APP_ORG_KEY = os.getenv("APP_ORG_KEY", app_org_key_default).strip()
    cfg.OTLP_GATEWAY_URL = os.getenv("OTLP_GATEWAY_URL", "http://otlp-gateway:4320")
    cfg.DEFAULT_OTLP_TOKEN = os.getenv("DEFAULT_OTLP_TOKEN")


def _populate_config_vault_and_notification_defaults(cfg: "Config") -> None:
    cfg.VAULT_ENABLED = _to_bool(os.getenv("VAULT_ENABLED"), default=False)
    cfg.VAULT_ADDR = os.getenv("VAULT_ADDR")
    cfg.VAULT_TOKEN = os.getenv("VAULT_TOKEN")
    cfg.VAULT_ROLE_ID = os.getenv("VAULT_ROLE_ID")
    cfg.VAULT_SECRET_ID = os.getenv("VAULT_SECRET_ID")
    cfg.VAULT_CACERT = os.getenv("VAULT_CACERT")
    cfg.VAULT_SECRETS_PREFIX = os.getenv("VAULT_SECRETS_PREFIX", "secret")
    cfg.VAULT_KV_VERSION = int(os.getenv("VAULT_KV_VERSION", "2"))
    cfg.VAULT_TIMEOUT = float(os.getenv("VAULT_TIMEOUT", "2.0"))
    cfg.VAULT_FAIL_ON_MISSING = _to_bool(os.getenv("VAULT_FAIL_ON_MISSING"), default=cfg.IS_PRODUCTION)

    try:
        cfg.load_vault_secrets()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if cfg.VAULT_ENABLED and (cfg.IS_PRODUCTION or cfg.VAULT_FAIL_ON_MISSING):
            raise
        logger.warning("Vault not available or misconfigured; continuing with environment variables: %s", exc)

    if not hasattr(cfg, "secret_provider") or cfg.secret_provider is None:
        cfg.secret_provider = EnvSecretProvider()

    cfg.DEFAULT_RULE_GROUP = os.getenv("DEFAULT_RULE_GROUP", "default")
    cfg.DEFAULT_SLACK_CHANNEL = os.getenv("DEFAULT_SLACK_CHANNEL", "default")
    cfg.ENABLED_NOTIFICATION_CHANNEL_TYPES = [
        channel_type.strip().lower()
        for channel_type in os.getenv(
            "ENABLED_NOTIFICATION_CHANNEL_TYPES",
            "email,slack,teams,webhook,pagerduty",
        ).split(",")
        if channel_type.strip()
    ]

    cfg.apply_security_defaults()
    cfg.validate()


def _populate_config(cfg: "Config") -> None:
    _populate_config_services_and_http(cfg)
    _populate_config_network_auth_and_limits(cfg)
    _populate_config_jwt_oidc_and_admin_defaults(cfg)
    _populate_config_vault_and_notification_defaults(cfg)


class Config:
    ALLOWED_JWT_ALGORITHMS = {"RS256", "ES256"}
    ALLOWED_CONTEXT_ALGORITHMS = {"HS256", "HS384", "HS512"}
    EXAMPLE_DATABASE_URL = "postgresql://watchdog:changeme123@localhost:5432/watchdog"

    secret_provider: Any | None
    APP_ENV: str
    IS_PRODUCTION: bool
    HOST: str
    PORT: int
    LOG_LEVEL: str
    ENABLE_API_DOCS: bool
    SKIP_STARTUP_DB_INIT: bool
    TEMPO_URL: str
    LOKI_URL: str
    ALERTMANAGER_URL: str
    NOTIFIER_URL: str
    RESOLVER_URL: str
    GRAFANA_URL: str
    MIMIR_URL: str
    GRAFANA_USERNAME: str
    GRAFANA_PASSWORD: str
    GRAFANA_API_KEY: str | None
    DATA_ENCRYPTION_KEY: str | None
    DATABASE_URL: str
    DEFAULT_TIMEOUT: float
    NOTIFIER_TIMEOUT_SECONDS: float
    RESOLVER_TIMEOUT_SECONDS: float
    MAX_RETRIES: int
    RETRY_BACKOFF: float
    RETRY_MAX_BACKOFF: float
    RETRY_JITTER: float
    HTTP_CLIENT_MAX_CONNECTIONS: int
    HTTP_CLIENT_MAX_KEEPALIVE_CONNECTIONS: int
    HTTP_CLIENT_KEEPALIVE_EXPIRY: float
    LOKI_FALLBACK_CONCURRENCY: int
    LOKI_MAX_FALLBACK_QUERIES: int
    LOKI_VOLUME_CACHE_TTL_SECONDS: int
    TEMPO_TRACE_FETCH_CONCURRENCY: int
    TEMPO_VOLUME_BUCKET_CONCURRENCY: int
    TEMPO_COUNT_QUERY_CONCURRENCY: int
    TEMPO_USE_METRICS_FOR_COUNT: bool
    SERVICE_CACHE_TTL_SECONDS: int
    CORS_ORIGINS: list[str]
    CORS_ALLOW_CREDENTIALS: bool
    MAX_QUERY_LIMIT: int
    DEFAULT_QUERY_LIMIT: int
    MAX_API_KEYS_PER_USER: int
    QUOTA_NATIVE_ENABLED: bool
    QUOTA_NATIVE_TIMEOUT_SECONDS: float
    LOKI_QUOTA_NATIVE_PATH: str
    TEMPO_QUOTA_NATIVE_PATH: str
    LOKI_QUOTA_NATIVE_LIMIT_FIELD: str
    LOKI_QUOTA_NATIVE_USED_FIELD: str
    TEMPO_QUOTA_NATIVE_LIMIT_FIELD: str
    TEMPO_QUOTA_NATIVE_USED_FIELD: str
    QUOTA_USAGE_WINDOW_SECONDS: int
    QUOTA_PROMETHEUS_ENABLED: bool
    QUOTA_PROMETHEUS_TIMEOUT_SECONDS: float
    QUOTA_PROMETHEUS_BASE_URL: str
    LOKI_QUOTA_PROM_LIMIT_QUERY: str
    LOKI_QUOTA_PROM_USED_QUERY: str
    TEMPO_QUOTA_PROM_LIMIT_QUERY: str
    TEMPO_QUOTA_PROM_USED_QUERY: str
    MAX_REQUEST_BYTES: int
    MAX_CONCURRENT_REQUESTS: int
    CONCURRENCY_ACQUIRE_TIMEOUT: float
    RATE_LIMIT_USER_PER_MINUTE: int
    RATE_LIMIT_PUBLIC_PER_MINUTE: int
    RATE_LIMIT_LOGIN_PER_MINUTE: int
    RATE_LIMIT_REGISTER_PER_HOUR: int
    RATE_LIMIT_GRAFANA_PROXY_PER_MINUTE: int
    GRAFANA_PROXY_CACHE_TTL: int
    RATE_LIMIT_REDIS_URL: str
    TTL_CACHE_REDIS_URL: str
    TTL_CACHE_KEY_PREFIX: str
    TRUST_PROXY_HEADERS: bool
    AUTH_PUBLIC_IP_ALLOWLIST: str | None
    GATEWAY_IP_ALLOWLIST: str | None
    WEBHOOK_IP_ALLOWLIST: str | None
    AGENT_INGEST_IP_ALLOWLIST: str | None
    GRAFANA_PROXY_IP_ALLOWLIST: str | None
    AGENT_HEARTBEAT_TOKEN: str | None
    INBOUND_WEBHOOK_TOKEN: str | None
    OTLP_INGEST_TOKEN: str | None
    GATEWAY_INTERNAL_SERVICE_TOKEN: str | None
    NOTIFIER_SERVICE_TOKEN: str | None
    NOTIFIER_CONTEXT_SIGNING_KEY: str | None
    NOTIFIER_CONTEXT_ISSUER: str
    NOTIFIER_CONTEXT_AUDIENCE: str
    NOTIFIER_CONTEXT_ALGORITHM: str
    NOTIFIER_CONTEXT_TTL_SECONDS: int
    NOTIFIER_TLS_ENABLED: bool
    NOTIFIER_CA_CERT_PATH: str | None
    RESOLVER_SERVICE_TOKEN: str | None
    RESOLVER_CONTEXT_SIGNING_KEY: str | None
    RESOLVER_CONTEXT_ISSUER: str
    RESOLVER_CONTEXT_AUDIENCE: str
    RESOLVER_CONTEXT_ALGORITHM: str
    RESOLVER_CONTEXT_TTL_SECONDS: int
    RESOLVER_PROXY_CACHE_TTL_SECONDS: int
    RESOLVER_TLS_ENABLED: bool
    RESOLVER_CA_CERT_PATH: str | None
    RESOLVER_ANALYZE_MAX_CONCURRENCY: int
    RESOLVER_ANALYZE_MAX_RETAINED_PER_USER: int
    RESOLVER_ANALYZE_JOB_TTL_SECONDS: int
    JWT_ALGORITHM: str
    JWT_EXPIRATION_MINUTES: int
    JWT_SECRET_KEY: str
    JWT_PRIVATE_KEY: str | None
    JWT_PUBLIC_KEY: str | None
    JWT_AUTO_GENERATE_KEYS: bool
    AUTH_PROVIDER: str
    AUTH_PASSWORD_FLOW_ENABLED: bool
    OIDC_ISSUER_URL: str | None
    OIDC_CLIENT_ID: str | None
    OIDC_CLIENT_SECRET: str | None
    OIDC_AUDIENCE: str | None
    OIDC_JWKS_URL: str | None
    OIDC_SCOPES: str
    OIDC_CLOCK_SKEW_LEEWAY_SECONDS: int
    OIDC_AUTO_PROVISION_USERS: bool
    OIDC_AUTO_LINK_BY_EMAIL: bool
    OIDC_REQUIRE_VERIFIED_EMAIL_FOR_LINK: bool
    OIDC_REQUIRE_MFA_FOR_MEMBERS: bool
    SKIP_LOCAL_MFA_FOR_EXTERNAL: bool
    KEYCLOAK_ADMIN_URL: str | None
    KEYCLOAK_ADMIN_REALM: str | None
    KEYCLOAK_ADMIN_CLIENT_ID: str | None
    KEYCLOAK_ADMIN_CLIENT_SECRET: str | None
    KEYCLOAK_USER_PROVISIONING_ENABLED: bool
    DEFAULT_ADMIN_BOOTSTRAP_ENABLED: bool
    REQUIRE_TOTP_ENCRYPTION_KEY: bool
    TRUSTED_PROXY_CIDRS: list[str]
    REQUIRE_CLIENT_IP_FOR_PUBLIC_ENDPOINTS: bool
    FORCE_SECURE_COOKIES: bool
    ALLOWLIST_FAIL_OPEN: bool
    RATE_LIMIT_GC_EVERY: int
    RATE_LIMIT_STALE_AFTER_SECONDS: int
    RATE_LIMIT_MAX_STATES: int
    RATE_LIMIT_FALLBACK_MODE: str
    PASSWORD_HASH_MAX_CONCURRENCY: int
    PASSWORD_RESET_INTERVAL_DAYS: int
    TEMP_PASSWORD_LENGTH: int
    DEFAULT_ADMIN_USERNAME: str
    DEFAULT_ADMIN_PASSWORD: str
    DEFAULT_ADMIN_EMAIL: str
    DEFAULT_ADMIN_TENANT: str
    DEFAULT_ORG_ID: str
    APP_ORG_KEY: str
    OTLP_GATEWAY_URL: str
    DEFAULT_OTLP_TOKEN: str | None
    VAULT_ENABLED: bool
    VAULT_ADDR: str | None
    VAULT_TOKEN: str | None
    VAULT_ROLE_ID: str | None
    VAULT_SECRET_ID: str | None
    VAULT_CACERT: str | None
    VAULT_SECRETS_PREFIX: str
    VAULT_KV_VERSION: int
    VAULT_TIMEOUT: float
    VAULT_FAIL_ON_MISSING: bool
    DEFAULT_RULE_GROUP: str
    DEFAULT_SLACK_CHANNEL: str
    ENABLED_NOTIFICATION_CHANNEL_TYPES: list[str]

    def __init__(self) -> None:
        self.secret_provider = None
        _populate_config(self)

    def load_vault_secrets(self) -> None:
        if not self.VAULT_ENABLED:
            return

        vault_mod = importlib.import_module("services.secrets.vault_client")

        if not self.VAULT_ADDR:
            raise ValueError("VAULT_ADDR must be set when VAULT_ENABLED=true")

        secret_id_fn = None
        if self.VAULT_SECRET_ID:
            secret_id = self.VAULT_SECRET_ID

            def _secret_id_fn() -> str:
                return secret_id

            secret_id_fn = _secret_id_fn

        provider: SecretProvider = vault_mod.VaultSecretProvider(
            vault_mod.VaultSecretProviderSettings(
                address=self.VAULT_ADDR,
                token=self.VAULT_TOKEN,
                role_id=self.VAULT_ROLE_ID,
                secret_id_fn=secret_id_fn,
                prefix=self.VAULT_SECRETS_PREFIX,
                kv_version=self.VAULT_KV_VERSION,
                timeout=self.VAULT_TIMEOUT,
                cacert=self.VAULT_CACERT,
            )
        )

        self.secret_provider = provider

        secret_keys = [
            "DATABASE_URL",
            "JWT_PRIVATE_KEY",
            "JWT_PUBLIC_KEY",
            "DEFAULT_ADMIN_PASSWORD",
            "DATA_ENCRYPTION_KEY",
            "GRAFANA_PASSWORD",
            "GRAFANA_API_KEY",
            "OIDC_CLIENT_SECRET",
            "KEYCLOAK_ADMIN_CLIENT_SECRET",
            "DEFAULT_OTLP_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "INBOUND_WEBHOOK_TOKEN",
            "OTLP_INGEST_TOKEN",
            "GATEWAY_INTERNAL_SERVICE_TOKEN",
            "NOTIFIER_SERVICE_TOKEN",
            "NOTIFIER_CONTEXT_SIGNING_KEY",
            "RESOLVER_SERVICE_TOKEN",
            "RESOLVER_CONTEXT_SIGNING_KEY",
            "AGENT_HEARTBEAT_TOKEN",
        ]

        for sk in secret_keys:
            try:
                val = provider.get(sk)
            except (OSError, RuntimeError, TypeError, ValueError):
                val = None
            if val:
                setattr(self, sk, val)
                logger.info("Loaded secret %s from Vault", sk)

    def get_secret(self, key: str) -> str | None:
        val = getattr(self, key, None)
        if val:
            return val if isinstance(val, str) else str(val)
        provider = self.secret_provider
        if provider is None:
            return None
        try:
            value = provider.get(key)
            return value if value is None else str(value)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None

    def apply_security_defaults(self) -> None:
        default_admin_password = getattr(self, "DEFAULT_ADMIN_PASSWORD", "")
        if _is_placeholder(default_admin_password, placeholders=["admin123", "admin", "password", "changeme"]):
            if not self.IS_PRODUCTION and self.DEFAULT_ADMIN_BOOTSTRAP_ENABLED:
                setattr(self, "DEFAULT_ADMIN_PASSWORD", secrets.token_urlsafe(18))
                logger.warning(
                    "Generated runtime DEFAULT_ADMIN_PASSWORD for non-production startup.",
                )

        jwt_secret_key = getattr(self, "JWT_SECRET_KEY", "")
        if _is_placeholder(
            jwt_secret_key, placeholders=["change-this-secret-key-in-production", "changeme", "secret", ""]
        ):
            if not self.IS_PRODUCTION:
                setattr(self, "JWT_SECRET_KEY", secrets.token_urlsafe(32))
                logger.info("Generated runtime JWT_SECRET_KEY for local compatibility.")

        jwt_private_key = getattr(self, "JWT_PRIVATE_KEY", None)
        jwt_public_key = getattr(self, "JWT_PUBLIC_KEY", None)
        if self.JWT_ALGORITHM in self.ALLOWED_JWT_ALGORITHMS and (not jwt_private_key or not jwt_public_key):
            if self.JWT_AUTO_GENERATE_KEYS and not self.IS_PRODUCTION:
                if self.JWT_ALGORITHM == "RS256":
                    private_key, public_key = _generate_rsa_keypair()
                elif self.JWT_ALGORITHM == "ES256":
                    private_key, public_key = _generate_ec_keypair()
                else:
                    raise ValueError("Unsupported JWT_ALGORITHM for auto key generation")

                setattr(self, "JWT_PRIVATE_KEY", private_key)
                setattr(self, "JWT_PUBLIC_KEY", public_key)
                logger.warning(
                    "Generated ephemeral JWT keypair for %s. Persist JWT_PRIVATE_KEY and "
                    "JWT_PUBLIC_KEY in a secret manager to avoid token invalidation on restart.",
                    self.JWT_ALGORITHM,
                )

    def _validate_identity_and_security(self) -> None:
        if self.DATABASE_URL == self.EXAMPLE_DATABASE_URL or "changeme123" in self.DATABASE_URL:
            raise ValueError(
                "Unsafe DATABASE_URL detected. Set DATABASE_URL to a non-example credentialed connection string."
            )

        if self.JWT_ALGORITHM not in self.ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"Unsupported JWT_ALGORITHM '{self.JWT_ALGORITHM}'. "
                f"Allowed values: {sorted(self.ALLOWED_JWT_ALGORITHMS)}"
            )

        if self.JWT_SECRET_KEY:
            logger.warning(
                "JWT_SECRET_KEY is currently unused for JWT_ALGORITHM=%s. "
                "Configure JWT_PRIVATE_KEY/JWT_PUBLIC_KEY instead.",
                self.JWT_ALGORITHM,
            )

        if self.JWT_ALGORITHM in self.ALLOWED_JWT_ALGORITHMS and (not self.JWT_PRIVATE_KEY or not self.JWT_PUBLIC_KEY):
            raise ValueError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be configured for RS256/ES256 tokens")

        if self.IS_PRODUCTION and self.JWT_AUTO_GENERATE_KEYS:
            raise ValueError("JWT_AUTO_GENERATE_KEYS must be disabled in production")

        if self.IS_PRODUCTION and self.DEFAULT_ADMIN_BOOTSTRAP_ENABLED:
            raise ValueError("DEFAULT_ADMIN_BOOTSTRAP_ENABLED must be false in production")

        if self.IS_PRODUCTION and self.DEFAULT_ADMIN_PASSWORD and _is_placeholder(
            self.DEFAULT_ADMIN_PASSWORD, placeholders=["admin123", "admin", "password", "changeme"]
        ):
            raise ValueError("DEFAULT_ADMIN_PASSWORD must be set to a strong value in production")

        if self.REQUIRE_TOTP_ENCRYPTION_KEY and not self.DATA_ENCRYPTION_KEY:
            raise ValueError("DATA_ENCRYPTION_KEY is required when REQUIRE_TOTP_ENCRYPTION_KEY is enabled")
        if self.IS_PRODUCTION and not self.DATA_ENCRYPTION_KEY:
            raise ValueError("DATA_ENCRYPTION_KEY must be configured in production")
        if self.DATA_ENCRYPTION_KEY:
            try:
                Fernet(self.DATA_ENCRYPTION_KEY)
            except (TypeError, ValueError) as exc:
                raise ValueError("DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc

        wildcard_enabled = any(origin.strip() == "*" for origin in self.CORS_ORIGINS)
        if wildcard_enabled and self.CORS_ALLOW_CREDENTIALS:
            raise ValueError("CORS_ORIGINS cannot contain '*' when CORS_ALLOW_CREDENTIALS is enabled.")

    def _validate_context_and_prod_secrets(self) -> None:
        if self.NOTIFIER_CONTEXT_ALGORITHM not in self.ALLOWED_CONTEXT_ALGORITHMS:
            raise ValueError(
                f"Unsupported NOTIFIER_CONTEXT_ALGORITHM '{self.NOTIFIER_CONTEXT_ALGORITHM}'. "
                f"Allowed values: {sorted(self.ALLOWED_CONTEXT_ALGORITHMS)}"
            )
        if self.RESOLVER_CONTEXT_ALGORITHM not in self.ALLOWED_CONTEXT_ALGORITHMS:
            raise ValueError(
                f"Unsupported RESOLVER_CONTEXT_ALGORITHM '{self.RESOLVER_CONTEXT_ALGORITHM}'. "
                f"Allowed values: {sorted(self.ALLOWED_CONTEXT_ALGORITHMS)}"
            )
        if self.NOTIFIER_CONTEXT_TTL_SECONDS <= 0:
            raise ValueError("NOTIFIER_CONTEXT_TTL_SECONDS must be greater than 0")
        if self.RESOLVER_CONTEXT_TTL_SECONDS <= 0:
            raise ValueError("RESOLVER_CONTEXT_TTL_SECONDS must be greater than 0")

        if self.IS_PRODUCTION:
            required_production_secrets = {
                "GATEWAY_INTERNAL_SERVICE_TOKEN": self.GATEWAY_INTERNAL_SERVICE_TOKEN,
                "NOTIFIER_SERVICE_TOKEN": self.NOTIFIER_SERVICE_TOKEN,
                "NOTIFIER_CONTEXT_SIGNING_KEY": self.NOTIFIER_CONTEXT_SIGNING_KEY,
                "RESOLVER_SERVICE_TOKEN": self.RESOLVER_SERVICE_TOKEN,
                "RESOLVER_CONTEXT_SIGNING_KEY": self.RESOLVER_CONTEXT_SIGNING_KEY,
                "INBOUND_WEBHOOK_TOKEN": self.INBOUND_WEBHOOK_TOKEN,
            }
            for key, value in required_production_secrets.items():
                if _is_weak_secret(value):
                    raise ValueError(f"{key} must be set to a strong non-placeholder secret in production")
            if self.ALLOWLIST_FAIL_OPEN:
                raise ValueError("ALLOWLIST_FAIL_OPEN must be false in production")

    def _validate_operational_limits(self) -> None:
        if self.MAX_QUERY_LIMIT <= 0:
            raise ValueError("MAX_QUERY_LIMIT must be greater than 0")
        if self.DEFAULT_QUERY_LIMIT <= 0:
            raise ValueError("DEFAULT_QUERY_LIMIT must be greater than 0")
        if self.DEFAULT_QUERY_LIMIT > self.MAX_QUERY_LIMIT:
            raise ValueError("DEFAULT_QUERY_LIMIT cannot exceed MAX_QUERY_LIMIT")
        if self.MAX_API_KEYS_PER_USER <= 0:
            raise ValueError("MAX_API_KEYS_PER_USER must be greater than 0")

        if self.QUOTA_NATIVE_TIMEOUT_SECONDS <= 0:
            raise ValueError("QUOTA_NATIVE_TIMEOUT_SECONDS must be greater than 0")
        if self.QUOTA_PROMETHEUS_TIMEOUT_SECONDS <= 0:
            raise ValueError("QUOTA_PROMETHEUS_TIMEOUT_SECONDS must be greater than 0")
        if self.QUOTA_USAGE_WINDOW_SECONDS <= 0:
            raise ValueError("QUOTA_USAGE_WINDOW_SECONDS must be greater than 0")

        if self.LOKI_FALLBACK_CONCURRENCY <= 0:
            raise ValueError("LOKI_FALLBACK_CONCURRENCY must be greater than 0")
        if self.LOKI_MAX_FALLBACK_QUERIES < 0:
            raise ValueError("LOKI_MAX_FALLBACK_QUERIES must be greater than or equal to 0")
        if self.LOKI_VOLUME_CACHE_TTL_SECONDS < 0:
            raise ValueError("LOKI_VOLUME_CACHE_TTL_SECONDS must be greater than or equal to 0")

        if self.TEMPO_TRACE_FETCH_CONCURRENCY <= 0:
            raise ValueError("TEMPO_TRACE_FETCH_CONCURRENCY must be greater than 0")
        if self.TEMPO_VOLUME_BUCKET_CONCURRENCY <= 0:
            raise ValueError("TEMPO_VOLUME_BUCKET_CONCURRENCY must be greater than 0")
        if self.TEMPO_COUNT_QUERY_CONCURRENCY <= 0:
            raise ValueError("TEMPO_COUNT_QUERY_CONCURRENCY must be greater than 0")

        if self.RESOLVER_PROXY_CACHE_TTL_SECONDS < 0:
            raise ValueError("RESOLVER_PROXY_CACHE_TTL_SECONDS must be greater than or equal to 0")

        if self.RESOLVER_ANALYZE_MAX_CONCURRENCY <= 0:
            raise ValueError("RESOLVER_ANALYZE_MAX_CONCURRENCY must be greater than 0")
        if self.RESOLVER_ANALYZE_MAX_RETAINED_PER_USER <= 0:
            raise ValueError("RESOLVER_ANALYZE_MAX_RETAINED_PER_USER must be greater than 0")
        if self.RESOLVER_ANALYZE_JOB_TTL_SECONDS <= 0:
            raise ValueError("RESOLVER_ANALYZE_JOB_TTL_SECONDS must be greater than 0")

        if self.PASSWORD_RESET_INTERVAL_DAYS < 0:
            raise ValueError("PASSWORD_RESET_INTERVAL_DAYS must be >= 0")
        if self.TEMP_PASSWORD_LENGTH < 12:
            raise ValueError("TEMP_PASSWORD_LENGTH must be >= 12")

    def validate(self) -> None:
        self._validate_identity_and_security()
        self._validate_context_and_prod_secrets()
        self._validate_operational_limits()


class Constants:
    APP_NAME: str = "Watchdog with Your Infrastructure"
    APP_VERSION: str = "0.0.5"
    APP_DESCRIPTION: str = "Unified API for managing Tempo, Loki, AlertManager, Grafana, and Resolver"

    STATUS_HEALTHY: str = "Healthy"
    STATUS_SUCCESS: str = "Success"
    STATUS_ERROR: str = "Error"

    SERVICE_TEMPO: str = "Tempo"
    SERVICE_LOKI: str = "Loki"
    SERVICE_ALERTMANAGER: str = "AlertManager"
    SERVICE_GRAFANA: str = "Grafana"
    SERVICE_RESOLVER: str = "Resolver"


config = Config()
constants = Constants()
