"""
Notification service for sending emails related to incidents and user management in Watchdog.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from html import escape as html_escape
from pathlib import Path
from string import Template
from types import ModuleType
from typing import TypedDict

from config import config
from services.common.http_client import create_async_client

try:
    import aiosmtplib as _loaded_aiosmtplib
except ImportError:
    _AIOSMTPLIB: ModuleType | None = None
else:
    _AIOSMTPLIB = _loaded_aiosmtplib

logger = logging.getLogger(__name__)

BOOL_TRUE = {"1", "true", "yes", "on"}
_EMAIL_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "emails"


class SMTPConfig(TypedDict):
    hostname: str
    port: int
    username: str | None
    password: str | None
    from_addr: str
    envelope_from: str
    start_tls: bool
    use_tls: bool


@dataclass(frozen=True, slots=True)
class WelcomeEmailRequest:
    recipient_email: str
    username: str
    full_name: str | None = None
    login_url: str | None = None


@dataclass(frozen=True, slots=True)
class TemporaryPasswordEmailRequest:
    recipient_email: str
    username: str
    temporary_password: str
    login_url: str | None = None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in BOOL_TRUE
    return False


def _first_secret(*keys: str) -> str | None:
    for key in keys:
        v = config.get_secret(key)
        if v:
            return v
    return None


def _is_enabled(*keys: str) -> bool:
    v = _first_secret(*keys)
    return str(v or "false").strip().lower() in BOOL_TRUE


def _smtp_config(*prefixes: str) -> SMTPConfig:
    def get(*suffixes: str) -> str | None:
        return _first_secret(*(f"{p}_{s}" for p in prefixes for s in suffixes))

    try:
        port = int(get("SMTP_PORT") or "587")
    except ValueError:
        port = 587

    default_sender = str(config.DEFAULT_ADMIN_EMAIL or "").strip()
    raw_from = str(get("FROM") or "").strip()
    display_name, parsed_addr = parseaddr(raw_from)
    has_valid_parsed_addr = "@" in parsed_addr
    has_default_sender = "@" in default_sender
    envelope_from = parsed_addr if has_valid_parsed_addr else (default_sender if has_default_sender else "")

    if raw_from and not has_valid_parsed_addr and envelope_from:
        header_from = formataddr((raw_from, envelope_from))
    elif has_valid_parsed_addr:
        header_from = formataddr((display_name, parsed_addr)) if display_name else parsed_addr
    else:
        header_from = envelope_from or raw_from or default_sender

    return {
        "hostname": (get("SMTP_HOST") or "").strip(),
        "port": port,
        "username": get("SMTP_USERNAME"),
        "password": get("SMTP_PASSWORD"),
        "from_addr": header_from,
        "envelope_from": envelope_from or header_from,
        "start_tls": _as_bool(get("SMTP_STARTTLS") or "true"),
        "use_tls": _as_bool(get("SMTP_USE_SSL") or "false"),
    }


def _render_html_template(template_name: str, values: dict[str, str]) -> str | None:
    path = _EMAIL_TEMPLATE_ROOT / template_name
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Email template %s could not be loaded: %s", path, exc)
        return None
    safe_values = {k: (str(v or "") if k.endswith("_html") else html_escape(str(v or ""))) for k, v in values.items()}
    return Template(raw).safe_substitute(safe_values)


class NotificationService:
    def __init__(self) -> None:
        self.timeout = float(config.DEFAULT_TIMEOUT)
        self._client = create_async_client(self.timeout)

    async def _send_smtp(self, *, message: EmailMessage, cfg: SMTPConfig) -> None:
        if _AIOSMTPLIB is None:
            raise RuntimeError("aiosmtplib is unavailable")
        await _AIOSMTPLIB.send(
            message,
            hostname=cfg["hostname"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            sender=cfg["envelope_from"],
            start_tls=cfg["start_tls"],
            use_tls=cfg["use_tls"],
            timeout=self.timeout,
        )

    async def _dispatch(self, cfg: SMTPConfig, msg: EmailMessage, recipient: str) -> bool:
        try:
            await self._send_smtp(message=msg, cfg=cfg)
            return True
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("Failed to send email to %s: %s", recipient, exc)
            return False

    def _build_message(self, *, subject: str, cfg: SMTPConfig, recipient: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = recipient
        msg.set_content(body)
        return msg

    async def send_user_welcome_email(
        self,
        email_request: WelcomeEmailRequest,
    ) -> bool:
        request = email_request
        if not _is_enabled("USER_WELCOME_EMAIL_ENABLED"):
            return False
        cfg = _smtp_config("USER_WELCOME")
        if not cfg["hostname"]:
            logger.info("User welcome email skipped: SMTP host not set")
            return False
        app_login_url = (request.login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""
        msg = self._build_message(
            subject="Welcome to Watchdog",
            cfg=cfg,
            recipient=request.recipient_email,
            body=(
                f"Hello {request.full_name or request.username},\n\n"
                "Your account was created in Watchdog.\n"
                f"Username: {request.username}\n"
                f"{login_line}"
                "If this is your first login, follow your administrator's instructions "
                "for credentials and MFA setup. If OIDC is enabled, please just login "
                "with this email account.\n"
            ),
        )
        login_url_html = html_escape(app_login_url)
        login_row_html = (
            f"<p class='meta'><span>Login URL</span><br><a href='{login_url_html}'>{login_url_html}</a></p>"
            if app_login_url
            else ""
        )
        html_body = _render_html_template(
            "welcome_user.html",
            {
                "display_name": request.full_name or request.username,
                "username": request.username,
                "login_row_html": login_row_html,
            },
        )
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        result = await self._dispatch(cfg, msg, request.recipient_email)
        if result:
            logger.info("User welcome email sent to %s", request.recipient_email)
        return result

    async def send_temporary_password_email(
        self,
        email_request: TemporaryPasswordEmailRequest,
    ) -> bool:
        request = email_request
        if not _is_enabled("PASSWORD_RESET_EMAIL_ENABLED", "USER_WELCOME_EMAIL_ENABLED"):
            return False
        cfg = _smtp_config("PASSWORD_RESET", "USER_WELCOME")
        if not cfg["hostname"]:
            logger.info("Temporary password email skipped: SMTP host not set")
            return False
        app_login_url = (request.login_url or config.get_secret("APP_LOGIN_URL") or "").strip()
        login_line = f"Login URL: {app_login_url}\n" if app_login_url else ""
        msg = self._build_message(
            subject="Temporary Password for Watchdog",
            cfg=cfg,
            recipient=request.recipient_email,
            body=(
                f"Hello {request.username},\n\n"
                "Your password has been reset by an administrator.\n\n"
                "Temporary password\n"
                f"{request.temporary_password}\n\n"
                f"{login_line}"
                "Please change this password immediately after login.\n"
                "This applies only to local/password authentication.\n\n"
                "If you did not expect this change, contact your administrator.\n"
            ),
        )
        login_url_html = html_escape(app_login_url)
        login_row_html = (
            f"<p class='meta'><span>Login URL</span><br><a href='{login_url_html}'>{login_url_html}</a></p>"
            if app_login_url
            else ""
        )
        html_body = _render_html_template(
            "temporary_password.html",
            {
                "username": request.username,
                "temporary_password": request.temporary_password,
                "login_row_html": login_row_html,
            },
        )
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        result = await self._dispatch(cfg, msg, request.recipient_email)
        if result:
            logger.info("Temporary password email sent to %s", request.recipient_email)
        return result
