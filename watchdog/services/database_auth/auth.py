"""
Database-authenticated user provisioning and OIDC/MFA handling.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from custom_types.json import JSONDict
from db_models import User
from models.access.auth_models import Token
from services.auth.oidc_service import OidcTransactionStartRequest
from services.database_auth.shared import sync_active_user_from_claims

if TYPE_CHECKING:
    from services.database_auth_service import DatabaseAuthService

AuthResult = Token | JSONDict | None
PKCE_CODE_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
EXTERNAL_USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,50}$")
EXTERNAL_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
MAX_EXTERNAL_FULL_NAME_LENGTH = 200
OIDC_MFA_CHALLENGE_TTL_SECONDS = 300
_OIDC_MFA_CHALLENGES: dict[str, tuple[float, User]] = {}
_OIDC_MFA_CHALLENGES_LOCK = threading.Lock()


@dataclass(frozen=True)
class _OidcTokens:
    access_token: str
    id_token: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> _OidcTokens:
        return cls(
            access_token=str(payload.get("access_token") or ""),
            id_token=str(payload.get("id_token") or ""),
        )

    def is_empty(self) -> bool:
        return not self.access_token and not self.id_token


def _prune_oidc_mfa_challenges(now: float | None = None) -> None:
    t = time.monotonic() if now is None else now
    for challenge_id, (expires_at, _user) in list(_OIDC_MFA_CHALLENGES.items()):
        if expires_at <= t:
            _OIDC_MFA_CHALLENGES.pop(challenge_id, None)


def _create_oidc_mfa_challenge(user: User) -> str:
    challenge_id = secrets.token_urlsafe(24)
    expires_at = time.monotonic() + OIDC_MFA_CHALLENGE_TTL_SECONDS
    with _OIDC_MFA_CHALLENGES_LOCK:
        _prune_oidc_mfa_challenges()
        _OIDC_MFA_CHALLENGES[challenge_id] = (expires_at, user)
    return challenge_id


def _get_oidc_mfa_challenge_user(challenge_id: str) -> User | None:
    key = str(challenge_id or "").strip()
    if not key:
        return None
    with _OIDC_MFA_CHALLENGES_LOCK:
        _prune_oidc_mfa_challenges()
        row = _OIDC_MFA_CHALLENGES.get(key)
        if row is None:
            return None
        _expires_at, user = row
        return user


def _clear_oidc_mfa_challenge(challenge_id: str) -> None:
    key = str(challenge_id or "").strip()
    if not key:
        return
    with _OIDC_MFA_CHALLENGES_LOCK:
        _OIDC_MFA_CHALLENGES.pop(key, None)


def _mfa_gate(service: DatabaseAuthService, user: User, mfa_code: str | None) -> bool | JSONDict | Token | None:
    if service.needs_mfa_setup(user):
        return service.mfa_setup_challenge(user)

    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service.MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None

    return True


def _resolve_oidc_claims(
    service: DatabaseAuthService, *, tokens: _OidcTokens, expected_nonce: str, enforce_nonce: bool
) -> JSONDict | None:
    if enforce_nonce and not expected_nonce:
        service.logger.warning("OIDC nonce enforcement requested but expected nonce is missing")
        return None

    if not tokens.id_token:
        service.logger.warning("OIDC response missing id_token; refusing access_token identity fallback")
        return None

    claims = service.oidc_service.verify_id_token(tokens.id_token, nonce=(expected_nonce or None))
    if not claims:
        service.logger.warning("OIDC id_token verification failed")
        return None

    return claims


def _normalize_pkce_code_verifier(code_verifier: str | None) -> str | None:
    if code_verifier is None:
        return None
    value = str(code_verifier).strip()
    if not value:
        return None
    if not PKCE_CODE_VERIFIER_PATTERN.fullmatch(value):
        return None
    return value


def _normalize_external_provisioning_inputs(
    *,
    email: str,
    username: str | None,
    full_name: str | None,
) -> tuple[str, str, str | None] | None:
    email_value = str(email or "").strip().lower()
    if not EXTERNAL_EMAIL_PATTERN.fullmatch(email_value):
        return None

    username_value = str(username or "").strip().lower()
    if not username_value:
        username_value = email_value.split("@", 1)[0]
    if not EXTERNAL_USERNAME_PATTERN.fullmatch(username_value):
        return None

    normalized_full_name: str | None = None
    if full_name is not None:
        collapsed = " ".join(str(full_name).split()).strip()
        if collapsed:
            normalized_full_name = collapsed[:MAX_EXTERNAL_FULL_NAME_LENGTH]

    return email_value, username_value, normalized_full_name


def login(  # pylint: disable=too-many-return-statements
    service: DatabaseAuthService, username: str, password: str, mfa_code: str | None = None
) -> AuthResult:
    external_flow = service.is_external_auth_enabled()

    if external_flow:
        if not service.is_password_auth_enabled():
            return None

        try:
            oidc_token = service.oidc_service.exchange_password(username, password)
        except (httpx.HTTPError, ValueError) as exc:
            service.logger.error("OIDC password login failed for user %s: %s", username, type(exc).__name__)
            return None

        tokens = _OidcTokens.from_mapping(oidc_token if isinstance(oidc_token, dict) else {})
        if tokens.is_empty():
            return None

        claims = _resolve_oidc_claims(
            service,
            tokens=tokens,
            expected_nonce="",
            enforce_nonce=False,
        )
        user = sync_active_user_from_claims(service, claims)
        if user is None:
            return None

        mfa_result = _mfa_gate(service, user, mfa_code)
        if mfa_result is not True:
            if isinstance(mfa_result, (Token, dict)):
                return mfa_result
            return None

        token = service.create_access_token(user)
        return token if isinstance(token, Token) else None

    user = service.authenticate_user(username, password)
    if not user:
        return None

    mfa_result = _mfa_gate(service, user, mfa_code)
    if mfa_result is not True:
        if isinstance(mfa_result, (Token, dict)):
            return mfa_result
        return None

    token = service.create_access_token(user)
    return token if isinstance(token, Token) else None


def exchange_oidc_authorization_code(
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements
    service: DatabaseAuthService,
    code: str,
    redirect_uri: str,
    transaction_id: str | None = None,
    state: str | None = None,
    code_verifier: str | None = None,
    mfa_code: str | None = None,
    mfa_challenge_id: str | None = None,
) -> AuthResult:
    if not service.is_external_auth_enabled():
        return None

    existing_mfa_challenge = str(mfa_challenge_id or "").strip()
    if existing_mfa_challenge:
        challenge_user = _get_oidc_mfa_challenge_user(existing_mfa_challenge)
        if challenge_user is None:
            service.logger.warning("OIDC MFA challenge missing or expired")
            return None
        if not mfa_code:
            return {
                service.MFA_REQUIRED_RESPONSE: True,
                "mfa_challenge_id": existing_mfa_challenge,
            }
        if not service.verify_totp_code(challenge_user, mfa_code):
            return {
                service.MFA_REQUIRED_RESPONSE: True,
                "mfa_challenge_id": existing_mfa_challenge,
            }
        _clear_oidc_mfa_challenge(existing_mfa_challenge)
        token = service.create_access_token(challenge_user)
        return token if isinstance(token, Token) else None

    normalized_code_verifier = _normalize_pkce_code_verifier(code_verifier)
    if code_verifier is not None and normalized_code_verifier is None:
        service.logger.warning("OIDC code exchange rejected due to invalid PKCE code_verifier format")
        return None

    try:
        txn: JSONDict = {}
        if transaction_id or state:
            txn_raw = service.oidc_service.consume_authorization_transaction(
                transaction_id=transaction_id,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=normalized_code_verifier,
            )
            txn = txn_raw if isinstance(txn_raw, dict) else {}

        tokens_payload = service.oidc_service.exchange_authorization_code(
            code,
            redirect_uri,
            code_verifier=(
                normalized_code_verifier if (txn.get("code_challenge") or normalized_code_verifier) else None
            ),
        )

        tokens = _OidcTokens.from_mapping(tokens_payload if isinstance(tokens_payload, dict) else {})
        if tokens.is_empty():
            service.logger.warning("OIDC exchange returned no tokens")
            return None

        nonce_value = txn.get("nonce")
        expected_nonce = nonce_value.strip() if isinstance(nonce_value, str) else ""

        claims = _resolve_oidc_claims(
            service,
            tokens=tokens,
            expected_nonce=expected_nonce,
            enforce_nonce=True,
        )
        if not claims:
            service.logger.warning("OIDC claims resolution failed")
            return None

        user = sync_active_user_from_claims(service, claims)
        if user is None:
            return None

        mfa_result = _mfa_gate(service, user, mfa_code=mfa_code)
        if mfa_result is not True:
            if isinstance(mfa_result, dict) and mfa_result.get(service.MFA_REQUIRED_RESPONSE):
                challenge_id = _create_oidc_mfa_challenge(user)
                return {
                    service.MFA_REQUIRED_RESPONSE: True,
                    "mfa_challenge_id": challenge_id,
                }
            if isinstance(mfa_result, (Token, dict)):
                return mfa_result
            return None

        token = service.create_access_token(user)
        return token if isinstance(token, Token) else None

    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("OIDC code exchange failed: %s", type(exc).__name__)
        return None


def get_oidc_authorization_url(
    service: DatabaseAuthService,
    request: OidcAuthorizationUrlRequest,
) -> dict[str, str]:
    result = service.oidc_service.start_authorization_transaction(
        request=OidcTransactionStartRequest(
            redirect_uri=request.redirect_uri,
            state=request.state,
            nonce=request.nonce,
            code_challenge=request.code_challenge,
            code_challenge_method=request.code_challenge_method,
        )
    )
    if not isinstance(result, dict):
        raise ValueError("OIDC authorization transaction did not return a mapping")

    authorization_url = result.get("authorization_url")
    if not isinstance(authorization_url, str) or not authorization_url.strip():
        raise ValueError("OIDC authorization transaction did not return an authorization_url")

    return {str(key): str(value) for key, value in result.items()}


@dataclass(frozen=True, slots=True)
class OidcAuthorizationUrlRequest:
    redirect_uri: str
    state: str | None = None
    nonce: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None


def provision_external_user(
    service: DatabaseAuthService, *, email: str, username: str, full_name: str | None
) -> str | None:
    if not service.is_external_auth_enabled():
        return None

    normalized_inputs = _normalize_external_provisioning_inputs(
        email=email,
        username=username,
        full_name=full_name,
    )
    if normalized_inputs is None:
        service.logger.warning("External user provisioning rejected due to invalid identity input")
        return None

    safe_email, safe_username, safe_full_name = normalized_inputs

    try:
        result = service.oidc_service.create_keycloak_user(
            email=safe_email,
            username=safe_username,
            full_name=safe_full_name,
        )
        return result if isinstance(result, str) or result is None else str(result)
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("External user provisioning failed for %s: %s", safe_username, type(exc).__name__)
        return None
