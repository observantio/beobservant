import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const toast = { success: vi.fn(), error: vi.fn() };
const authState = {
  user: { id: "u1", org_id: "org-1", api_keys: [] },
  isAuthenticated: true,
  loading: false,
};

const fetchTempoServices = vi.fn();
const searchTraces = vi.fn();
const getTrace = vi.fn();

vi.mock("../../hooks", () => ({
  useAutoRefresh: () => {},
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../api", () => ({
  fetchTempoServices: (...args) => fetchTempoServices(...args),
  searchTraces: (...args) => searchTraces(...args),
  getTrace: (...args) => getTrace(...args),
}));

vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));

vi.mock("../../components/ui/AutoRefreshControl", () => ({
  default: () => <div>auto-refresh</div>,
}));

vi.mock("../../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, loading, ...props }) => (
    <button {...props} disabled={loading || props.disabled}>
      {children}
    </button>
  ),
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Input: (props) => <input {...props} />, 
  Spinner: () => <div>Loading</div>,
}));

vi.mock("../../components/HelpTooltip", () => ({
  default: () => <span>help</span>,
}));

vi.mock("../../components/tempo/ServiceGraph", () => ({
  default: () => <div>service-graph</div>,
}));

vi.mock("../../components/tempo/TraceResults", () => ({
  default: ({ traces = [], handleTraceClick, onToggleSelect, onShowOnMap }) => (
    <div>
      {traces.map((trace) => (
        <div key={trace.traceID}>
          <span>{trace.traceID}</span>
          <button onClick={() => handleTraceClick(trace.traceID)}>open-{trace.traceID}</button>
          <button onClick={() => onToggleSelect(trace.traceID, true)}>select-{trace.traceID}</button>
          <button onClick={() => onShowOnMap(trace.traceID)}>map-{trace.traceID}</button>
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../components/tempo/TraceTimeline", () => ({
  default: ({ trace, onClose, onCopyTraceId }) => (
    <div>
      <div>timeline-{trace?.traceID || trace?.traceId || trace?.id}</div>
      <button onClick={onCopyTraceId}>copy-trace-id</button>
      <button onClick={onClose}>close-timeline</button>
    </div>
  ),
}));

import TempoPage from "../TempoPage";

describe("TempoPage extra coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchTempoServices.mockResolvedValue(["svc-a"]);
    searchTraces.mockResolvedValue({
      data: [
        {
          traceID: "t-1",
          spans: [
            {
              spanId: "s1",
              operationName: "GET /",
              duration: 1000,
              startTime: 1,
              attributes: [{ key: "service.name", value: { stringValue: "svc-a" } }],
            },
          ],
        },
      ],
    });
    getTrace.mockResolvedValue({
      traceID: "t-1",
      spans: [
        {
          spanId: "s1",
          operationName: "GET /",
          duration: 1000,
          startTime: 1,
          attributes: [{ key: "service.name", value: { stringValue: "svc-a" } }],
        },
      ],
    });
  });

  it("shows selected traces on dependency map", async () => {
    render(<TempoPage />);

    fireEvent.click(screen.getByRole("button", { name: /Search Traces/i }));
    await waitFor(() => {
      expect(searchTraces).toHaveBeenCalled();
    });

    fireEvent.click(await screen.findByRole("button", { name: /select-t-1/i }));
    fireEvent.click(screen.getByRole("button", { name: /Show selected on Map/i }));

    await waitFor(() => {
      expect(getTrace).toHaveBeenCalledWith("t-1");
      expect(screen.getByText("service-graph")).toBeInTheDocument();
    });
  });

  it("covers trace lookup errors and incomplete trace responses", async () => {
    render(<TempoPage />);

    getTrace.mockRejectedValueOnce({ status: 404 });
    fireEvent.change(screen.getByPlaceholderText(/Paste a trace ID/i), {
      target: { value: "missing-trace" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Lookup/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Trace not found: missing-trace");
    });

    getTrace.mockResolvedValueOnce({ traceID: "t-no-spans" });
    fireEvent.change(screen.getByPlaceholderText(/Paste a trace ID/i), {
      target: { value: "t-no-spans" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Lookup/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Trace data is incomplete — no spans returned");
    });
  });

  it("covers dependency map suggestion trace load failure", async () => {
    getTrace.mockRejectedValueOnce(new Error("boom"));

    render(<TempoPage />);

    fireEvent.click(screen.getByRole("button", { name: /Search Traces/i }));
    await waitFor(() => {
      expect(searchTraces).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTitle(/Dependency Map/i));
    fireEvent.click(await screen.findByRole("button", { name: /t-1/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to load trace: boom");
    });
  });

  it("handles selected map flow with missing trace", async () => {
    getTrace.mockResolvedValueOnce({ traceID: "t-1", spans: [] });

    render(<TempoPage />);

    fireEvent.click(screen.getByRole("button", { name: /Search Traces/i }));
    await waitFor(() => {
      expect(searchTraces).toHaveBeenCalled();
    });

    fireEvent.click(await screen.findByRole("button", { name: /select-t-1/i }));
    fireEvent.click(screen.getByRole("button", { name: /Show selected on Map/i }));

    await waitFor(() => {
      expect(screen.queryByText("service-graph")).not.toBeInTheDocument();
    });
  });
});
