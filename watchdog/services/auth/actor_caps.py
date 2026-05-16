"""
Shared actor/capability bundle for auth mutations (pylint-friendly arity).

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthActorCaps:
    """Who is performing the operation and their resolved role/permission hints."""

    user_id: str | None = None
    role: str | None = None
    permissions: list[str] | None = None
    is_superuser: bool = False
