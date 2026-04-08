"""
Tempo parsers for processing trace responses from Tempo, providing functions to extract and normalize trace and span
data into application models.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from typing import List, Optional

from models.observability.tempo_models import Span, SpanAttribute, Trace
from custom_types.json import JSONDict

SERVICE_NAME_KEY = "service.name"
SERVICE_ALIAS_KEY = "service"
OTLP_VALUE_TYPES = ("stringValue", "intValue", "boolValue", "doubleValue")


def _json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _json_dict_list(value: object) -> List[JSONDict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _derive_systrace_component_from_line(line: object) -> Optional[str]:
    if not isinstance(line, str):
        return None
    text = line.strip()
    if not text:
        return None

    token = text.split()[0] if text.split() else ""
    if not token:
        return None
    prefix = token.split(":", 1)[0]

    # Linux scheduler traces commonly emit task names like: name-12345
    # Keep the task stem and normalize to a service-like component key.
    stem = prefix
    if "-" in prefix:
        maybe_name, maybe_pid = prefix.rsplit("-", 1)
        if maybe_name and maybe_pid.isdigit():
            stem = maybe_name

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


def parse_attributes(attrs: List[JSONDict]) -> JSONDict:
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


def parse_span(
    span_data: JSONDict,
    trace_id: str,
    process_id: str,
    service_name: Optional[str],
    resource_attrs: Optional[JSONDict] = None,
) -> Span:
    attr_map = parse_attributes(_json_dict_list(span_data.get("attributes", [])))

    if resource_attrs:
        for k, v in resource_attrs.items():
            attr_map.setdefault(k, v)

    operation_name = span_data.get("name")
    derived_systrace_component = _derive_systrace_component_from_line(attr_map.get("systrace.trace.line"))
    is_systrace_line = isinstance(operation_name, str) and operation_name == "systrace.trace.line"

    preferred_service_name: object | None = (
        derived_systrace_component if is_systrace_line and derived_systrace_component else None
    )

    span_service_name_value = (
        preferred_service_name
        or attr_map.get(SERVICE_NAME_KEY)
        or attr_map.get(SERVICE_ALIAS_KEY)
        or attr_map.get("service_name")
        or service_name
        or "unknown"
    )
    span_service_name = (
        span_service_name_value
        if isinstance(span_service_name_value, str)
        else str(span_service_name_value)
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
    parent_span_id_value = span_data.get("parentSpanId")
    parent_span_id = parent_span_id_value if isinstance(parent_span_id_value, str) and parent_span_id_value else None

    span_id = span_data.get("spanId")
    return Span.model_validate(
        {
            "spanID": span_id if isinstance(span_id, str) else "",
            "traceID": trace_id,
            "parentSpanID": parent_span_id,
            "operationName": operation_name if isinstance(operation_name, str) else "",
            "startTime": start_time,
            "duration": duration,
            "tags": [{"key": t.key, "value": t.value} for t in tags],
            "serviceName": span_service_name,
            "attributes": attr_map,
            "processID": str(span_service_name or process_id),
            "warnings": None,
        }
    )


def parse_tempo_trace(trace_id: str, data: JSONDict) -> Trace:
    spans: List[Span] = []
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
                parse_span(s, trace_id, process_id, service_name, resource_attrs)
                for s in _json_dict_list(scope.get("spans"))
            )

    return Trace.model_validate({"traceID": trace_id, "spans": spans, "processes": processes})


def build_summary_trace(trace_data: JSONDict) -> Optional[Trace]:
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
