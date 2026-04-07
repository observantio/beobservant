import { render, fireEvent, waitFor } from "@testing-library/react";
import TempoPage from "../TempoPage";
import * as api from "../../api";

vi.mock("../../hooks", () => ({ useAutoRefresh: () => {} }));
let authState = {
  user: { id: "u1", username: "me", org_id: "org-a", api_keys: [] },
  isAuthenticated: true,
  loading: false,
  hasPermission: () => true,
};
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));
vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));
vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));
vi.mock("../../components/ui/AutoRefreshControl", () => ({
  default: () => <div />,
}));
vi.mock("../../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, loading, ...props }) => (
    <button {...props} disabled={loading || props.disabled}>
      {children}
    </button>
  ),
  Input: (props) => <input {...props} />,
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Spinner: () => <div>Loading</div>,
  Badge: ({ children }) => <span>{children}</span>,
  Alert: ({ children }) => <div>{children}</div>,
}));
vi.mock("../../components/HelpTooltip", () => ({ default: () => <span /> }));
vi.mock("../../components/tempo/TraceResults", () => ({
  default: ({ traces }) => <div>Trace results: {traces?.length || 0}</div>,
}));
vi.mock("../../components/tempo/TraceTimeline", () => ({
  default: () => <div>Trace timeline</div>,
}));

vi.mock("../../api");

describe("TempoPage — fetch limit and pagination", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    authState = {
      user: { id: "u1", username: "me", org_id: "org-a", api_keys: [] },
      isAuthenticated: true,
      loading: false,
      hasPermission: () => true,
    };
  });

  it("allows a separate search limit (max traces) and sends it to the API", async () => {
    api.fetchTempoServices.mockResolvedValue([]);
    api.searchTraces.mockResolvedValue({ data: [] });

    const { getByText } = render(<TempoPage />);

    
    const limitLabel = getByText(/Search Limit/i);
    const limitSelect = limitLabel.parentElement.querySelector("select");
    fireEvent.change(limitSelect, { target: { value: "50" } });

    const searchBtn = getByText(/Search Traces/i);
    fireEvent.click(searchBtn);

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled());
    const lastCall = api.searchTraces.mock.calls[0][0];
    expect(lastCall.limit).toBe(50);
    expect(lastCall.fetchFull).toBe(false);
  });

  it("calculates total pages based on pageSize and shows pagination info", async () => {
    api.fetchTempoServices.mockResolvedValue([]);
    
    const fakeTraces = Array.from({ length: 45 }, (_, i) => ({
      traceID: `t${i}`,
      spans: [{ duration: 1000, operationName: "op", attributes: [] }],
    }));
    api.searchTraces.mockResolvedValue({ data: fakeTraces });

    const { getByText, findByText } = render(<TempoPage />);
    const searchBtn = getByText(/Search Traces/i);
    fireEvent.click(searchBtn);

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled());

    const pageInfo = await findByText(/Page\s*1\s*of\s*3/i);
    expect(pageInfo).toBeInTheDocument();
  });

  it("does not restore filters or auto-search from localStorage on mount", async () => {
    localStorage.setItem(
      "tempoPageState",
      JSON.stringify({
        service: "svc",
        viewMode: "list",
      }),
    );
    api.fetchTempoServices.mockResolvedValue([]);
    api.searchTraces.mockResolvedValue({ data: [] });

    const { getByText } = render(<TempoPage />);
    expect(api.searchTraces).not.toHaveBeenCalled();

    fireEvent.click(getByText(/Search Traces/i));
    await waitFor(() => expect(api.searchTraces).toHaveBeenCalledTimes(1));
    const call = api.searchTraces.mock.calls[0][0];
    expect(call.service).toBe("");
  });

  it("shows only services with current trace data after search", async () => {
    api.fetchTempoServices.mockResolvedValue(["frontend", "checkout"]);
    api.searchTraces.mockResolvedValue({
      data: [
        {
          traceID: "t1",
          spans: [
            {
              duration: 1000,
              operationName: "GET /checkout",
              serviceName: "checkout",
              startTime: 1000,
            },
          ],
        },
      ],
    });

    const { getAllByRole, getByText } = render(<TempoPage />);
    await waitFor(() => expect(api.fetchTempoServices).toHaveBeenCalled());

    const selectElements = getAllByRole("combobox");
    const serviceSelect = selectElements[0];
    expect(serviceSelect.children.length).toBe(3); // All Services + frontend + checkout

    fireEvent.change(serviceSelect, { target: { value: "checkout" } });
    fireEvent.click(getByText(/Search Traces/i));
    await waitFor(() => expect(api.searchTraces).toHaveBeenCalledTimes(1));

    expect(serviceSelect.value).toBe("checkout");
    expect(serviceSelect.children.length).toBe(2); // All Services + checkout only
    expect(Array.from(serviceSelect.children).map((o) => o.value)).toEqual(["", "checkout"]);

    const call = api.searchTraces.mock.calls[0][0];
    expect(call.service).toBe("checkout");
  });

  it("does not auto-lookup saved trace ids from localStorage", async () => {
    localStorage.setItem(
      "tempoPageState",
      JSON.stringify({ selectedTrace: "missing" }),
    );
    api.fetchTempoServices.mockResolvedValue([]);
    api.searchTraces.mockResolvedValue({ data: [] });
    api.getTrace.mockResolvedValue({ traceID: "missing", spans: [] });

    render(<TempoPage />);
    await waitFor(() => expect(api.fetchTempoServices).toHaveBeenCalled());
    expect(api.getTrace).not.toHaveBeenCalled();
  });

  it("re-fetches tempo services when the active API key changes", async () => {
    api.fetchTempoServices
      .mockResolvedValueOnce(["svc-a"])
      .mockResolvedValueOnce(["svc-b"]);
    api.searchTraces.mockResolvedValue({ data: [] });

    const { rerender } = render(<TempoPage />);
    await waitFor(() => {
      expect(api.fetchTempoServices).toHaveBeenCalledTimes(1);
    });

    authState = {
      ...authState,
      user: {
        ...authState.user,
        api_keys: [
          { id: "key-a", key: "org-a", is_enabled: false },
          { id: "key-b", key: "org-b", is_enabled: true },
        ],
      },
    };
    rerender(<TempoPage />);

    await waitFor(() => {
      expect(api.fetchTempoServices).toHaveBeenCalledTimes(2);
    });
  });

  it("shows suggested traces in dependency map mode when no map trace is selected", async () => {
    api.fetchTempoServices.mockResolvedValue([]);
    api.searchTraces.mockResolvedValue({
      data: [
        {
          traceID: "trace-a",
          spans: [
            {
              duration: 1000,
              operationName: "GET /checkout",
              attributes: [{ key: "service.name", value: { stringValue: "checkout" } }],
              startTime: 1000,
            },
          ],
        },
      ],
    });
    api.getTrace.mockResolvedValue({
      traceID: "trace-a",
      spans: [
        {
          spanId: "1",
          duration: 1000,
          operationName: "GET /checkout",
          attributes: [{ key: "service.name", value: { stringValue: "checkout" } }],
          startTime: 1000,
        },
      ],
    });

    const { getByText, findByText, findByRole, queryByText } = render(<TempoPage />);

    fireEvent.click(getByText(/Search Traces/i));
    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled());

    fireEvent.click(getByText(/Dependency Map/i));

    expect(await findByText(/Pick a Trace to Inspect/i)).toBeInTheDocument();
    expect(await findByText(/Open on dependency map/i)).toBeInTheDocument();
    expect(queryByText(/No Traces Found/i)).not.toBeInTheDocument();

    fireEvent.click(await findByRole("button", { name: /trace-a/i }));

    await waitFor(() => {
      expect(api.getTrace).toHaveBeenCalledWith("trace-a");
    });
  });
});
