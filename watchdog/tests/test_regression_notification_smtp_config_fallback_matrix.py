"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from services import notification_service as notification_mod


def test_smtp_config_defaults_port_to_587_on_invalid_input(monkeypatch) -> None:
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_SMTP_HOST": "smtp.example.com",
            "USER_WELCOME_SMTP_PORT": "invalid-port",
        }.get(key),
    )

    cfg = notification_mod._smtp_config("USER_WELCOME")

    assert cfg["hostname"] == "smtp.example.com"
    assert cfg["port"] == 587


def test_smtp_config_uses_default_sender_when_from_is_name_only(monkeypatch) -> None:
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_SMTP_HOST": "smtp.example.com",
            "USER_WELCOME_FROM": "Observantio Alerts",
        }.get(key),
    )

    cfg = notification_mod._smtp_config("USER_WELCOME")

    assert "Observantio Alerts" in cfg["from_addr"]
    assert "admin@example.com" in cfg["from_addr"]
    assert cfg["envelope_from"] == "admin@example.com"


def test_smtp_config_keeps_explicit_from_address_and_display_name(monkeypatch) -> None:
    monkeypatch.setattr(notification_mod.config, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "USER_WELCOME_SMTP_HOST": "smtp.example.com",
            "USER_WELCOME_FROM": "Watchdog Alerts <alerts@example.com>",
        }.get(key),
    )

    cfg = notification_mod._smtp_config("USER_WELCOME")

    assert "alerts@example.com" in cfg["from_addr"]
    assert cfg["envelope_from"] == "alerts@example.com"


def test_is_enabled_uses_truthy_boolean_strings(monkeypatch) -> None:
    monkeypatch.setattr(notification_mod.config, "get_secret", lambda key: {"A": "true", "B": "0"}.get(key))

    assert notification_mod._is_enabled("A") is True
    assert notification_mod._is_enabled("B") is False


def test_first_secret_returns_first_present_key(monkeypatch) -> None:
    monkeypatch.setattr(
        notification_mod.config,
        "get_secret",
        lambda key: {
            "PASSWORD_RESET_SMTP_HOST": "",
            "USER_WELCOME_SMTP_HOST": "smtp.welcome.example",
        }.get(key),
    )

    value = notification_mod._first_secret("PASSWORD_RESET_SMTP_HOST", "USER_WELCOME_SMTP_HOST")

    assert value == "smtp.welcome.example"
