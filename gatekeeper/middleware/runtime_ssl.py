"""
Runtime SSL helpers for the Gateway Auth service.

Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any


@dataclass(frozen=True)
class RuntimeSSLOptions:
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    ssl_ca_certs: str | None = None

    @classmethod
    def from_settings(cls, settings: object) -> RuntimeSSLOptions | None:
        certfile = str(getattr(settings, "SSL_CERTFILE", "")).strip()
        keyfile = str(getattr(settings, "SSL_KEYFILE", "")).strip()
        ca_certs = str(getattr(settings, "SSL_CA_CERTS", "")).strip()

        if not certfile and not keyfile and not ca_certs:
            return None

        if bool(certfile) ^ bool(keyfile):
            raise ValueError("GATEWAY_SSL_CERTFILE and GATEWAY_SSL_KEYFILE must be set together when TLS is enabled")

        return cls(ssl_certfile=certfile or None, ssl_keyfile=keyfile or None, ssl_ca_certs=ca_certs or None)

    def to_uvicorn_kwargs(self) -> dict[str, str]:
        kwargs: dict[str, str] = {}
        if self.ssl_certfile:
            kwargs["ssl_certfile"] = self.ssl_certfile
        if self.ssl_keyfile:
            kwargs["ssl_keyfile"] = self.ssl_keyfile
        if self.ssl_ca_certs:
            kwargs["ssl_ca_certs"] = self.ssl_ca_certs
        return kwargs


def run_uvicorn(app: Any, *, ssl_options: RuntimeSSLOptions | None = None, **kwargs: Any) -> None:
    if ssl_options is not None:
        kwargs.update(ssl_options.to_uvicorn_kwargs())

    uvicorn = import_module("uvicorn")
    uvicorn.run(app=app, **kwargs)
