"""
PromQL query construction logic for Tempo trace metrics to get volume

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import List, Optional


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_promql_selector(service: Optional[str]) -> List[str]:
    if not service:
        return ["{}"]
    svc = _escape(service)
    return list(dict.fromkeys([
        f'{{resource.service.name="{svc}"}}',
        f'{{service_name="{svc}"}}',
        f'{{service="{svc}"}}',
        f'{{service.name="{svc}"}}',
    ]))


def build_count_promql(service: Optional[str], range_s: int) -> str:
    primary = build_promql_selector(service)[0]
    return f"sum(count_over_time({primary}[{range_s}s]))"