"""
Package exposing the Resolver service, which provides AI-driven insights and automation for observability data.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
"""

from services.aiops.helpers import correlation_id, inject_tenant

__all__ = ["correlation_id", "inject_tenant"]
