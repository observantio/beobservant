"""
Helpers for tests that monkeypatch NotifierProxyService.forward / ResolverProxyService.request_json.

Production passes a single positional dataclass; stubs should accept that argument and unpack
fields the older **kwargs-style fakes relied on.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from typing import Any


def unpack_notifier_forward(fwd: Any) -> dict[str, Any]:
    return {
        "request": fwd.request,
        "upstream_path": fwd.upstream_path,
        "current_user": fwd.current_user,
        "require_api_key": fwd.require_api_key,
        "audit_action": fwd.audit_action,
        "correlation_id": fwd.correlation_id,
        "request_body": fwd.request_body,
    }


def unpack_resolver_json_request(req: Any) -> dict[str, Any]:
    return {
        "method": req.method,
        "upstream_path": req.upstream_path,
        "current_user": req.current_user,
        "tenant_id": req.tenant_id,
        "payload": req.payload,
        "params": req.params,
        "audit_action": req.audit_action,
        "correlation_id": req.correlation_id,
        "cache_ttl_seconds": req.cache_ttl_seconds,
    }
