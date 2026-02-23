from tests._env import ensure_test_env
ensure_test_env()

import asyncio
from engine.fetcher import fetch_metrics


class DummyMetrics:
    def __init__(self):
        self.queried = []

    async def query_range(self, query, start, end, step):
        self.queried.append((query, start, end, step))
        # always return an empty result set to simulate an empty TSDB
        return {"data": {"result": []}}

    async def scrape(self):
        # simulate a Prometheus exposition string with a couple of metrics
        return """
# HELP process_cpu_seconds_total CPU time
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 123.5
some_other_metric 7
"""


class DummyProvider:
    def __init__(self):
        self.metrics = DummyMetrics()

    async def query_metrics(self, query, start, end, step):
        # delegate to the underlying metrics connector
        return await self.metrics.query_range(query, start, end, step)


def test_fetch_metrics_fallback_from_scrape():
    provider = DummyProvider()
    queries = [
        "rate(process_cpu_seconds_total[5m])",
        "process_resident_memory_bytes",
    ]
    # using arbitrary start/end values
    results = asyncio.run(fetch_metrics(provider, queries, start=10, end=20, step="60"))

    # should have produced at least one synthetic series for cpu
    assert results, "fetch_metrics should return a non-empty list when scrape fallback succeeds"
    # inspect the first response for the cpu metric
    cpu_resp = next((r for r in results if r.get("data", {}).get("result") and r["data"]["result"][0]["metric"]["__name__"] == "process_cpu_seconds_total"), None)
    assert cpu_resp is not None, "cpu metric should appear in fallback response"
    vals = cpu_resp["data"]["result"][0]["values"]
    # two points (start + end) with the same scraped value
    assert len(vals) == 2
    assert vals[0][1] == vals[1][1] == 123.5


def test_mimir_connector_scrape(monkeypatch):
    """Verify that the connector requests the /metrics path with tenant header."""
    import httpx
    from connectors.mimir import MimirConnector

    captured = {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured['url'] = url
            captured['headers'] = headers

            class R:
                status_code = 200
                text = "foo 1\n"

                def raise_for_status(self):
                    return None

            return R()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    conn = MimirConnector("http://mimir:9009", "mytenant")
    scraped = asyncio.run(conn.scrape())
    assert "foo" in scraped
    assert captured['url'].endswith("/metrics")
    assert captured['headers']['X-Scope-OrgID'] == "mytenant"
