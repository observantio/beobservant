"""
Service for managing authentication and authorization, providing functions for user management, group management,
permission handling, API key management, and integration with external identity providers. This module includes logic
for authenticating users, generating and validating access tokens, managing multi-factor authentication (MFA) using
TOTP, and synchronizing user information from external OIDC providers. The service also handles the assignment of
permissions to users and groups, the creation and management of API keys, and the logging of audit events related to
authentication and authorization actions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import secrets
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast

from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def _load_db_models_module() -> ModuleType:
    try:
        return importlib.import_module("db_models")
    except ImportError as exc:
        repo_root = Path(__file__).resolve().parent.parent
        db_models_path = repo_root / "db_models.py"
        if not db_models_path.exists():
            raise
        spec = importlib.util.spec_from_file_location("db_models", str(db_models_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load db_models from {db_models_path}") from exc
        db_models = importlib.util.module_from_spec(spec)
        sys.modules["db_models"] = db_models
        spec.loader.exec_module(db_models)
        return db_models


if TYPE_CHECKING:
    from db_models import Group, User, UserApiKey
else:
    _db_models_mod = _load_db_models_module()
    Group = _db_models_mod.Group
    User = _db_models_mod.User
    UserApiKey = _db_models_mod.UserApiKey

# pylint: disable=wrong-import-position
from config import config
from custom_types.json import JSONDict
from models.access.api_key_models import ApiKey, ApiKeyCreate, ApiKeyUpdate
from models.access.auth_models import Token, TokenData
from models.access.group_models import Group as GroupSchema
from models.access.group_models import GroupCreate, GroupUpdate
from models.access.user_models import (
    User as UserSchema,
)
from models.access.user_models import (
    UserCreate,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)
from services.auth.actor_caps import AuthActorCaps
from services.auth.api_key_ops import (
    ApiKeyShareReplaceRequest as ApiKeyShareReplaceOpsRequest,
)
from services.auth.api_key_ops import (
    backfill_otlp_tokens as backfill_otlp_tokens_op,
)
from services.auth.api_key_ops import (
    create_api_key as create_api_key_op,
)
from services.auth.api_key_ops import (
    delete_api_key as delete_api_key_op,
)
from services.auth.api_key_ops import (
    delete_api_key_share as delete_api_key_share_op,
)
from services.auth.api_key_ops import (
    list_api_key_shares as list_api_key_shares_op,
)
from services.auth.api_key_ops import (
    list_api_keys as list_api_keys_op,
)
from services.auth.api_key_ops import (
    regenerate_api_key_otlp_token as regenerate_api_key_otlp_token_op,
)
from services.auth.api_key_ops import (
    replace_api_key_shares as replace_api_key_shares_op,
)
from services.auth.api_key_ops import (
    set_api_key_hidden as set_api_key_hidden_op,
)
from services.auth.api_key_ops import (
    update_api_key as update_api_key_op,
)
from services.auth.auth_ops import (
    authenticate_user as authenticate_user_op,
)
from services.auth.auth_ops import (
    create_access_token as create_access_token_op,
)
from services.auth.auth_ops import (
    update_password as update_password_op,
)
from services.auth.auth_ops import (
    validate_otlp_token as validate_otlp_token_op,
)
from services.auth.group_ops import (
    create_group as create_group_op,
)
from services.auth.group_ops import (
    delete_group as delete_group_op,
)
from services.auth.group_ops import (
    get_group as get_group_op,
)
from services.auth.group_ops import (
    list_groups as list_groups_op,
)
from services.auth.group_ops import (
    update_group as update_group_op,
)
from services.auth.group_ops import (
    update_group_members as update_group_members_op,
)
from services.auth.group_ops import (
    update_group_permissions as update_group_permissions_op,
)
from services.auth.oidc_service import OIDCService
from services.auth.user_ops import (
    create_user as create_user_op,
)
from services.auth.user_ops import (
    delete_user as delete_user_op,
)
from services.auth.user_ops import (
    get_user_by_id as get_user_by_id_op,
)
from services.auth.user_ops import (
    get_user_by_username as get_user_by_username_op,
)
from services.auth.user_ops import (
    list_users as list_users_op,
)
from services.auth.user_ops import (
    set_grafana_user_id as set_grafana_user_id_op,
)
from services.auth.user_ops import (
    update_user as update_user_op,
)
from services.auth.user_ops import (
    update_user_permissions as update_user_permissions_op,
)
from services.database_auth import (
    audit as db_audit,
)
from services.database_auth import (
    auth as db_auth,
)
from services.database_auth import (
    bootstrap as db_bootstrap,
)
from services.database_auth import (
    mfa as db_mfa,
)
from services.database_auth import (
    oidc as db_oidc,
)
from services.database_auth import (
    password as db_password,
)
from services.database_auth import (
    permissions as db_permissions,
)
from services.database_auth import (
    schema_converters as db_schema,
)
from services.database_auth import (
    token as db_token,
)
from services.database_auth.service_state import DatabaseAuthServiceState
from services.secrets.provider import SecretProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OidcUserUpdateProfile:
    email: str
    full_name: str | None
    subject: str


@dataclass(frozen=True, slots=True)
class ApiKeyShareReplaceRequest:
    tenant_id: str
    key_id: str
    user_ids: list[str]
    group_ids: list[str] | None = None


class _DatabaseAuthCredentialsMixin(DatabaseAuthServiceState):
    """Authentication modes, lifecycle, passwords, MFA/TOTP, and OTLP token helpers."""

    def is_external_auth_enabled(self) -> bool:
        return config.AUTH_PROVIDER in {"oidc", "keycloak"} and self.oidc_service.is_enabled()

    def is_password_auth_enabled(self) -> bool:
        return bool(config.AUTH_PASSWORD_FLOW_ENABLED)

    def ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            try:
                self._ensure_default_setup()
                self._initialized = True
            except (SQLAlchemyError, ValueError) as exc:
                logger.warning("Failed to initialize auth service: %s", exc)

    def _ensure_default_setup(self) -> None:
        db_bootstrap.ensure_default_setup(_as_db_auth(self))

    def _ensure_permissions(self, db: Session) -> None:
        db_bootstrap.ensure_permissions(db)

    def ensure_default_api_key(self, db: Session, user: User) -> None:
        db_bootstrap.ensure_default_api_key(_as_db_auth(self), db, user)

    def hash_password(self, password: str) -> str:
        return db_password.hash_password(_as_db_auth(self), password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return db_password.verify_password(_as_db_auth(self), plain_password, hashed_password)

    def reset_user_password_temp(self, actor_user_id: str, target_user_id: str, tenant_id: str) -> JSONDict:
        result = db_password.reset_user_password_temp(_as_db_auth(self), actor_user_id, target_user_id, tenant_id)
        return {str(key): value for key, value in result.items()}

    @staticmethod
    def generate_otlp_token() -> str:
        return f"bo_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_otlp_token(token: str) -> str:
        return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

    def resolve_default_otlp_token(self) -> str:
        return config.DEFAULT_OTLP_TOKEN or self.generate_otlp_token()

    def log_audit(self, db: Session, record: db_audit.AuditLogRecord) -> None:
        db_audit.log_audit(db, record)


class _DatabaseAuthMfaMixin(DatabaseAuthServiceState):
    """MFA/TOTP and recovery code helpers."""

    def get_mfa_fernet(self) -> Fernet | None:
        return db_mfa.get_mfa_fernet(_as_db_auth(self))

    def encrypt_mfa_secret(self, secret: str) -> str:
        return db_mfa.encrypt_mfa_secret(_as_db_auth(self), secret)

    def decrypt_mfa_secret(self, token: str) -> str:
        return db_mfa.decrypt_mfa_secret(_as_db_auth(self), token)

    def generate_recovery_codes(self, count: int = 10) -> list[str]:
        return db_mfa.generate_recovery_codes(_as_db_auth(self), count)

    def hash_recovery_codes(self, codes: list[str]) -> list[str]:
        return db_mfa.hash_recovery_codes(_as_db_auth(self), codes)

    def consume_recovery_code(self, db_user: User, code: str) -> bool:
        return db_mfa.consume_recovery_code(_as_db_auth(self), db_user, code)

    def enroll_totp(self, user_id: str) -> dict[str, str]:
        return db_mfa.enroll_totp(_as_db_auth(self), user_id)

    def verify_enable_totp(self, user_id: str, code: str) -> list[str]:
        return db_mfa.verify_enable_totp(_as_db_auth(self), user_id, code)

    def verify_totp_code(self, user: User, code: str) -> bool:
        return db_mfa.verify_totp_code(_as_db_auth(self), user, code)

    def disable_totp(
        self,
        user_id: str,
        *,
        current_password: str | None = None,
        code: str | None = None,
    ) -> bool:
        return db_mfa.disable_totp(_as_db_auth(self), user_id, current_password=current_password, code=code)

    def reset_totp(self, user_id: str, admin_id: str) -> bool:
        return db_mfa.reset_totp(_as_db_auth(self), user_id, admin_id)

    def mfa_setup_challenge(self, user: User) -> JSONDict:
        return db_mfa.mfa_setup_challenge(_as_db_auth(self), user)

    def needs_mfa_setup(self, user: User) -> bool:
        return db_mfa.needs_mfa_setup(user)

    def _check_local_mfa(
        self,
        _svc: DatabaseAuthService,
        user: User,
        token: str | None,
    ) -> bool | JSONDict | Token | None:
        if getattr(user, "auth_provider", "local") != "local" and config.SKIP_LOCAL_MFA_FOR_EXTERNAL:
            return True

        setup_response = getattr(self, "MFA_SETUP_RESPONSE", "mfa_setup_required")
        required_response = getattr(self, "MFA_REQUIRED_RESPONSE", "mfa_required")

        if self.needs_mfa_setup(user):
            return {setup_response: True}

        if getattr(user, "mfa_enabled", False):
            if not token:
                return {required_response: True}
            if not self.verify_totp_code(user, token):
                return None

        return True


class _DatabaseAuthAuthFlowMixin(DatabaseAuthServiceState):
    """Access tokens, login and OIDC flows."""

    def create_access_token(self, user: User) -> Token:
        return create_access_token_op(_as_db_auth(self), user)

    def _build_token_data_for_user(self, user: User) -> TokenData:
        return db_token.build_token_data_for_user(_as_db_auth(self), user)

    def decode_token(self, token: str) -> TokenData | None:
        return db_token.decode_token(_as_db_auth(self), token)

    def authenticate_user(self, username: str, password: str) -> User | None:
        svc = _as_db_auth(self)
        if svc.is_external_auth_enabled() and not svc.is_password_auth_enabled():
            return None
        return authenticate_user_op(svc, username, password)

    def login(self, username: str, password: str, mfa_code: str | None = None) -> Token | JSONDict | None:
        return db_auth.login(_as_db_auth(self), username, password, mfa_code)

    def exchange_oidc_authorization_code(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        code: str,
        redirect_uri: str,
        transaction_id: str | None = None,
        state: str | None = None,
        code_verifier: str | None = None,
        mfa_code: str | None = None,
        mfa_challenge_id: str | None = None,
    ) -> Token | JSONDict | None:
        return db_auth.exchange_oidc_authorization_code(
            _as_db_auth(self),
            code,
            redirect_uri,
            transaction_id=transaction_id,
            state=state,
            code_verifier=code_verifier,
            mfa_code=mfa_code,
            mfa_challenge_id=mfa_challenge_id,
        )

    def get_oidc_authorization_url(
        self,
        request: db_auth.OidcAuthorizationUrlRequest,
    ) -> dict[str, str]:
        return db_auth.get_oidc_authorization_url(_as_db_auth(self), request)

    def provision_external_user(self, *, email: str, username: str, full_name: str | None) -> str | None:
        return db_auth.provision_external_user(_as_db_auth(self), email=email, username=username, full_name=full_name)

    def extract_permissions_from_oidc_claims(self, claims: JSONDict) -> list[str]:
        return db_oidc.extract_permissions_from_oidc_claims(claims)

    def sync_user_from_oidc_claims(self, claims: JSONDict) -> User | None:
        return db_oidc.sync_user_from_oidc_claims(_as_db_auth(self), claims)

    def _provision_oidc_user(
        self,
        db: Session,
        profile: db_oidc.OidcProvisionProfile,
    ) -> User:
        return db_oidc.provision_oidc_user(_as_db_auth(self), db, profile)

    def _update_oidc_user(self, db: Session, user: User, profile: OidcUserUpdateProfile) -> None:
        db_oidc.update_oidc_user(
            _as_db_auth(self),
            db,
            user,
            db_oidc.OidcUserUpdateProfile(
                email=profile.email,
                full_name=profile.full_name,
                subject=profile.subject,
            ),
        )


class _DatabaseAuthPermissionsMixin(DatabaseAuthServiceState):
    """Permission, schema conversion, and group management helpers."""

    def get_user_permissions(self, user: User | UserSchema) -> list[str]:
        return db_permissions.get_user_permissions(_as_db_auth(self), user)

    def get_user_direct_permissions(self, user: User | UserSchema) -> list[str]:
        return db_permissions.get_user_direct_permissions(user)

    def collect_permissions(self, user: User) -> list[str]:
        return db_permissions.collect_permissions(user)

    def list_all_permissions(self) -> list[dict[str, object]]:
        return db_permissions.list_all_permissions()

    def to_user_schema(self, user: User) -> UserSchema:
        return db_schema.to_user_schema(_as_db_auth(self), user)

    def build_user_response(
        self,
        user: UserSchema,
        fallback_permissions: list[str] | None = None,
    ) -> UserResponse:
        return db_schema.build_user_response(_as_db_auth(self), user, fallback_permissions)

    def to_api_key_schema(self, key: UserApiKey) -> ApiKey:
        return db_schema.to_api_key_schema(key)

    def to_group_schema(self, group: Group) -> GroupSchema:
        return db_schema.to_group_schema(group)

    def create_group(self, group_create: GroupCreate, tenant_id: str, creator_id: str | None = None) -> GroupSchema:
        return create_group_op(_as_db_auth(self), group_create, tenant_id, creator_id)

    def list_groups(
        self,
        tenant_id: str,
        *,
        actor: AuthActorCaps | None = None,
        q: str | None = None,
    ) -> list[GroupSchema]:
        return list_groups_op(_as_db_auth(self), tenant_id, actor=actor, q=q)

    def get_group(
        self,
        group_id: str,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> GroupSchema | None:
        return get_group_op(_as_db_auth(self), group_id, tenant_id, actor=actor)

    def delete_group(
        self,
        group_id: str,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> bool:
        return delete_group_op(_as_db_auth(self), group_id, tenant_id, actor=actor)

    def update_group(
        self,
        group_id: str,
        group_update: GroupUpdate,
        *,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> GroupSchema | None:
        return update_group_op(_as_db_auth(self), group_id, group_update, tenant_id, actor=actor)

    def update_group_permissions(
        self,
        group_id: str,
        permission_names: list[str],
        *,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> bool:
        return update_group_permissions_op(_as_db_auth(self), group_id, permission_names, tenant_id, actor=actor)

    def update_group_members(
        self,
        group_id: str,
        user_ids: list[str],
        *,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> bool:
        return update_group_members_op(_as_db_auth(self), group_id, user_ids, tenant_id, actor=actor)


class _DatabaseAuthUserMixin(DatabaseAuthServiceState):
    """User CRUD and permission update helpers."""

    def get_user_by_id(
        self,
        user_id: str,
        tenant_id: str | None = None,
        db: Session | None = None,
    ) -> UserSchema | None:
        return get_user_by_id_op(_as_db_auth(self), user_id, tenant_id=tenant_id, db=db)

    def get_user_by_id_in_tenant(self, user_id: str, tenant_id: str) -> UserSchema | None:
        return get_user_by_id_op(_as_db_auth(self), user_id, tenant_id)

    def get_user_by_username(self, username: str) -> UserSchema | None:
        return get_user_by_username_op(_as_db_auth(self), username)

    def create_user(
        self,
        user_create: UserCreate,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> UserSchema:
        return create_user_op(_as_db_auth(self), user_create, tenant_id, actor)

    def list_users(
        self,
        tenant_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        q: str | None = None,
    ) -> list[UserSchema]:
        return list_users_op(_as_db_auth(self), tenant_id, limit=limit, offset=offset, q=q)

    def update_user(
        self,
        user_id: str,
        user_update: UserUpdate,
        *,
        tenant_id: str,
        updater_id: str | None = None,
    ) -> UserSchema | None:
        return update_user_op(_as_db_auth(self), user_id, user_update, tenant_id, updater_id=updater_id)

    def set_grafana_user_id(self, user_id: str, grafana_user_id: int, tenant_id: str) -> bool:
        return set_grafana_user_id_op(user_id, grafana_user_id, tenant_id)

    def delete_user(self, user_id: str, tenant_id: str, deleter_id: str | None = None) -> bool:
        return delete_user_op(_as_db_auth(self), user_id, tenant_id, deleter_id)

    def update_user_permissions(
        self,
        user_id: str,
        permission_names: list[str],
        *,
        tenant_id: str,
        actor: AuthActorCaps | None = None,
    ) -> bool:
        return update_user_permissions_op(
            _as_db_auth(self),
            user_id,
            permission_names,
            tenant_id,
            actor=actor,
        )

    def update_password(self, user_id: str, password_update: UserPasswordUpdate, tenant_id: str) -> bool:
        return update_password_op(_as_db_auth(self), user_id, password_update, tenant_id)


class _DatabaseAuthApiKeyMixin(DatabaseAuthServiceState):
    """API key and share management helpers."""

    def list_api_keys(self, user_id: str, show_hidden: bool = False) -> list[ApiKey]:
        return list_api_keys_op(_as_db_auth(self), user_id, show_hidden)

    def create_api_key(self, user_id: str, tenant_id: str, key_create: ApiKeyCreate) -> ApiKey:
        return create_api_key_op(_as_db_auth(self), user_id, tenant_id, key_create)

    def update_api_key(self, user_id: str, key_id: str, key_update: ApiKeyUpdate) -> ApiKey:
        return update_api_key_op(_as_db_auth(self), user_id, key_id, key_update)

    def set_api_key_hidden(self, user_id: str, key_id: str, hidden: bool = True) -> bool:
        return set_api_key_hidden_op(_as_db_auth(self), user_id, key_id, hidden)

    def regenerate_api_key_otlp_token(self, user_id: str, key_id: str) -> ApiKey:
        return regenerate_api_key_otlp_token_op(_as_db_auth(self), user_id, key_id)

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        return delete_api_key_op(_as_db_auth(self), user_id, key_id)

    def list_api_key_shares(self, owner_user_id: str, tenant_id: str, key_id: str) -> list[JSONDict]:
        return [
            share.model_dump() for share in list_api_key_shares_op(_as_db_auth(self), owner_user_id, tenant_id, key_id)
        ]

    def replace_api_key_shares(
        self,
        owner_user_id: str,
        request: ApiKeyShareReplaceRequest,
    ) -> list[JSONDict]:
        return [
            share.model_dump()
            for share in replace_api_key_shares_op(
                _as_db_auth(self),
                owner_user_id,
                ApiKeyShareReplaceOpsRequest(
                    tenant_id=request.tenant_id,
                    key_id=request.key_id,
                    user_ids=request.user_ids,
                    group_ids=request.group_ids,
                ),
            )
        ]

    def delete_api_key_share(
        self,
        owner_user_id: str,
        tenant_id: str,
        key_id: str,
        *,
        shared_user_id: str,
    ) -> bool:
        return delete_api_key_share_op(
            _as_db_auth(self),
            owner_user_id,
            tenant_id,
            key_id,
            shared_user_id=shared_user_id,
        )

    def validate_otlp_token(self, token: str, *, suppress_errors: bool = True) -> str | None:
        return validate_otlp_token_op(_as_db_auth(self), token, suppress_errors=suppress_errors)

    def backfill_otlp_tokens(self) -> None:
        backfill_otlp_tokens_op(_as_db_auth(self))


class DatabaseAuthService(
    _DatabaseAuthCredentialsMixin,
    _DatabaseAuthMfaMixin,
    _DatabaseAuthAuthFlowMixin,
    _DatabaseAuthPermissionsMixin,
    _DatabaseAuthUserMixin,
    _DatabaseAuthApiKeyMixin,
):
    MFA_SETUP_RESPONSE = "mfa_setup_required"
    MFA_REQUIRED_RESPONSE = "mfa_required"

    def __init__(self) -> None:
        super().__init__()
        self._initialized = False
        self._init_lock = threading.Lock()
        self.logger = logger
        self.oidc_service = OIDCService()
        self._password_op_semaphore = threading.Semaphore(1)
        self._secret_provider: SecretProvider | None = None


def _as_db_auth(svc: DatabaseAuthServiceState) -> DatabaseAuthService:
    """Narrow mixin ``self`` when delegating to operation helpers (mypy)."""
    return cast(DatabaseAuthService, svc)
