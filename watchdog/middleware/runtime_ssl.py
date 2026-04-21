"""
Runtime SSL helpers for the Watchdog service.

Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeSSLOptions:
    ssl_certfile: str
    ssl_keyfile: str

    @classmethod
    def from_env(cls) -> RuntimeSSLOptions | None:
        enabled = os.getenv("SSL_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return None

        certfile = os.getenv("SSL_CERTFILE", "").strip()
        keyfile = os.getenv("SSL_KEYFILE", "").strip()
        if not certfile or not keyfile:
            raise ValueError("SSL_ENABLED=true requires SSL_CERTFILE and SSL_KEYFILE to be set")

        return cls(ssl_certfile=certfile, ssl_keyfile=keyfile)

    def to_uvicorn_kwargs(self) -> dict[str, str]:
        return {
            "ssl_certfile": self.ssl_certfile,
            "ssl_keyfile": self.ssl_keyfile,
        }


def run_uvicorn(app: Any, *, ssl_options: RuntimeSSLOptions | None = None, **kwargs: Any) -> None:
    if ssl_options is not None:
        kwargs.update(ssl_options.to_uvicorn_kwargs())

    import uvicorn  # pylint: disable=import-outside-toplevel

    uvicorn.run(app=app, **kwargs)
