import { getServiceName, hasSpanError } from "./helpers";

export function discoverServices(traces) {
  const discovered = new Set();
  traces.forEach((trace) => {
    (trace.spans || []).forEach((span) => {
      const name = getServiceName(span);
      if (name && name !== "unknown") discovered.add(name);
    });
  });
  return Array.from(discovered).sort((a, b) => a.localeCompare(b));
}

export function computeTraceStats(filteredTraces) {
  if (!filteredTraces.length) return null;
  const durationsUs = filteredTraces.map((trace) => {
    if (trace.spans?.length) {
      const rootSpan =
        trace.spans.find((span) => !span.parentSpanId && !span.parentSpanID) ||
        trace.spans[0];
      return rootSpan?.duration || 0;
    }

    if (trace.durationMs !== undefined && trace.durationMs !== null) {
      return Number(trace.durationMs) * 1000;
    }
    if (trace.duration_us !== undefined && trace.duration_us !== null) {
      return Number(trace.duration_us);
    }

    return 0;
  });

  const errorCount = filteredTraces.filter((trace) =>
    trace.spans?.some(hasSpanError),
  ).length;
  const validDurationsUs = durationsUs.filter((duration) => duration > 0);
  const avgDurationUs = validDurationsUs.length
    ? validDurationsUs.reduce((acc, duration) => acc + duration, 0) /
      validDurationsUs.length
    : 0;
  const maxDurationUs = validDurationsUs.length
    ? Math.max(...validDurationsUs)
    : 0;
  const minDurationUs = validDurationsUs.length
    ? Math.min(...validDurationsUs)
    : 0;
  const errorRate = filteredTraces.length
    ? (errorCount / filteredTraces.length) * 100
    : 0;

  return {
    total: filteredTraces.length,
    avgDuration: Math.round(avgDurationUs * 1000),
    maxDuration: Math.round(maxDurationUs * 1000),
    minDuration: Math.round(minDurationUs * 1000),
    errorRate,
    errorCount,
  };
}
