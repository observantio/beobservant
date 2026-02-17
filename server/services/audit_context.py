from contextvars import ContextVar
from typing import Optional

_audit_ip: ContextVar[Optional[str]] = ContextVar("audit_ip", default=None)
_audit_user_agent: ContextVar[Optional[str]] = ContextVar("audit_user_agent", default=None)


def set_request_audit_context(ip_address: Optional[str], user_agent: Optional[str]):
    token_ip = _audit_ip.set(ip_address)
    token_ua = _audit_user_agent.set(user_agent)
    return token_ip, token_ua


def reset_request_audit_context(tokens) -> None:
    token_ip, token_ua = tokens
    _audit_ip.reset(token_ip)
    _audit_user_agent.reset(token_ua)


def get_request_audit_context() -> tuple[Optional[str], Optional[str]]:
    return _audit_ip.get(), _audit_user_agent.get()
