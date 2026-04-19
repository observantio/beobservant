"""
Composed access/auth router split by concern.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from .shared import router
from . import api_keys
from . import audit
from . import authentication
from . import groups
from . import mfa
from . import users

__all__ = [
    "router",
    "api_keys",
    "audit",
    "authentication",
    "groups",
    "mfa",
    "users",
]
