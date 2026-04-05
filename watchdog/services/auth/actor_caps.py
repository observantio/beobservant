"""Shared actor/capability bundle for auth mutations (pylint-friendly arity)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True, slots=True)
class AuthActorCaps:
    """Who is performing the operation and their resolved role/permission hints."""

    user_id: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_superuser: bool = False
