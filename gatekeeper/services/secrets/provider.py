"""
Provider interfaces and implementations for secrets management.

Defines a `SecretProvider` protocol and a simple `EnvSecretProvider`
implementation backed by process environment variables. This keeps secret
lookup pluggable while preserving a minimal default implementation.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import os
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, key: str) -> str | None: ...
    def get_many(self, keys: list[str]) -> dict[str, str | None]: ...


class EnvSecretProvider:
    def get(self, key: str) -> str | None:
        return os.environ.get(key) or None

    def get_many(self, keys: list[str]) -> dict[str, str | None]:
        return {k: self.get(k) for k in keys}
