import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Section from "../Section";
import RcaTabs from "../RcaTabs";
import RcaWarningsPanel from "../RcaWarningsPanel";
import RcaForecastSloPanel from "../RcaForecastSloPanel";
import RcaReportSummary from "../RcaReportSummary";
import RcaRootCauseTable from "../RcaRootCauseTable";
import RcaDistributionStatsPanel from "../RcaDistributionStatsPanel";
import RcaAnomalyPanels from "../RcaAnomalyPanels";
import RcaTopologyPanel from "../RcaTopologyPanel";
import RcaClusterPanel from "../RcaClusterPanel";
import RcaCausalPanel from "../RcaCausalPanel";
import RcaJobQueuePanel from "../RcaJobQueuePanel";

const toastSuccess = vi.fn();
const toastError = vi.fn();
const submitRcaMlWeightFeedback = vi.fn();
const getRcaMlWeights = vi.fn();
const resetRcaMlWeights = vi.fn();
const copyToClipboard = vi.fn();

vi.mock("../../ui", () => ({
  Card: ({ children, className = "" }) => <div className={className}>{children}</div>,
  Badge: ({ children, variant }) => <span data-variant={variant}>{children}</span>,
  Button: ({ children, loading, ...props }) => (
    <button {...props}>{loading ? "loading" : children}</button>
  ),
  Spinner: () => <div>spinner</div>,
  MetricCard: ({ label, value, status }) => (
    <div>
      <span>{label}</span>
      <span>{value}</span>
      <span>{status}</span>
    </div>
  ),
}));

vi.mock("../../../contexts/ToastContext", () => ({
  useToast: () => ({ success: toastSuccess, error: toastError }),
}));

vi.mock("../../../api", () => ({
  submitRcaMlWeightFeedback: (...args) => submitRcaMlWeightFeedback(...args),
  getRcaMlWeights: (...args) => getRcaMlWeights(...args),
  resetRcaMlWeights: (...args) => resetRcaMlWeights(...args),
}));

vi.mock("../../../utils/helpers", () => ({
  copyToClipboard: (...args) => copyToClipboard(...args),
}));

vi.mock("@dagrejs/dagre", () => {
  class Graph {
    constructor() {
      this._nodes = new Map();
    }

    setGraph() {}

    setDefaultEdgeLabel() {}

    setNode(id) {
      this._nodes.set(id, {
        x: 160 + this._nodes.size * 220,
        y: 120 + this._nodes.size * 40,
      });
    }

    setEdge() {}

    node(id) {
      return this._nodes.get(id) || { x: 100, y: 100 };
    }
  }

  return {
    default: {
      graphlib: { Graph },
      layout: vi.fn(),
    },
  };
});

vi.mock("reactflow", () => ({
  __esModule: true,
  default: ({ nodes = [], edges = [], children }) => (
    <div>
      <div data-testid="rf-nodes">{nodes.length}</div>
      <div data-testid="rf-edges">{edges.length}</div>
      {children}
    </div>
  ),
  Background: () => <div>Background</div>,
  Controls: () => <div>Controls</div>,
  MiniMap: () => <div>MiniMap</div>,
  MarkerType: { ArrowClosed: "arrow" },
}));

describe("RCA coverage panel suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    submitRcaMlWeightFeedback.mockResolvedValue({
      updated_weights: { metrics: 0.7, logs: 0.2, traces: 0.1 },
      update_count: 2,
    });
    getRcaMlWeights.mockResolvedValue({
      weights: { metrics: 0.5, logs: 0.3, traces: 0.2 },
      update_count: 3,
    });
    resetRcaMlWeights.mockResolvedValue({
      weights: { metrics: 0.33, logs: 0.33, traces: 0.34 },
      update_count: 0,
    });
    copyToClipboard.mockResolvedValue(true);
  });

  it("covers Section and RcaTabs branches", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <>
        <Section compact className="x">
          compact body
        </Section>
        <RcaTabs
          tabs={[
            { key: "summary", label: "Summary" },
            { key: "causal", label: "Causal", icon: <span>i</span> },
          ]}
          activeTab="summary"
          onChange={onChange}
          sticky
          className="tabs"
        />
      </>,
    );

    fireEvent.click(screen.getByRole("tab", { name: /Causal/i }));
    expect(onChange).toHaveBeenCalledWith("causal");
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    rerender(
      <Section className="y">
        normal body
      </Section>,
    );

    expect(screen.getByText("normal body")).toBeInTheDocument();
  });

  it("covers warnings, forecast and report summary branches", () => {
    const fullReport = {
      summary: "incident summary",
      overall_severity: "high",
      metric_anomalies: [{ id: 1 }],
      root_causes: [{ id: 1 }],
      duration_seconds: 42,
      quality: {
        gating_profile: "very-long-gating-profile-name",
        suppression_counts: { a: 1, b: 2 },
        anomaly_density: { x: 0.4, y: 1.7 },
      },
      forecasts: [
        {
          metric_name: "latency",
          severity: "critical",
          description: "forecast breach",
        },
      ],
      degradation_signals: [{ metric_name: "errors" }],
      analysis_warnings: ["threshold exceeded"],
      change_points: [{ metric_name: "cpu", timestamp: 1710000000 }],
    };

    const { rerender } = render(
      <>
        <RcaWarningsPanel report={null} />
        <RcaForecastSloPanel report={{}} forecast={{}} slo={{}} />
        <RcaReportSummary report={null} />
      </>,
    );

    expect(screen.getByText(/No analysis warnings/i)).toBeInTheDocument();
    expect(screen.getByText(/No budget status returned/i)).toBeInTheDocument();

    rerender(
      <>
        <RcaWarningsPanel report={fullReport} compact />
        <RcaForecastSloPanel
          report={fullReport}
          forecast={{
            results: [
              {
                metric: "latency",
                forecast: { severity: "high", confidence: 0.88 },
                degradation: { trend: "up", severity: "medium" },
              },
            ],
          }}
          slo={{
            burn_alerts: [
              {
                service: "api",
                window_label: "5m",
                burn_rate: 2.5,
                severity: "warning",
              },
            ],
            budget_status: {
              service: "api",
              target_availability: 0.999,
              current_availability: 0.992,
              budget_used_pct: 40,
              remaining_minutes: 144,
            },
          }}
          compact
        />
        <RcaReportSummary report={fullReport} compact />
      </>,
    );

    expect(screen.getByText(/threshold exceeded/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Change Points/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Forecast and SLO/i)).toBeInTheDocument();
    expect(screen.getByText(/Gating Profile/i)).toBeInTheDocument();
  });

  it("covers root cause table, anomaly panel and distribution filter", () => {
    const report = {
      root_causes: [
        {
          hypothesis: "[DB] Connection pool exhausted",
          severity: "high",
          confidence: 0.91,
          recommended_action: "increase pool size",
          corroboration_summary: "spike correlated",
          evidence: ["p95 up", "error logs"],
          contributing_signals: ["latency", "errors"],
          selection_score_components: {
            final_score: 0.9,
            ml_score: 0.8,
            rule_confidence: 0.7,
          },
          suppression_diagnostics: { throttled: false },
        },
      ],
      ranked_causes: [
        {
          root_cause: { hypothesis: "[DB] Connection pool exhausted" },
          final_score: 0.944,
          ml_score: 0.72,
        },
      ],
      metric_anomalies: [
        {
          metric_name: "errors",
          timestamp: 1710000000,
          value: 10,
          z_score: 3,
          mad_score: 2,
          iqr_score: 2,
          tukey_outlier_class: "extreme_high",
          severity: "critical",
        },
      ],
      log_bursts: [
        {
          window_start: 1710000000,
          window_end: 1710000060,
          rate_per_second: 3,
          baseline_rate: 1,
          ratio: 3,
          severity: "high",
        },
      ],
      log_patterns: [
        {
          pattern: "timeout",
          count: 12,
          rate_per_minute: 2.4,
          severity: "medium",
        },
      ],
      service_latency: [
        {
          service: "api",
          operation: "GET /x",
          p95_ms: 120,
          p99_ms: 300,
          apdex: 0.92,
        },
      ],
      error_propagation: [
        {
          source_service: "api",
          affected_services: ["db"],
          error_rate: 0.8,
          severity: "high",
        },
      ],
      metric_series_statistics: [
        {
          series_key: "sum(rate(errors[5m]))::errors_total",
          metric_name: "errors_total",
          sample_count: 10,
          mean: 10,
          std: 1.2,
          coefficient_of_variation: 0.12,
          mad: 0.3,
          min: 8,
          q1: 9,
          median: 10,
          q3: 11,
          max: 12,
          iqr: 2,
          skewness: 0.5,
          kurtosis: 1.1,
        },
      ],
    };

    const { rerender } = render(
      <>
        <RcaRootCauseTable report={{ root_causes: [] }} />
        <RcaAnomalyPanels report={{}} compact />
        <RcaDistributionStatsPanel report={{ metric_series_statistics: [] }} />
      </>,
    );

    expect(screen.getByText(/No root causes identified/i)).toBeInTheDocument();
    expect(screen.getByText(/No metric anomalies/i)).toBeInTheDocument();
    expect(screen.getByText(/No statistics for this report/i)).toBeInTheDocument();

    rerender(
      <>
        <RcaRootCauseTable report={report} compact />
        <RcaAnomalyPanels report={report} />
        <RcaDistributionStatsPanel report={report} compact />
      </>,
    );

    expect(screen.getByText(/Connection pool exhausted/i)).toBeInTheDocument();
    expect(screen.getByText(/increase pool size/i)).toBeInTheDocument();
    expect(screen.getByText(/Anomalies and Signals/i)).toBeInTheDocument();

    const filterInput = screen.getByPlaceholderText(/Filter by metric or query/i);
    fireEvent.change(filterInput, { target: { value: "missing" } });
    expect(screen.getByText(/No series match your filter/i)).toBeInTheDocument();

    fireEvent.change(filterInput, { target: { value: "errors" } });
    expect(screen.getByText(/errors_total/i)).toBeInTheDocument();
  });

  it("covers topology empty and populated branches", () => {
    const { rerender } = render(<RcaTopologyPanel topology={null} />);
    expect(screen.getByText(/Topology data not available/i)).toBeInTheDocument();

    rerender(
      <RcaTopologyPanel
        topology={{
          root_service: "api",
          affected_downstream: ["db"],
          upstream_roots: ["ingress"],
          all_services: ["cache"],
        }}
        compact
      />,
    );

    expect(screen.getByText(/Topology and Blast Radius/i)).toBeInTheDocument();
    expect(screen.getByTestId("rf-nodes")).toHaveTextContent("4");
    expect(screen.getByTestId("rf-edges")).toHaveTextContent("3");
  });

  it("covers cluster panel empty, chart and selection details", () => {
    const { rerender } = render(<RcaClusterPanel report={{ anomaly_clusters: [] }} />);
    expect(screen.getByText(/No clusters were produced/i)).toBeInTheDocument();

    rerender(
      <RcaClusterPanel
        report={{
          anomaly_clusters: [
            {
              cluster_id: "A",
              size: 3,
              centroid_timestamp: 1710000000,
              centroid_value: 12.3,
              metric_names: ["latency", "errors"],
            },
            {
              cluster_id: "B",
              size: 6,
              centroid_timestamp: 1710000100,
              centroid_value: 8.1,
              metric_names: Array.from({ length: 26 }, (_, i) => `m${i}`),
            },
          ],
        }}
      />,
    );

    expect(screen.getByLabelText(/Anomaly cluster bubble chart/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("B"));
    expect(screen.getByText(/Affected Metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/\+2 more/i)).toBeInTheDocument();
  });

  it("covers causal panel feedback branches and queue actions", async () => {
    const onSelectJob = vi.fn();
    const onDelete = vi.fn();
    const onView = vi.fn();

    const { rerender } = render(
      <>
        <RcaCausalPanel
          correlate={{ correlated_events: [], log_metric_links: [] }}
          granger={{ causal_pairs: [] }}
          bayesian={{ posteriors: [] }}
          mlWeights={{ weights: { metrics: 0.5, logs: 0.3, traces: 0.2 }, update_count: 1 }}
          deployments={[]}
        />
        <RcaJobQueuePanel
          jobs={[]}
          loading
          selectedJobId=""
          onSelectJob={onSelectJob}
          onDelete={onDelete}
          onView={onView}
          deletingReport={false}
          canDelete
        />
      </>,
    );

    expect(screen.getByText("spinner")).toBeInTheDocument();

    rerender(
      <>
        <RcaCausalPanel
          correlate={{
            correlated_events: [
              {
                window_start: 1710000000,
                confidence: 0.88,
                signal_count: 3,
                metric_anomaly_count: 2,
                log_burst_count: 1,
              },
            ],
            log_metric_links: [{ id: 1 }],
          }}
          granger={{ causal_pairs: [{ cause_metric: "a", effect_metric: "b", strength: 0.9 }] }}
          bayesian={{ posteriors: [{ category: "db", posterior: 0.8, prior: 0.2 }] }}
          mlWeights={{ weights: { metrics: 0.5, logs: 0.3, traces: 0.2 }, update_count: 1 }}
          deployments={{ items: [{ service: "api", version: "1.2.3", timestamp: 1710000000 }] }}
          compact
        />
        <RcaJobQueuePanel
          jobs={[
            {
              job_id: "job-12345678",
              report_id: "rep-1",
              status: "completed",
              created_at: "2024-01-01T00:00:00Z",
              summary_preview: "summary",
            },
          ]}
          loading={false}
          selectedJobId="job-12345678"
          onSelectJob={onSelectJob}
          onDelete={onDelete}
          onView={onView}
          deletingReport={false}
          canDelete
        />
      </>,
    );

    fireEvent.click(screen.getByLabelText(/Mark metrics as correct/i));
    await waitFor(() => {
      expect(submitRcaMlWeightFeedback).toHaveBeenCalledWith("metrics", true);
    });

    fireEvent.click(screen.getByRole("button", { name: /Reset Weights/i }));
    await waitFor(() => {
      expect(resetRcaMlWeights).toHaveBeenCalled();
      expect(toastSuccess).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByText(/job-1234/i));
    expect(onSelectJob).toHaveBeenCalledWith("job-12345678");

    fireEvent.click(screen.getByLabelText("Copy Report ID"));
    await waitFor(() => {
      expect(copyToClipboard).toHaveBeenCalledWith("rep-1");
      expect(toastSuccess).toHaveBeenCalledWith("Report ID copied");
    });

    copyToClipboard.mockResolvedValueOnce(false);
    fireEvent.click(screen.getByLabelText("Copy Report ID"));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Failed to copy report ID");
    });

    fireEvent.click(screen.getByLabelText("View"));
    expect(onView).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Delete"));
    expect(onDelete).toHaveBeenCalled();
  });

  it("covers causal feedback fallback refresh path and queue empty state", async () => {
    submitRcaMlWeightFeedback.mockResolvedValueOnce({ update_count: 10 });

    const { rerender } = render(
      <RcaCausalPanel
        correlate={{ correlated_events: [], log_metric_links: [] }}
        granger={{ causal_pairs: [] }}
        bayesian={{ posteriors: [] }}
        mlWeights={{ weights: { metrics: 0.4 }, update_count: 1 }}
        deployments={{ events: [] }}
      />,
    );

    fireEvent.click(screen.getByLabelText(/Mark logs as incorrect/i));
    await waitFor(() => {
      expect(submitRcaMlWeightFeedback).toHaveBeenCalledWith("logs", false);
      expect(getRcaMlWeights).toHaveBeenCalled();
    });

    submitRcaMlWeightFeedback.mockRejectedValueOnce(new Error("submit failed"));
    fireEvent.click(screen.getByLabelText(/Mark traces as correct/i));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("submit failed");
    });

    resetRcaMlWeights.mockRejectedValueOnce(new Error("reset failed"));
    fireEvent.click(screen.getByRole("button", { name: /Reset Weights/i }));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("reset failed");
    });

    rerender(
      <RcaJobQueuePanel
        jobs={[]}
        loading={false}
        selectedJobId=""
        onSelectJob={vi.fn()}
        deletingReport={false}
        canDelete={false}
      />,
    );

    expect(screen.getByText(/currently no RCA jobs available/i)).toBeInTheDocument();
  });
});
