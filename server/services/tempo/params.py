"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import Any, Dict
from models.observability.tempo_models import TraceQuery

_SERVICE_NAME_KEY = "service.name"


def build_search_params(query: TraceQuery) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": query.limit}
    tags = {}
    if query.service:
        tags[_SERVICE_NAME_KEY] = query.service
    if query.operation:
        tags["name"] = query.operation
    if query.tags:
        tags.update(query.tags)
    if tags:
        params["tags"] = " && ".join(f'{k}="{v}"' for k, v in tags.items())
    if query.start:
        params["start"] = int(query.start) // 1_000_000
    if query.end:
        params["end"] = int(query.end) // 1_000_000
    if query.min_duration:
        params["minDuration"] = query.min_duration
    if query.max_duration:
        params["maxDuration"] = query.max_duration
    return params
