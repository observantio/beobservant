"""
Utility functions for AIOps services.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from custom_types.json import JSONDict
from fastapi import Request


def inject_tenant(payload: JSONDict | None, tenant_id: str) -> JSONDict:
    data: JSONDict = dict(payload or {})
    data["tenant_id"] = tenant_id
    return data


def correlation_id(request: Request) -> str | None:
    return request.headers.get("x-correlation-id")
