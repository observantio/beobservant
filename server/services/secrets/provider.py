"""SecretProvider interface + environment-backed provider.

Pluggable abstraction so `Config` can read secrets from Vault (or other
stores) while keeping `os.getenv` fallback for rollout.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Protocol


class SecretProvider(Protocol):
    def get(self, key: str) -> Optional[str]:
        """Return the secret value for `key` or None if not present."""

    def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        return {k: self.get(k) for k in keys}


class EnvSecretProvider:
    """Simple provider that reads from process environment."""

    def get(self, key: str) -> Optional[str]:
        val = os.getenv(key)
        return val if val is not None and val != "" else None

    def get_many(self, keys: List[str]) -> Dict[str, Optional[str]]:
        return {k: self.get(k) for k in keys}
