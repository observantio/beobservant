"""Vault-backed SecretProvider implementation.

- Uses `hvac` (imported lazily) so the codebase can remain runnable when
  `VAULT_ENABLED=false` in dev.
- Supports KV v1 and KV v2 mounts and a small in-memory cache.
"""
from __future__ import annotations

import time
from typing import Dict, Optional


class VaultClientError(RuntimeError):
    pass


class VaultSecretProvider:
    def __init__(
        self,
        address: str,
        token: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
        prefix: str = "secret",
        kv_version: int = 2,
        timeout: float = 2.0,
        cacert: Optional[str] = None,
        cache_ttl: float = 30.0,
    ) -> None:
        try:
            import hvac
        except Exception as exc:  # pragma: no cover - import error handled in runtime
            raise VaultClientError("hvac library is required for VaultSecretProvider") from exc

        if not address:
            raise VaultClientError("VAULT_ADDR is required to use VaultSecretProvider")

        self._client = hvac.Client(url=address, timeout=timeout, verify=cacert or True)
        self._prefix = prefix.strip("/")
        self._kv_version = int(kv_version)
        self._cache: Dict[str, tuple[float, Optional[str]]] = {}
        self._cache_ttl = float(cache_ttl)

        # auth: token preferred, otherwise AppRole
        if token:
            self._client.token = token
        elif role_id and secret_id:
            auth = self._client.auth.approle.login(role_id=role_id, secret_id=secret_id)
            self._client.token = auth["auth"]["client_token"]
        else:
            raise VaultClientError("Vault auth not configured (provide VAULT_TOKEN or AppRole credentials)")

        if not self._client.is_authenticated():
            raise VaultClientError("Vault authentication failed")

    def _from_cache(self, key: str) -> Optional[str]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        return value

    def _to_cache(self, key: str, value: Optional[str]) -> None:
        self._cache[key] = (time.time(), value)

    def get(self, key: str) -> Optional[str]:
        # Fast-path from cache
        cached = self._from_cache(key)
        if cached is not None:
            return cached

        try:
            # KV v2 mount (most common): read_secret_version
            if self._kv_version == 2:
                # mount_point is the prefix (e.g. "secret"); path is the key name
                resp = self._client.secrets.kv.v2.read_secret_version(path=key, mount_point=self._prefix)
                payload = resp.get("data", {}).get("data", {})
            else:
                # KV v1
                full_path = f"{self._prefix}/{key}" if self._prefix else key
                resp = self._client.secrets.kv.read_secret(path=full_path)
                payload = resp.get("data", {})
        except Exception:
            # treat missing / inaccessible as absent rather than crash the process
            self._to_cache(key, None)
            return None

        # common extraction heuristics
        if not payload:
            self._to_cache(key, None)
            return None

        if "value" in payload and isinstance(payload["value"], (str, int, float)):
            val = str(payload["value"])
        elif key in payload and isinstance(payload[key], (str, int, float)):
            val = str(payload[key])
        elif len(payload) == 1:
            # pick the single value
            val = str(next(iter(payload.values())))
        else:
            # nothing obvious to return
            self._to_cache(key, None)
            return None

        self._to_cache(key, val)
        return val

    # keep a `get_many`-like helper for callers that want multiple secrets
    def get_many(self, keys: list[str]) -> Dict[str, Optional[str]]:
        return {k: self.get(k) for k in keys}
