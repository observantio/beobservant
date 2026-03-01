"""
Package initialization for gateway auth service secrets module.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from  services.secrets.provider import build_secret_provider

__all__ = ["build_secret_provider"]
