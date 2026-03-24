import { render, fireEvent, waitFor } from "@testing-library/react";
import TempoPage from "../TempoPage";
import * as api from "../../api";

vi.mock("../../hooks", () => ({ useAutoRefresh: () => {} }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", username: "me" },
    hasPermission: () => true,
  }),
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
  Button: ({ children }) => <button>{children}</button>,
  Input: (props) => <input {...props} />,
  Select: ({ children }) => <select>{children}</select>,
  Spinner: () => <div>Loading</div>,
  Badge: ({ children }) => <span>{children}</span>,
  Alert: ({ children }) => <div>{children}</div>,
}));
vi.mock("../../components/HelpTooltip", () => ({ default: () => <span /> }));

vi.mock("../../api");

describe("TempoPage — fetch limit and pagination", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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
    }));
    api.searchTraces.mockResolvedValue({ data: fakeTraces });

    const { getByText } = render(<TempoPage />);
    const searchBtn = getByText(/Search Traces/i);
    fireEvent.click(searchBtn);

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled());

    
    await waitFor(() => {
      expect(getByText(/Page 1 of 3/)).toBeInTheDocument();
    });
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

  it("does not auto-lookup saved trace ids from localStorage", async () => {
    localStorage.setItem(
      "tempoPageState",
      JSON.stringify({ selectedTrace: "missing" }),
    );
    api.fetchTempoServices.mockResolvedValue([]);
    api.searchTraces.mockResolvedValue({ data: [] });
    api.getTrace.mockResolvedValue({ traceID: "missing", spans: [] });

    render(<TempoPage />);
    expect(api.getTrace).not.toHaveBeenCalled();
  });
});
