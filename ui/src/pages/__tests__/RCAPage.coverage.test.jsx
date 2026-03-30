import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getRcaAnalyzeConfigTemplate = vi.fn();
const createJob = vi.fn();
const refreshJobs = vi.fn();
const deleteReportById = vi.fn();
const removeJobByReportId = vi.fn();
const setSelectedJobId = vi.fn();
const reloadReport = vi.fn();

const jobsState = {
  jobs: [],
  loadingJobs: false,
  creatingJob: false,
  deletingReport: false,
  selectedJobId: null,
  selectedJob: null,
};

const reportState = {
  loadingPrimaryReport: false,
  loadingInsights: false,
  loadingReport: false,
  reportError: null,
  reportErrorStatus: null,
  report: null,
  reportMeta: null,
  insights: {},
  insightErrors: {},
  hasReport: false,
};

vi.mock("../../api", () => ({
  getRcaAnalyzeConfigTemplate: (...args) => getRcaAnalyzeConfigTemplate(...args),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", api_keys: [{ key: "org-1", is_default: true }] } }),
}));

vi.mock("../../hooks", async () => {
  const React = await vi.importActual("react");
  return {
    useLocalStorage: (_k, initial) => React.useState(initial),
  };
});

vi.mock("../../hooks/useRcaJobs", () => ({
  useRcaJobs: () => ({
    ...jobsState,
    setSelectedJobId,
    createJob,
    refreshJobs,
    deleteReportById,
    removeJobByReportId,
  }),
}));

vi.mock("../../hooks/useRcaReport", () => ({
  useRcaReport: () => ({
    ...reportState,
    reloadReport,
  }),
}));

vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ title, children }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

vi.mock("../../components/ui", () => ({
  Alert: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Card: ({ children }) => <div>{children}</div>,
  Spinner: () => <div>loading-spinner</div>,
}));

vi.mock("../../components/ConfirmModal", () => ({
  default: ({ isOpen, title, message, onConfirm, onCancel, confirmText }) =>
    isOpen ? (
      <div role="dialog">
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>{confirmText || "Confirm"}</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock("../../components/rca/RcaJobComposer", () => ({
  default: ({ onCreate, onDownloadTemplate, creating }) => (
    <div>
      <button
        onClick={() =>
          onCreate({ start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:05:00Z", step: "15s" })
        }
      >
        create-job
      </button>
      <button onClick={() => onDownloadTemplate()}>download-template</button>
      <span>{creating ? "creating" : "idle"}</span>
    </div>
  ),
}));

vi.mock("../../components/rca/RcaLookup", () => ({
  default: ({ value, onChange, onFind, onClear, error }) => (
    <div>
      <input value={value} onChange={onChange} placeholder="lookup" />
      <button onClick={onFind}>find-report</button>
      <button onClick={onClear}>clear-report</button>
      {error ? <span>{error}</span> : null}
    </div>
  ),
}));

vi.mock("../../components/rca/RcaJobQueuePanel", () => ({
  default: ({ onSelectJob, onReload, onDelete, onView, canDelete }) => (
    <div>
      <button onClick={() => onSelectJob("job-1")}>select-job</button>
      <button onClick={() => onReload()}>reload-job</button>
      <button onClick={() => onDelete()}>delete-job</button>
      <button onClick={() => onView({ job_id: "job-1" })}>view-job</button>
      <span>{canDelete ? "can-delete" : "cannot-delete"}</span>
    </div>
  ),
}));

vi.mock("../../components/rca/RcaReportModal", () => ({
  default: ({ isOpen, activeTab, setActiveTab, renderActiveTab, tabs, loadingReport }) =>
    isOpen ? (
      <div>
        <div>{loadingReport ? "loading-report" : "ready-report"}</div>
        <div>{tabs.length}</div>
        <button onClick={() => setActiveTab("topology")}>tab-topology</button>
        <button onClick={() => setActiveTab("causal")}>tab-causal</button>
        <button onClick={() => setActiveTab("forecast-slo")}>tab-forecast</button>
        <button onClick={() => setActiveTab("warnings")}>tab-warnings</button>
        <div>{activeTab}</div>
        {renderActiveTab({ compact: true })}
      </div>
    ) : null,
}));

vi.mock("../../components/rca/RcaReportSummary", () => ({ default: () => <div>summary-panel</div> }));
vi.mock("../../components/rca/RcaRootCauseTable", () => ({ default: () => <div>root-causes-panel</div> }));
vi.mock("../../components/rca/RcaAnomalyPanels", () => ({ default: () => <div>anomalies-panel</div> }));
vi.mock("../../components/rca/RcaDistributionStatsPanel", () => ({ default: () => <div>statistics-panel</div> }));
vi.mock("../../components/rca/RcaClusterPanel", () => ({ default: () => <div>clusters-panel</div> }));
vi.mock("../../components/rca/RcaTopologyPanel", () => ({ default: () => <div>topology-panel</div> }));
vi.mock("../../components/rca/RcaCausalPanel", () => ({ default: () => <div>causal-panel</div> }));
vi.mock("../../components/rca/RcaForecastSloPanel", () => ({ default: () => <div>forecast-panel</div> }));
vi.mock("../../components/rca/RcaWarningsPanel", () => ({ default: () => <div>warnings-panel</div> }));

import RCAPage from "../RCAPage";

describe("RCAPage coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    jobsState.jobs = [{ job_id: "job-1", report_id: "rep-1", requested_by: "u1" }];
    jobsState.loadingJobs = false;
    jobsState.creatingJob = false;
    jobsState.deletingReport = false;
    jobsState.selectedJobId = "job-1";
    jobsState.selectedJob = { job_id: "job-1", report_id: "rep-1", requested_by: "u1" };

    reportState.loadingPrimaryReport = false;
    reportState.loadingInsights = false;
    reportState.loadingReport = false;
    reportState.reportError = null;
    reportState.reportErrorStatus = null;
    reportState.report = { overall_severity: "high", metric_anomalies: [], root_causes: [] };
    reportState.reportMeta = { report_id: "rep-1", requested_by: "u1" };
    reportState.insights = {};
    reportState.insightErrors = {};
    reportState.hasReport = true;

    createJob.mockResolvedValue({ job_id: "job-2" });
    deleteReportById.mockResolvedValue({ ok: true });
  });

  it("covers composer, lookup validation, select job, and clear lookup", async () => {
    render(<RCAPage />);

    fireEvent.click(screen.getByRole("button", { name: /create-job/i }));
    fireEvent.click(screen.getByRole("button", { name: /download-template/i }));
    expect(createJob).toHaveBeenCalled();
    expect(getRcaAnalyzeConfigTemplate).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /select-job/i }));
    expect(setSelectedJobId).toHaveBeenCalledWith("job-1");

    fireEvent.change(screen.getByPlaceholderText("lookup"), { target: { value: "bad-id" } });
    fireEvent.click(screen.getByRole("button", { name: /find-report/i }));
    expect(screen.getByText(/Report ID must be a valid UUID/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /clear-report/i }));
    expect(screen.queryByText(/Report ID must be a valid UUID/i)).not.toBeInTheDocument();
  });

  it("covers report modal tab branches and insight loading/errors", async () => {
    reportState.loadingInsights = true;
    reportState.insights = {};

    render(<RCAPage />);

    fireEvent.click(screen.getByRole("button", { name: /view-job/i }));
    expect(screen.getByText("summary-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /tab-topology/i }));
    expect(screen.getByText("loading-spinner")).toBeInTheDocument();

    reportState.loadingInsights = false;
    reportState.insightErrors = { topology: "topology error" };
    fireEvent.click(screen.getByRole("button", { name: /tab-causal/i }));
    fireEvent.click(screen.getByRole("button", { name: /tab-topology/i }));
    await waitFor(() => {
      expect(screen.getByText(/topology error/i)).toBeInTheDocument();
    });

    reportState.insightErrors = { correlate: "causal error" };
    fireEvent.click(screen.getByRole("button", { name: /tab-causal/i }));
    await waitFor(() => {
      expect(screen.getByText(/causal error/i)).toBeInTheDocument();
    });

    reportState.insightErrors = {};
    fireEvent.click(screen.getByRole("button", { name: /tab-forecast/i }));
    expect(screen.getByText("forecast-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /tab-warnings/i }));
    expect(screen.getByText("warnings-panel")).toBeInTheDocument();
  });

  it("covers delete confirm flow and report error alert", async () => {
    reportState.reportError = "report failed";

    render(<RCAPage />);

    expect(screen.getByText(/report failed/i)).toBeInTheDocument();
    expect(screen.getByText("can-delete")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete-job/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(deleteReportById).toHaveBeenCalledWith("rep-1");
      expect(removeJobByReportId).toHaveBeenCalledWith("rep-1");
      expect(refreshJobs).toHaveBeenCalled();
    });
  });

  it("handles 404 lookup reset and stale storage cleanup", async () => {
    jobsState.selectedJobId = null;
    jobsState.selectedJob = null;
    localStorage.setItem("rcaPage.selectedJobId", "stale-job");
    reportState.reportErrorStatus = 404;

    render(<RCAPage />);

    fireEvent.change(screen.getByPlaceholderText("lookup"), {
      target: { value: "123e4567-e89b-12d3-a456-426614174000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /find-report/i }));

    await waitFor(() => {
      expect(localStorage.getItem("rcaPage.selectedJobId")).toBeNull();
    });
  });
});
