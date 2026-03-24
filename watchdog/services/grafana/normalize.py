"""
Normalization logic for Grafana "next" paths.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations
from typing import Optional
from urllib.parse import parse_qsl, urlencode

def normalize_grafana_next_path(path: Optional[str]) -> str:
    candidate = (path or "/dashboards").strip() or "/dashboards"
    if candidate.startswith(("http://", "https://", "//")):
        return "/dashboards"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if candidate.startswith("/grafana"):
        candidate = candidate[len("/grafana"):] or "/dashboards"
    if "?" not in candidate:
        return candidate

    path_part, query_part = candidate.split("?", 1)
    if not query_part:
        return path_part
    if "#" in query_part:
        query_only, fragment = query_part.split("#", 1)
    else:
        query_only, fragment = query_part, ""

    preserved_pairs = [
        (key, value)
        for key, value in parse_qsl(query_only, keep_blank_values=True)
        if key.lower() != "orgid"
    ]
    rebuilt_query = urlencode(preserved_pairs, doseq=True)
    normalized = f"{path_part}?{rebuilt_query}" if rebuilt_query else path_part
    if fragment:
        normalized = f"{normalized}#{fragment}"
    return normalized
