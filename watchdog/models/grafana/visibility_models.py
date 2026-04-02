"""
Shared Grafana visibility model definitions.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from enum import Enum


class Visibility(str, Enum):
    PRIVATE = "private"
    GROUP = "group"
    TENANT = "tenant"
    PUBLIC = "public"
