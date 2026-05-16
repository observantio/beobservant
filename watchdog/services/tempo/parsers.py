"""
Tempo parsers for processing trace responses from Tempo, providing functions to extract and normalize trace and span
data into application models.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from dataclasses import dataclass
from itertools import pairwise

from custom_types.json import JSONDict
from models.observability.tempo_models import Span, SpanAttribute, Trace

SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
OTLP_VALUE_TYPES = ("stringValue", "intValue", "boolValue", "doubleValue")
SYSTRACE_LINE_OP = "systrace.trace.line"
SYSTRACE_LINE_ATTR = "systrace.trace.line"
SYSTRACE_LINE_DELTA_US_ATTR = "systrace.trace.line.delta_us"


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _json_dict_list(value: object) -> list[JSONDict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            parsed = 0
    else:
        parsed = 0
    return parsed


def _optional_positive_int(value: object) -> int | None:
    as_int = _int_value(value)
    return as_int if as_int > 0 else None


def _derive_systrace_component_from_line(line: object) -> str | None:
    if not isinstance(line, str):
        return None
    text = line.strip()
    if not text:
        return None

    stem: str | None = None
    if text.startswith("=>"):
        rest = text[2:].strip()
        symbol = (rest.split()[0] if rest.split() else "").strip()
        if symbol:
            stem = "userstack" if symbol.startswith("<") and symbol.endswith(">") else symbol
    else:
        token = text.split()[0] if text.split() else ""
        if token:
            prefix = token.split(":", 1)[0]
            stem = prefix
            if "-" in prefix:
                maybe_name, maybe_pid = prefix.rsplit("-", 1)
                if maybe_name and maybe_pid.isdigit():
                    stem = maybe_name
    return _normalize_component_stem(stem)


def _normalize_component_stem(stem: str | None) -> str | None:
    if not stem:
        return None
    normalized_chars: list[str] = []
    prev_dot = False
    for ch in stem:
        if ch.isalnum() or ch in "-_":
            normalized_chars.append(ch.lower())
            prev_dot = False
            continue
        if ch in "/:.":
            if normalized_chars and not prev_dot:
                normalized_chars.append(".")
                prev_dot = True
            continue

    while normalized_chars and normalized_chars[-1] == ".":
        normalized_chars.pop()
    normalized = "".join(normalized_chars)
    if not normalized:
        return None
    return f"kernel.{normalized}"


def _parse_systrace_line_seconds(line: object) -> float | None:
    if not isinstance(line, str):
        return None
    for part in line.split():
        candidate = part[:-1] if part.endswith(":") else part
        if "." not in candidate:
            continue
        if not any(ch.isdigit() for ch in candidate):
            continue
        if all(ch.isdigit() or ch == "." for ch in candidate):
            try:
                return float(candidate)
            except ValueError:
                return None
    return None


def _apply_systrace_line_timing(spans: list[Span]) -> None:
    line_indexes: list[int] = []
    line_seconds: list[float | None] = []

    for i, span in enumerate(spans):
        if span.operation_name != SYSTRACE_LINE_OP:
            continue
        attrs = span.attributes or {}
        ts = _parse_systrace_line_seconds(attrs.get(SYSTRACE_LINE_ATTR))
        line_indexes.append(i)
        line_seconds.append(ts)

    if not line_indexes:
        return
    if all((spans[i].duration or 0) > 1 for i in line_indexes):
        return

    derived_us: list[int] = [1] * len(line_indexes)
    known_positions = [i for i, ts in enumerate(line_seconds) if ts is not None]

    for left_pos, right_pos in pairwise(known_positions):
        left_ts = line_seconds[left_pos]
        right_ts = line_seconds[right_pos]
        if left_ts is None or right_ts is None:
            continue
        width = right_pos - left_pos
        if width <= 0:
            continue
        delta_us = round((right_ts - left_ts) * 1_000_000)
        per_line_us = max(1, round(delta_us / width)) if delta_us > 0 else 1
        for pos in range(left_pos, right_pos):
            derived_us[pos] = per_line_us

    for pos, span_index in enumerate(line_indexes):
        span = spans[span_index]
        if span.duration <= 0 or span.duration == 1:
            span.duration = derived_us[pos]

    first_start = spans[line_indexes[0]].start_time
    if all(spans[i].start_time == first_start for i in line_indexes):
        offset_us = 0
        for i in line_indexes:
            spans[i].start_time = first_start + offset_us
            offset_us += max(1, int(spans[i].duration or 1))


def parse_attributes(attrs: list[JSONDict]) -> JSONDict:
    parsed: JSONDict = {}
    for attr in attrs or []:
        key = attr.get("key", "")
        if not isinstance(key, str) or not key:
            continue
        value = _json_dict(attr.get("value", {}))
        for val_type in OTLP_VALUE_TYPES:
            if val_type in value:
                parsed[key] = value[val_type]
                break
    return parsed


@dataclass(frozen=True, slots=True)
class SpanParseContext:
    trace_id: str
    process_id: str
    service_name: str | None
    resource_attrs: JSONDict | None = None


def parse_span(
    span_data: JSONDict,
    parse_context: SpanParseContext,
) -> Span:
    attr_map = parse_attributes(_json_dict_list(span_data.get("attributes", [])))

    if parse_context.resource_attrs:
        for k, v in parse_context.resource_attrs.items():
            attr_map.setdefault(k, v)

    operation_name = span_data.get("name")
    derived_systrace_component = _derive_systrace_component_from_line(attr_map.get(SYSTRACE_LINE_ATTR))
    is_systrace_line = isinstance(operation_name, str) and operation_name == SYSTRACE_LINE_OP

    preferred_service_name: object | None = (
        derived_systrace_component if is_systrace_line and derived_systrace_component else None
    )

    span_service_name_value = (
        preferred_service_name
        or attr_map.get(SERVICE_NAME_KEY)
        or attr_map.get(SERVICE_ALIAS_KEY)
        or attr_map.get("service_name")
        or parse_context.service_name
        or "unknown"
    )
    span_service_name = (
        span_service_name_value if isinstance(span_service_name_value, str) else str(span_service_name_value)
    )

    if span_service_name and (SERVICE_NAME_KEY not in attr_map or preferred_service_name is not None):
        attr_map[SERVICE_NAME_KEY] = span_service_name

    tags = [SpanAttribute(key=k, value=v) for k, v in attr_map.items()]

    start_ns = _int_value(span_data.get("startTimeUnixNano"))
    end_ns = _int_value(span_data.get("endTimeUnixNano"))
    start_time = start_ns // 1000
    end_time = end_ns // 1000
    duration = end_time - start_time
    # Preserve very short positive spans that would otherwise be truncated to 0us.
    if duration == 0 and end_ns > start_ns:
        duration = 1
    # Systrace line spans are very short and can collapse to 0us at source resolution.
    if is_systrace_line and duration <= 0:
        duration = 1
    explicit_delta_us = _optional_positive_int(attr_map.get(SYSTRACE_LINE_DELTA_US_ATTR))
    if is_systrace_line and explicit_delta_us is not None:
        duration = explicit_delta_us
    parent_span_id_value = span_data.get("parentSpanId")
    parent_span_id = parent_span_id_value if isinstance(parent_span_id_value, str) and parent_span_id_value else None

    span_id = span_data.get("spanId")
    return Span.model_validate(
        {
            "spanID": span_id if isinstance(span_id, str) else "",
            "traceID": parse_context.trace_id,
            "parentSpanID": parent_span_id,
            "operationName": operation_name if isinstance(operation_name, str) else "",
            "startTime": start_time,
            "duration": duration,
            "tags": [{"key": t.key, "value": t.value} for t in tags],
            "serviceName": span_service_name,
            "attributes": attr_map,
            "processID": str(span_service_name or parse_context.process_id),
            "warnings": None,
        }
    )


def parse_tempo_trace(trace_id: str, data: JSONDict) -> Trace:
    spans: list[Span] = []
    processes: JSONDict = {}

    for batch in _json_dict_list(data.get("batches")):
        resource = _json_dict(batch.get("resource", {}))
        resource_attrs = parse_attributes(_json_dict_list(resource.get("attributes", [])))
        service_name_value = (
            resource_attrs.get(SERVICE_NAME_KEY)
            or resource_attrs.get(SERVICE_ALIAS_KEY)
            or resource_attrs.get("serviceName")
            or "unknown"
        )
        service_name = service_name_value if isinstance(service_name_value, str) else str(service_name_value)
        process_id = str(service_name)
        processes[process_id] = {
            "serviceName": service_name,
            "resource": resource,
            "attributes": resource_attrs,
        }
        for scope in _json_dict_list(batch.get("scopeSpans")):
            spans.extend(
                parse_span(
                    s,
                    SpanParseContext(
                        trace_id=trace_id,
                        process_id=process_id,
                        service_name=service_name,
                        resource_attrs=resource_attrs,
                    ),
                )
                for s in _json_dict_list(scope.get("spans"))
            )

    _apply_systrace_line_timing(spans)
    return Trace.model_validate({"traceID": trace_id, "spans": spans, "processes": processes})


def build_summary_trace(trace_data: JSONDict) -> Trace | None:
    trace_id_value = trace_data.get("traceID")
    if not isinstance(trace_id_value, str) or not trace_id_value:
        return None
    trace_id = trace_id_value

    try:
        start_ns = _int_value(trace_data["startTimeUnixNano"]) if trace_data.get("startTimeUnixNano") else None
    except KeyError:
        start_ns = None

    try:
        duration_ms = _int_value(trace_data["durationMs"]) if trace_data.get("durationMs") is not None else None
    except KeyError:
        duration_ms = None

    service_name_value = trace_data.get("rootServiceName") or trace_data.get("rootService") or "unknown"
    service_name = service_name_value if isinstance(service_name_value, str) else "unknown"

    root_trace_name = trace_data.get("rootTraceName")

    summary_span: JSONDict = {
        "spanID": "root",
        "traceID": trace_id,
        "parentSpanID": None,
        "operationName": root_trace_name if isinstance(root_trace_name, str) else "",
        "startTime": int(start_ns // 1000) if start_ns else 0,
        "duration": int(duration_ms * 1000) if duration_ms is not None else 0,
        "tags": [],
        "serviceName": service_name,
        "attributes": {},
        "processID": service_name,
        "warnings": ["Trace summary only"],
    }

    return Trace.model_validate(
        {
            "traceID": trace_id,
            "spans": [summary_span],
            "processes": {},
            "warnings": ["Trace summary only"],
        }
    )
