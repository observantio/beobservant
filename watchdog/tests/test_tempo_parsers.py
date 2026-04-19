"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()
from services.tempo import parsers as tempo_parsers
from models.observability.tempo_models import Span, Trace


def test_parse_attributes_and_span_and_trace():
    attrs = [
        {"key": "k1", "value": {"stringValue": "v1"}},
        {"key": "k2", "value": {"intValue": 42}},
    ]
    parsed = tempo_parsers.parse_attributes(attrs)
    assert parsed["k1"] == "v1"
    assert parsed["k2"] == 42

    span_data = {
        "spanId": "s1",
        "name": "op",
        "startTimeUnixNano": "1000000",
        "endTimeUnixNano": "2000000",
        "attributes": [{"key": "k1", "value": {"stringValue": "v1"}}],
    }
    span = tempo_parsers.parse_span(
        span_data,
        tempo_parsers.SpanParseContext(
            trace_id="t1",
            process_id="proc",
            service_name="svc",
            resource_attrs={"res": "x"},
        ),
    )
    assert isinstance(span, Span)
    assert span.span_id == "s1"
    assert span.trace_id == "t1"
    assert span.service_name == "svc"
    assert span.attributes.get("k1") == "v1"

    trace_data = {
        "batches": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "svcA"}}]},
                "scopeSpans": [{"spans": [span_data]}],
            }
        ]
    }
    trace = tempo_parsers.parse_tempo_trace("t1", trace_data)
    assert isinstance(trace, Trace)
    assert len(trace.spans) == 1
    assert list(trace.processes.keys())[0] == "svcA"


def test_build_summary_trace_returns_trace_or_none():
    t = tempo_parsers.build_summary_trace({})
    assert t is None

    td = {
        "traceID": "tx",
        "startTimeUnixNano": "1000000",
        "durationMs": 5,
        "rootTraceName": "r",
        "rootServiceName": "svc",
    }
    s = tempo_parsers.build_summary_trace(td)
    assert isinstance(s, Trace)
    assert s.spans[0].operation_name == "r"


def test_systrace_stack_component_and_duration_floor():
    assert (
        tempo_parsers._derive_systrace_component_from_line("=> exc_page_fault")
        == "kernel.exc_page_fault"
    )
    assert (
        tempo_parsers._derive_systrace_component_from_line("=>  <000077aab70ac772>")
        == "kernel.userstack"
    )

    span_data = {
        "spanId": "s2",
        "parentSpanId": "p1",
        "name": "systrace.trace.line",
        "startTimeUnixNano": "1000",
        "endTimeUnixNano": "1000",
        "attributes": [{"key": "systrace.trace.line", "value": {"stringValue": "=> do_syscall_64"}}],
    }
    span = tempo_parsers.parse_span(
        span_data,
        tempo_parsers.SpanParseContext(
            trace_id="t2",
            process_id="proc",
            service_name="svc",
            resource_attrs={"service.name": "ojo-systrace"},
        ),
    )
    assert span.duration == 1
    assert span.parent_span_id == "p1"
    assert span.service_name == "kernel.do_syscall_64"


def test_parse_tempo_trace_derives_systrace_line_timing_from_trace_text():
    trace = tempo_parsers.parse_tempo_trace(
        "t3",
        {
            "batches": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "ojo-systrace"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "spanId": "l1",
                                    "parentSpanId": "r1",
                                    "name": "systrace.trace.line",
                                    "startTimeUnixNano": "1000",
                                    "endTimeUnixNano": "1000",
                                    "attributes": [
                                        {
                                            "key": "systrace.trace.line",
                                            "value": {
                                                "stringValue": "task-1 [000] .... 10.000000: foo"
                                            },
                                        }
                                    ],
                                },
                                {
                                    "spanId": "l2",
                                    "parentSpanId": "l1",
                                    "name": "systrace.trace.line",
                                    "startTimeUnixNano": "1000",
                                    "endTimeUnixNano": "1000",
                                    "attributes": [
                                        {
                                            "key": "systrace.trace.line",
                                            "value": {
                                                "stringValue": "task-1 [000] .... 10.000250: bar"
                                            },
                                        }
                                    ],
                                },
                            ]
                        }
                    ],
                }
            ]
        },
    )
    spans_by_id = {s.span_id: s for s in trace.spans}
    assert spans_by_id["l1"].duration >= 200
    assert spans_by_id["l2"].duration >= 1
    assert spans_by_id["l2"].start_time >= spans_by_id["l1"].start_time


def test_parse_tempo_trace_distributes_sparse_systrace_timestamps():
    lines = [
        "task-1 [000] .... 10.000000: <stack trace>",
        "=> first_symbol",
        "=> second_symbol",
        "task-1 [000] .... 10.001000: sys_enter: NR 1",
    ]
    spans = []
    for i, line in enumerate(lines):
        spans.append(
            {
                "spanId": f"p{i+1}",
                "parentSpanId": "root" if i == 0 else f"p{i}",
                "name": "systrace.trace.line",
                "startTimeUnixNano": "1000",
                "endTimeUnixNano": "1000",
                "attributes": [{"key": "systrace.trace.line", "value": {"stringValue": line}}],
            }
        )

    trace = tempo_parsers.parse_tempo_trace(
        "t4",
        {
            "batches": [
                {
                    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "ojo-systrace"}}]},
                    "scopeSpans": [{"spans": spans}],
                }
            ]
        },
    )
    by_id = {s.span_id: s for s in trace.spans}
    assert by_id["p1"].duration >= 300
    assert by_id["p2"].duration >= 300
    assert by_id["p3"].duration >= 300


def test_systrace_explicit_delta_us_attribute_takes_precedence():
    trace = tempo_parsers.parse_tempo_trace(
        "t5",
        {
            "batches": [
                {
                    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "ojo-systrace"}}]},
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "spanId": "x1",
                                    "name": "systrace.trace.line",
                                    "startTimeUnixNano": "1000",
                                    "endTimeUnixNano": "1000",
                                    "attributes": [
                                        {"key": "systrace.trace.line", "value": {"stringValue": "=> do_syscall_64"}},
                                        {"key": "systrace.trace.line.delta_us", "value": {"intValue": 42}},
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )
    assert trace.spans[0].duration == 42
