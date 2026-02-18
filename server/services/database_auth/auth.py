"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Optional, Union

import httpx

from config import config
from models.access.auth_models import Token
from services.auth.auth_ops import (
    create_access_token as create_access_token_op,
    validate_otlp_token as validate_otlp_token_op,
)


def login(service, username: str, password: str, mfa_code: Optional[str] = None) -> Optional[Union[Token, dict]]:
    if service.is_external_auth_enabled():
        if not service.is_password_auth_enabled():
            return None
        try:
            oidc_token = service.oidc_service.exchange_password(username, password)
        except (httpx.HTTPError, ValueError) as exc:
            service.logger.error("OIDC password login failed: %s", exc)
            return None
        access_token = oidc_token.get("access_token")
        if not access_token:
            return None
        claims = service.oidc_service.verify_access_token(access_token)
        if not claims:
            return None
        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None
        return Token(
            access_token=access_token,
            token_type=oidc_token.get("token_type", "bearer"),
            expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
        )

    user = service.authenticate_user(username, password)
    if not user:
        return None
    if service._needs_mfa_setup(user):
        return service._mfa_setup_challenge(user)
    if getattr(user, "mfa_enabled", False):
        if not mfa_code:
            return {service._MFA_REQUIRED_RESPONSE: True}
        if not service.verify_totp_code(user, mfa_code):
            return None
    return service.create_access_token(user)


def exchange_oidc_authorization_code(service, code: str, redirect_uri: str) -> Optional[Union[Token, dict]]:
    if not service.is_external_auth_enabled():
        return None
    try:
        oidc_token = service.oidc_service.exchange_authorization_code(code, redirect_uri)
        access_token = oidc_token.get("access_token")
        if not access_token:
            return None
        claims = service.oidc_service.verify_access_token(access_token)
        if not claims:
            return None
        user = service._sync_user_from_oidc_claims(claims)
        if not user or not user.is_active:
            return None
        if service._needs_mfa_setup(user):
            return service._mfa_setup_challenge(user)
        return Token(
            access_token=access_token,
            token_type=oidc_token.get("token_type", "bearer"),
            expires_in=int(oidc_token.get("expires_in", config.JWT_EXPIRATION_MINUTES * 60)),
        )
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("OIDC code exchange failed: %s", exc)
        return None


def get_oidc_authorization_url(service, redirect_uri: str, state: str, nonce: str) -> str:
    return service.oidc_service.build_authorization_url(redirect_uri, state, nonce)


def provision_external_user(service, *, email: str, username: str, full_name: Optional[str]) -> Optional[str]:
    if not service.is_external_auth_enabled():
        return None
    try:
        return service.oidc_service.create_keycloak_user(email=email, username=username, full_name=full_name)
    except (httpx.HTTPError, ValueError) as exc:
        service.logger.error("External user provisioning failed: %s", exc)
        return None
