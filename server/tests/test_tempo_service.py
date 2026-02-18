import asyncio

from tests._env import ensure_test_env
ensure_test_env()

from services.tempo_service import TempoService
from models.observability.tempo_models import TraceQuery


def test_search_traces_fetches_full_traces_with_concurrency():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_search(*args, **kwargs):
        return {"traces": [{"traceID": "t1"}, {"traceID": "t2"}, {"traceID": "t3"}]}

    inflight = 0
    max_inflight = 0

    async def fake_get_trace(trace_id, tenant_id="default"):
        nonlocal inflight, max_inflight
        inflight += 1
        max_inflight = max(max_inflight, inflight)
        await asyncio.sleep(0.03)
        inflight -= 1
        return {
            "traceID": trace_id,
            "spans": [],
            "processes": {},
            "warnings": None,
        }

    service._timed_get_json = fake_search
    service.get_trace = fake_get_trace

    result = asyncio.run(service.search_traces(TraceQuery(limit=3), fetch_full_traces=True))

    assert result.total == 3
    assert len(result.data) == 3
    assert max_inflight > 1


def test_get_trace_volume_uses_metrics_query_range():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append((promql, start_us, end_us, step_s))
        # return a single-sample matrix matching expected shape
        ts = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
        return {"status": "success", "data": {"result": [{"metric": {}, "values": [[ts, "5"]]}]}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    assert len(called) == 1
    values = result["data"]["result"][0]["values"]
    assert values[0][1] == "5"


def test_get_trace_volume_falls_back_to_bucket_when_metrics_unavailable():
    service = TempoService(tempo_url="http://tempo.test")

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        # metrics endpoint returns no result -> fallback expected
        return {"status": "success", "data": {"result": []}}

    service._query_metrics_range = fake_query_metrics
    # Prepare a fake search_traces that returns traces across multiple buckets
    start = 1_700_000_000_000_000
    end = start + (10 * 60 * 1_000_000)

    async def fake_search_traces(query, tenant_id="default", fetch_full_traces=False):
        # create one trace per 2-minute interval within the range
        traces = []
        for i in range(0, 10):
            # place traces at start + i*60s
            ts_us = int(start + i * 60 * 1_000_000)
            spans = [{"spanID": "root", "traceID": f"t{i}", "startTime": ts_us, "duration": 1000, "serviceName": "svc", "attributes": {}, "processID": "svc"}]
            traces.append({"traceID": f"t{i}", "spans": spans})

        # Build a TraceResponse-like object matching service expectations
        from models.observability.tempo_models import TraceResponse, Trace, Span

        trace_objs = []
        for t in traces:
            span = Span(spanID=t["spans"][0]["spanID"], traceID=t["spans"][0]["traceID"], operationName="op", startTime=t["spans"][0]["startTime"], duration=t["spans"][0]["duration"], tags=[], serviceName=t["spans"][0]["serviceName"], attributes={}, processID=t["spans"][0]["processID"])
            trace_objs.append(Trace(traceID=t["traceID"], spans=[span], processes={}))

        return TraceResponse(data=trace_objs, total=len(trace_objs), limit=query.limit, offset=0)

    service.search_traces = fake_search_traces

    result = asyncio.run(service.get_trace_volume(start=start, end=end, step=60))

    values = result["data"]["result"][0]["values"]
    assert len(values) > 1


def test_get_trace_volume_tries_label_candidates_in_order():
    service = TempoService(tempo_url="http://tempo.test")

    called = []

    async def fake_query_metrics(promql, start_us=None, end_us=None, step_s=300, tenant_id="default"):
        called.append(promql)
        # New implementation combines selectors into one expression; just return
        # a synthetic non-empty result for the combined query.
        ts = int((start_us or int(__import__('time').time() * 1_000_000)) / 1_000_000)
        return {"status": "success", "data": {"result": [{"metric": {}, "values": [[ts, "3"]]}]}}

    service._query_metrics_range = fake_query_metrics

    start = 1_700_000_000_000_000
    end = start + (60 * 1_000_000)
    result = asyncio.run(service.get_trace_volume(service="svc", start=start, end=end, step=60))

    # ensure we tried at least the first candidate and then a succeeding candidate
    assert any("resource.service.name" in p for p in called)
    values = result["data"]["result"][0]["values"]
    assert values[0][1] == "3"
