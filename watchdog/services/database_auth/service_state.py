"""
Instance-attribute shape shared by ``DatabaseAuthService`` and its mixins.

Helper modules type the ``service`` parameter as this class so mixin ``self`` is
assignable without invalid ``self: DatabaseAuthService`` annotations on mixin
definitions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from services.auth.oidc_service import OIDCService
from services.secrets.provider import SecretProvider


class DatabaseAuthServiceState:
    """Base for auth service mixins; documents attributes set in ``DatabaseAuthService.__init__``."""

    logger: logging.Logger
    oidc_service: OIDCService
    _initialized: bool
    _init_lock: threading.Lock
    _password_op_semaphore: threading.Semaphore
    _secret_provider: Optional[SecretProvider]
