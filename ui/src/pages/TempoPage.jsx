import {
  useEffect,
  useState,
  useMemo,
  useCallback,
  useRef,
  lazy,
  Suspense,
} from "react";
import { useAutoRefresh } from "../hooks";
import PageHeader from "../components/ui/PageHeader";
import AutoRefreshControl from "../components/ui/AutoRefreshControl";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import { fetchTempoServices, searchTraces, getTrace } from "../api";
import { Card, Button, Select, Input, Spinner } from "../components/ui";
import ServiceGraph from "../components/tempo/ServiceGraph";
const TraceResults = lazy(() => import("../components/tempo/TraceResults"));
const TraceTimeline = lazy(() => import("../components/tempo/TraceTimeline"));
import { formatDuration } from "../utils/formatters";
import { getServiceName, hasSpanError } from "../utils/helpers";
import {
  TIME_RANGES,
  DEFAULT_DURATION_RANGE,
  TRACE_STATUS_OPTIONS,
  REFRESH_INTERVALS,
  TRACE_LIMIT_OPTIONS,
  DEFAULT_QUERY_LIMITS,
} from "../utils/constants";
import HelpTooltip from "../components/HelpTooltip";
import { discoverServices, computeTraceStats } from "../utils/tempoTraceUtils";

const TRACE_PAGE_SIZE = 20;

function normalizeServiceNames(values) {
  const set = new Set();
  (Array.isArray(values) ? values : []).forEach((value) => {
    const text = String(value || "").trim();
    if (!text) return;
    if (text.toLowerCase() === "unknown") return;
    set.add(text);
  });
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function getTraceIdentity(trace) {
  return trace?.traceID || trace?.traceId || trace?.id || "";
}

function getTraceSummary(trace) {
  const spans = Array.isArray(trace?.spans) ? trace.spans : [];
  const rootSpan =
    spans.find((span) => !span.parentSpanId && !span.parentSpanID) || spans[0];
  const duration = Number(rootSpan?.duration || 0);
  const traceId = getTraceIdentity(trace);
  const rootServiceName = rootSpan ? getServiceName(rootSpan) : "unknown";
  const hasError = spans.some(hasSpanError);

  return {
    traceId,
    rootSpan,
    duration,
    rootServiceName,
    hasError,
    spanCount: spans.length,
  };
}

export default function TempoPage() {
  const [services, setServices] = useState([]);
  const [service, setService] = useState("");
  const [operation, setOperation] = useState("");
  const [traceIdSearch, setTraceIdSearch] = useState("");
  const [durationRange, setDurationRange] = useState([
    DEFAULT_DURATION_RANGE.min,
    DEFAULT_DURATION_RANGE.max,
  ]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [timeRange, setTimeRange] = useState(60);
  const [traces, setTraces] = useState(null);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [selectedTraceIds, setSelectedTraceIds] = useState(new Set());
  const [graphTraces, setGraphTraces] = useState([]);
  const [graphLoading, setGraphLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState("list");
  const [tracePage, setTracePage] = useState(1);
  const [pageSize, setPageSize] = useState(TRACE_PAGE_SIZE);
  const [searchLimit, setSearchLimit] = useState(
    DEFAULT_QUERY_LIMITS.traces || TRACE_PAGE_SIZE,
  );
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(30);
  const searchRunIdRef = useRef(0);
  const activeSearchControllerRef = useRef(null);
  const servicesLoadControllerRef = useRef(null);
  const previousActiveApiKeyIdRef = useRef(null);

  const { user, isAuthenticated, loading: authLoading } = useAuth();
  const toast = useToast();
  const activeApiKeyId = useMemo(() => {
    const keys = user?.api_keys || [];
    const active = keys.find((k) => k.is_enabled) || keys.find((k) => k.is_default);
    return active?.id || active?.key || user?.org_id || "";
  }, [user]);

  const pruneSelectedTraceIds = useCallback((invalidIds) => {
    if (!invalidIds || invalidIds.size === 0) return;

    setSelectedTraceIds((prev) => {
      const next = new Set(prev);
      invalidIds.forEach((id) => next.delete(id));
      return next;
    });
  }, []);

  const loadServices = useCallback(async () => {
    if (servicesLoadControllerRef.current) {
      servicesLoadControllerRef.current.abort();
    }
    const controller = new AbortController();
    servicesLoadControllerRef.current = controller;
    try {
      const data = await fetchTempoServices({ signal: controller.signal });
      setServices(normalizeServiceNames(data));
    } catch (error) {
      if (error?.name === "AbortError" || error?.code === "REQUEST_ABORTED") {
        return;
      }
      setServices([]);
    } finally {
      if (servicesLoadControllerRef.current === controller) {
        servicesLoadControllerRef.current = null;
      }
    }
  }, []);

  // Keep filters/options synced with the active API key (tenant context).
  useEffect(() => {
    if (!isAuthenticated || authLoading) {
      previousActiveApiKeyIdRef.current = null;
      return;
    }
    const previous = previousActiveApiKeyIdRef.current;
    const changed = previous !== null && previous !== activeApiKeyId;
    previousActiveApiKeyIdRef.current = activeApiKeyId;

    if (changed) {
      if (activeSearchControllerRef.current) {
        activeSearchControllerRef.current.abort();
      }
      setService("");
      setOperation("");
      setTraceIdSearch("");
      setTraces(null);
      setSelectedTrace(null);
      setSelectedTraceIds(new Set());
      setGraphTraces([]);
      setViewMode("list");
      setTracePage(1);
    }
    loadServices();
  }, [isAuthenticated, authLoading, activeApiKeyId, loadServices]);

  useAutoRefresh(() => onSearch(), refreshInterval * 1000, autoRefresh);

  useEffect(
    () => () => {
      if (activeSearchControllerRef.current) {
        activeSearchControllerRef.current.abort();
      }
      if (servicesLoadControllerRef.current) {
        servicesLoadControllerRef.current.abort();
      }
    },
    [],
  );

  const discoveredServiceOptions = useMemo(
    () => normalizeServiceNames(discoverServices(traces?.data || [])),
    [traces],
  );

  const serviceOptions = useMemo(() => {
    if (discoveredServiceOptions.length > 0) return discoveredServiceOptions;
    return normalizeServiceNames(services);
  }, [discoveredServiceOptions, services]);

  useEffect(() => {
    if (!service) return;
    if (!serviceOptions.includes(service)) {
      setService("");
    }
  }, [service, serviceOptions]);

  const handleTraceClick = useCallback(
    async (traceId, { silent = false, signal } = {}) => {
      if (viewMode !== "list") {
        setViewMode("list");
      }

      try {
        const trace = await getTrace(traceId, { signal });
        if (trace?.spans) {
          setSelectedTrace({
            ...trace,
            spans: trace.spans.map((s) => ({
              ...s,
              endTime: s.startTime + (s.duration || 0),
            })),
          });
        } else {
          if (!silent) toast.error("Trace data is incomplete — no spans returned");
        }
        return true;
      } catch (e) {
        if (e?.name === "AbortError" || e?.code === "REQUEST_ABORTED") {
          return false;
        }
        if (e.status === 404) {
          pruneSelectedTraceIds(new Set([traceId]));
          setSelectedTrace(null);
          if (!silent) {
            toast.error(`Trace not found: ${traceId}`);
          }
        } else {
          if (!silent) toast.error(`Failed to load trace: ${e?.message || e}`);
        }
        return false;
      }
    },
    [pruneSelectedTraceIds, toast, viewMode],
  );

  function toggleSelectTrace(traceId, checked) {
    setSelectedTraceIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(traceId);
      else next.delete(traceId);
      return next;
    });
  }

  async function showSelectedOnMap() {
    if (!selectedTraceIds || selectedTraceIds.size === 0) {
      toast && toast.error && toast.error("No traces selected");
      return;
    }

    setViewMode("graph");
    setGraphLoading(true);
    setGraphTraces([]);

    const ids = Array.from(selectedTraceIds);
    const concurrency = Math.min(8, ids.length);
    const queue = ids.slice();
    const results = [];
    const invalidIds = new Set();

    const worker = async () => {
      while (queue.length) {
        const id = queue.shift();
        try {
          const t = await getTrace(id);
          if (t && t.spans && t.spans.length) {
            results.push(t);
          } else {
            invalidIds.add(id);
          }
        } catch (e) {
          if (e?.status === 404) {
            invalidIds.add(id);
          }
        }
      }
    };

    try {
      await Promise.all(
        Array.from({ length: concurrency }).map(() => worker()),
      );
      pruneSelectedTraceIds(invalidIds);
      if (results.length === 0) {
        setGraphTraces([]);
        return;
      }
      setGraphTraces(results);
    } finally {
      setGraphLoading(false);
    }
  }

  const showTraceOnMap = useCallback(
    async (traceId) => {
      if (!traceId) return;

      setViewMode("graph");
      setGraphLoading(true);
      setGraphTraces([]);
      setSelectedTraceIds(new Set([traceId]));

      try {
        const t = await getTrace(traceId);
        if (t && t.spans && t.spans.length) {
          setGraphTraces([t]);
        } else {
          toast && toast.error && toast.error("Failed to load trace for map");
        }
      } catch (e) {
        toast &&
          toast.error &&
          toast.error(`Failed to load trace: ${e.message || e}`);
      } finally {
        setGraphLoading(false);
      }
    },
    [toast],
  );

  async function onSearch(e) {
    if (e) e.preventDefault();

    if (viewMode !== "list") {
      setViewMode("list");
    }

    const runId = searchRunIdRef.current + 1;
    searchRunIdRef.current = runId;
    if (activeSearchControllerRef.current) {
      activeSearchControllerRef.current.abort();
    }
    const controller = new AbortController();
    activeSearchControllerRef.current = controller;

    if (traceIdSearch.trim()) {
      setLoading(true);
      try {
        await handleTraceClick(traceIdSearch.trim(), { signal: controller.signal });
      } finally {
        if (runId === searchRunIdRef.current) {
          setLoading(false);
        }
      }
      return;
    }

    setLoading(true);
    try {
      const end = Date.now() * 1000;
      const start = end - timeRange * 60 * 1000000;
      const searchParams = {
        service,
        operation,
        minDuration: `${Math.floor(Math.max(0, durationRange[0]) / 1000000)}ms`,
        maxDuration: `${Math.floor(durationRange[1] / 1000000)}ms`,
        start: Math.floor(start),
        end: Math.floor(end),
        limit: searchLimit,
        fetchFull: false,
        signal: controller.signal,
      };
      const res = await searchTraces(searchParams);
      if (runId !== searchRunIdRef.current) return;

      setTraces(res);
      setTracePage(1);
      const resultIds = new Set(
        (res?.data || [])
          .map((t) => t?.traceID || t?.traceId || t?.id)
          .filter(Boolean),
      );
      pruneSelectedTraceIds(
        new Set([...selectedTraceIds].filter((id) => !resultIds.has(id))),
      );
      const selectedId =
        selectedTrace?.traceId || selectedTrace?.traceID || selectedTrace?.id;
      if (selectedId && !resultIds.has(selectedId)) {
        setSelectedTrace(null);
      }

    } catch (e) {
      if (e?.name === "AbortError" || e?.code === "REQUEST_ABORTED") return;
      toast.error(e?.message || "Failed to search traces");
    } finally {
      if (runId === searchRunIdRef.current) {
        setLoading(false);
      }
    }
  }

  const getTraceStartTime = useCallback((trace) => {
    const spans = Array.isArray(trace?.spans) ? trace.spans : [];
    const rootSpan =
      spans.find((span) => !span.parentSpanId && !span.parentSpanID) || spans[0];
    return Number(rootSpan?.startTime || 0);
  }, []);

  const filteredTraces = useMemo(() => {
    if (!traces?.data) return [];
    const selectedService = String(service || "").trim().toLowerCase();
    const selectedOperation = String(operation || "").trim().toLowerCase();
    const minDurationUs = Math.max(0, Number(durationRange?.[0] || 0));
    const maxDurationUs = Math.max(minDurationUs, Number(durationRange?.[1] || 0));

    const traceDurationUs = (trace) => {
      const spans = Array.isArray(trace?.spans) ? trace.spans : [];
      if (!spans.length) return 0;
      // Summary traces expose the full duration on the synthetic root span.
      if (spans.length === 1 && Number.isFinite(Number(spans[0]?.duration))) {
        return Math.max(0, Number(spans[0].duration));
      }
      return spans.reduce((max, span) => {
        const d = Number(span?.duration || 0);
        return Number.isFinite(d) ? Math.max(max, d) : max;
      }, 0);
    };

    return traces.data
      .filter((trace) => {
        const spans = Array.isArray(trace?.spans) ? trace.spans : [];
        if (!spans.length) return false;

        if (selectedService) {
          const hasService = spans.some(
            (span) =>
              String(getServiceName(span) || "")
                .trim()
                .toLowerCase() === selectedService,
          );
          if (!hasService) return false;
        }

        if (selectedOperation) {
          const hasOperation = spans.some((span) =>
            String(span?.operationName || "")
              .toLowerCase()
              .includes(selectedOperation),
          );
          if (!hasOperation) return false;
        }

        const durationUs = traceDurationUs(trace);
        if (durationUs < minDurationUs || durationUs > maxDurationUs) {
          return false;
        }

        if (statusFilter === "error") return trace.spans.some(hasSpanError);
        if (statusFilter === "ok") return !trace.spans.some(hasSpanError);
        return true;
      })
      .sort((a, b) => getTraceStartTime(b) - getTraceStartTime(a));
  }, [traces, statusFilter, service, operation, durationRange, getTraceStartTime]);

  const traceStats = useMemo(() => {
    return computeTraceStats(filteredTraces);
  }, [filteredTraces]);

  const pagedTraces = useMemo(() => {
    const start = (tracePage - 1) * pageSize;
    return filteredTraces.slice(start, start + pageSize);
  }, [filteredTraces, tracePage, pageSize]);

  const totalPages = Math.max(1, Math.ceil(filteredTraces.length / pageSize));

  const graphSuggestions = useMemo(() => {
    return filteredTraces.slice(0, 8).map((trace) => ({
      trace,
      ...getTraceSummary(trace),
    }));
  }, [filteredTraces]);

  useEffect(() => {
    if (tracePage > totalPages) {
      setTracePage(totalPages);
    }
  }, [totalPages, tracePage]);

  function clearFilters() {
    setService("");
    setOperation("");
    setTraceIdSearch("");
    setDurationRange([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max]);
    setStatusFilter("all");
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        icon="timeline"
        title="Tracing"
        subtitle="Search and analyze distributed traces across your services"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            {[
              { key: "list", icon: "list", label: "List View" },
              { key: "graph", icon: "hub", label: "Dependency Map" },
            ].map((v) => (
              <button
                key={v.key}
                onClick={() => setViewMode(v.key)}
                title={v.label}
                className={`px-3 py-2 rounded-lg transition-colors flex items-center gap-1.5 text-sm ${
                  viewMode === v.key
                    ? "bg-sre-primary text-white shadow-sm"
                    : "text-sre-text-muted hover:text-sre-text hover:bg-sre-surface"
                }`}
              >
                <span className="material-icons text-sm">{v.icon}</span>
                <span className="hidden sm:inline">{v.label}</span>
              </button>
            ))}
            <HelpTooltip text="Switch between list view (detailed trace information) and dependency map (service relationships)." />
          </div>

          <AutoRefreshControl
            enabled={autoRefresh}
            onToggle={setAutoRefresh}
            interval={refreshInterval}
            onIntervalChange={setRefreshInterval}
            intervalOptions={REFRESH_INTERVALS.slice(0, 4)}
          />
        </div>
      </PageHeader>

      {/* Stats Bar */}
      {traceStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            {
              label: "Total Traces",
              value: Number(traceStats.total).toLocaleString(),
              color: "text-sre-text",
            },
            {
              label: "Avg Duration",
              value: formatDuration(traceStats.avgDuration),
              color: "text-sre-text",
            },
            {
              label: "Max Duration",
              value: formatDuration(traceStats.maxDuration),
              color: "text-sre-text",
            },
            {
              label: "Error Rate",
              value: `${traceStats.errorRate.toFixed(1)}%`,
              color:
                traceStats.errorRate > 5 ? "text-red-500" : "text-green-500",
            },
            {
              label: "Errors",
              value: traceStats.errorCount,
              color:
                traceStats.errorCount > 0 ? "text-red-500" : "text-green-500",
            },
          ].map((stat) => (
            <Card
              key={stat.label}
              className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm"
            >
              <div className="text-sre-text-muted text-xs mb-1">
                {stat.label}
              </div>
              <div className={`text-2xl font-bold ${stat.color}`}>
                {stat.value}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Search Form */}
      <Card
        title="Search Traces"
        subtitle="Query traces by service, operation, duration, or trace ID"
        className="mb-6"
      >
        <form onSubmit={onSearch} className="space-y-4">
          {/* Trace ID quick search */}
          <div className="flex gap-2 items-end pb-3 border-b border-sre-border">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Input
                  size="sm"
                  label="Trace ID (direct lookup)"
                  value={traceIdSearch}
                  onChange={(e) => setTraceIdSearch(e.target.value)}
                  placeholder="Paste a trace ID to jump directly to it"
                  className="flex-1 px-2 py-0.5 text-sm"
                />
                <HelpTooltip text="Enter a specific trace ID to view that trace directly, bypassing the search filters." />
              </div>
            </div>
            <Button
              size="sm"
              type="submit"
              loading={loading && !!traceIdSearch.trim()}
              disabled={!traceIdSearch.trim() && loading}
            >
              <span className="material-icons text-xs mr-1">search</span> Lookup
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Service"
                  value={service}
                  onChange={(e) => setService(e.target.value)}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  <option value="">All Services</option>
                  {serviceOptions.length > 0 ? (
                    serviceOptions.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))
                  ) : (
                    <option disabled>No services discovered yet</option>
                  )}
                </Select>
                <HelpTooltip text="Filter traces by the service that initiated them. Services are automatically discovered from your traces." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Input
                  size="sm"
                  label="Operation"
                  value={operation}
                  onChange={(e) => setOperation(e.target.value)}
                  placeholder="HTTP GET /api"
                  className="flex-1 px-2 py-0.5 text-sm"
                />
                <HelpTooltip text="Filter traces by operation name, such as HTTP methods or function names." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Time Range"
                  value={timeRange}
                  onChange={(e) => setTimeRange(Number(e.target.value))}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  {TIME_RANGES.map((tr) => (
                    <option key={tr.value} value={tr.value}>
                      {tr.label}
                    </option>
                  ))}
                </Select>
                <HelpTooltip text="Select how far back to search for traces. Larger ranges may take longer to query." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  {TRACE_STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
                <HelpTooltip text="Filter traces by their status: all, successful, or those containing errors." />
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-medium text-sre-text">
                <span className="material-icons text-xs mr-1 align-middle">
                  schedule
                </span>
                Duration Range: {formatDuration(durationRange[0])} –{" "}
                {formatDuration(durationRange[1])}
              </label>
              <HelpTooltip text="Filter traces by their total duration using the sliders below." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-sre-text-muted">Minimum</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[0]}
                  onChange={(e) => {
                    const newMin = Math.max(0, Number(e.target.value));
                    setDurationRange([
                      newMin,
                      Math.max(durationRange[1], newMin + 10000000),
                    ]);
                  }}
                  className="tempo-range-slider w-full h-1.5 bg-sre-surface rounded-lg border border-sre-border/60 appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
              <div>
                <label className="text-xs text-sre-text-muted">Maximum</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[1]}
                  onChange={(e) => {
                    const newMax = Math.max(0, Number(e.target.value));
                    setDurationRange([
                      Math.max(
                        0,
                        Math.min(durationRange[0], newMax - 10000000),
                      ),
                      newMax,
                    ]);
                  }}
                  className="tempo-range-slider w-full h-1.5 bg-sre-surface rounded-lg border border-sre-border/60 appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
            </div>
            <div className="flex justify-between text-xs text-sre-text-muted mt-0.5">
              <span>0ms</span>
              <button
                type="button"
                onClick={() =>
                  setDurationRange([
                    DEFAULT_DURATION_RANGE.min,
                    DEFAULT_DURATION_RANGE.max,
                  ])
                }
                className="text-sre-primary hover:underline text-xs"
              >
                Reset range
              </button>
              <span>10s</span>
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-2">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={clearFilters}
              >
                Clear Filters
              </Button>
              <HelpTooltip text="Reset all search filters and duration range to their default values." />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-sre-text-muted">
                Search Limit
              </label>
              <select
                value={searchLimit}
                onChange={(e) => {
                  setSearchLimit(Number(e.target.value));
                  setTracePage(1);
                }}
                className="text-xs px-2 py-1 bg-sre-surface border border-sre-border rounded text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
              >
                {TRACE_LIMIT_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <label className="text-xs text-sre-text-muted">Page Size</label>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setTracePage(1);
                }}
                className="text-xs px-2 py-1 bg-sre-surface border border-sre-border rounded text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
              >
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <Button
                type="submit"
                size="sm"
                loading={loading && !traceIdSearch.trim()}
              >
                <span className="material-icons text-xs mr-1">search</span>{" "}
                Search Traces
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {/* Service Dependency Graph */}
      {viewMode === "graph" && (
        <Card
          title="Dependency Map"
          subtitle={
            graphLoading
              ? "Building dependency map for selected traces…"
              : graphTraces.length
                ? `Showing relationships between ${new Set(graphTraces.flatMap((t) => t.spans?.map((s) => getServiceName(s)).filter(Boolean) || [])).size} services (selected) Note that systraces are not traces but dependencies`
                : filteredTraces.length
                  ? "Select one of the traces below to build the dependency map"
                  : "Run a search to see the dependency map"
          }
        >
          {graphLoading ? (
            <div className="py-24 flex flex-col items-center">
              <Spinner size="lg" />
              <p className="text-sre-text-muted mt-4">
                Building dependency map…
              </p>
            </div>
          ) : graphTraces.length > 0 ? (
            <ServiceGraph traces={graphTraces} />
          ) : filteredTraces.length > 0 ? (
            <div className="rounded-2xl border border-sre-border bg-sre-bg-alt/70 p-5">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-sre-text">
                    Pick a Trace to Inspect
                  </h3>
                  <p className="mt-1 max-w-2xl text-sm text-sre-text-muted">
                    Dependency maps need a full trace. Choose one of the traces
                    from your current search and we&apos;ll open its service map here.
                  </p>
                </div>
                <div className="rounded-full border border-sre-border bg-sre-surface px-3 py-1 text-xs font-medium text-sre-text-muted">
                  {filteredTraces.length} possible trace
                  {filteredTraces.length === 1 ? "" : "s"}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {graphSuggestions.map(
                  ({
                    trace,
                    traceId,
                    rootServiceName,
                    duration,
                    hasError,
                    spanCount,
                    rootSpan,
                  }) => (
                    <button
                      key={traceId}
                      type="button"
                      onClick={() => showTraceOnMap(traceId)}
                      className="rounded-xl border border-sre-border bg-sre-surface/70 p-4 text-left transition-all hover:border-sre-primary/40 hover:bg-sre-surface hover:shadow-md"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-mono text-sm font-semibold text-sre-text">
                            {traceId}
                          </div>
                          <div className="mt-1 text-xs text-sre-text-muted">
                            {rootServiceName}
                            {rootSpan?.operationName
                              ? ` · ${rootSpan.operationName}`
                              : ""}
                          </div>
                        </div>
                        <span
                          className={`material-icons text-lg ${
                            hasError ? "text-red-500" : "text-sre-primary"
                          }`}
                          aria-hidden
                        >
                          {hasError ? "error" : "hub"}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-sre-text-muted">
                        <span className="rounded-full border border-sre-border bg-sre-bg px-2 py-1">
                          {formatDuration(duration)}
                        </span>
                        <span className="rounded-full border border-sre-border bg-sre-bg px-2 py-1">
                          {spanCount} span{spanCount === 1 ? "" : "s"}
                        </span>
                        <span className="rounded-full border border-sre-border bg-sre-bg px-2 py-1">
                          {hasError ? "Contains errors" : "Healthy trace"}
                        </span>
                      </div>

                      <div className="mt-3 text-xs font-medium text-sre-primary">
                        Open on dependency map
                      </div>
                    </button>
                  ),
                )}
              </div>

              {filteredTraces.length > graphSuggestions.length && (
                <p className="mt-4 text-xs text-sre-text-muted">
                  Showing {graphSuggestions.length} suggestions from your current
                  search. Refine the query in list view to narrow this down further.
                </p>
              )}
            </div>
          ) : (
            <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
              <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
                hub
              </span>
              <h3 className="text-xl font-semibold text-sre-text mb-2">
                No Traces Found
              </h3>
              <p className="text-sre-text-muted mb-6 text-sm max-w-md mx-auto">
                Try adjusting your search criteria, expanding the time range, or
                selecting traces from the list and clicking "Show selected on
                Map".
              </p>
            </div>
          )}
        </Card>
      )}

      {/* Trace Results */}
      {viewMode === "list" && (
        <Card
          title="Trace Results"
          subtitle={
            filteredTraces.length
              ? `Found ${filteredTraces.length} trace${filteredTraces.length === 1 ? "" : "s"}`
              : "Run a search to see results"
          }
        >
          <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border" />
          <Suspense
            fallback={
              <div className="py-12 flex flex-col items-center">
                <Spinner size="lg" />
                <p className="text-sre-text-muted mt-4">Searching traces...</p>
              </div>
            }
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="text-xs text-sre-primary hover:underline"
                  onClick={() => {
                    const ids = pagedTraces
                      .map((t) => t.traceID || t.traceId)
                      .filter(Boolean);
                    setSelectedTraceIds(new Set(ids));
                  }}
                >
                  Select visible
                </button>
                <button
                  type="button"
                  className="text-xs text-sre-primary hover:underline"
                  onClick={() => setSelectedTraceIds(new Set())}
                >
                  Clear selection
                </button>
                <div className="text-xs text-sre-text-muted">
                  {selectedTraceIds.size} selected
                </div>
              </div>
              <div>
                <button
                  type="button"
                  className="btn btn-sm bg-sre-primary text-white px-3 py-1 rounded text-xs"
                  onClick={showSelectedOnMap}
                  disabled={selectedTraceIds.size === 0}
                >
                  Show selected on Map
                </button>
              </div>
            </div>
            <TraceResults
              traces={pagedTraces}
              loading={loading}
              handleTraceClick={handleTraceClick}
              selectedIds={selectedTraceIds}
              onToggleSelect={toggleSelectTrace}
              onShowOnMap={showTraceOnMap}
            />
            {filteredTraces.length > pageSize && (
              <div className="mt-4 flex items-center justify-between text-xs text-sre-text-muted">
                <span>
                  Page {tracePage} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={tracePage <= 1}
                    onClick={() => setTracePage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={tracePage >= totalPages}
                    onClick={() =>
                      setTracePage((p) => Math.min(totalPages, p + 1))
                    }
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </Suspense>
        </Card>
      )}

      {/* Trace Detail Modal */}
      {selectedTrace && (
        <TraceTimeline
          trace={selectedTrace}
          onClose={() => setSelectedTrace(null)}
          onCopyTraceId={() => {
            const id =
              selectedTrace.traceId ||
              selectedTrace.traceID ||
              selectedTrace.id ||
              "";
            navigator.clipboard.writeText(id).then(
              () => toast.success("Trace ID copied"),
              () => toast.error("Failed to copy"),
            );
          }}
        />
      )}
    </div>
  );
}
