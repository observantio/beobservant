import { act, renderHook, waitFor } from "@testing-library/react";
import { useAgentActivity } from "../useAgentActivity";
import { useDashboardData } from "../useDashboardData";
import { useIncidentSummary } from "../useIncidentSummary";
import { usePersistentOrder } from "../usePersistentOrder";
import * as api from "../../api";

let hasPermission = () => true;
let userState = { id: "u1", org_id: "org-a", api_keys: [] };

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ hasPermission, user: userState }),
}));

vi.mock("../../utils/lokiQueryUtils", () => ({
  getVolumeValues: vi.fn(() => [1, 2]),
}));

vi.mock("../../api", () => ({
  getActiveAgents: vi.fn(),
  fetchHealth: vi.fn(),
  getAlerts: vi.fn(),
  getLogVolume: vi.fn(),
  searchDashboards: vi.fn(),
  getSilences: vi.fn(),
  getDatasources: vi.fn(),
  fetchSystemMetrics: vi.fn(),
  getIncidentsSummary: vi.fn(),
}));

describe("data hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    hasPermission = () => true;
    userState = { id: "u1", org_id: "org-a", api_keys: [] };
  });

  it("useAgentActivity handles success and failure", async () => {
    api.getActiveAgents.mockResolvedValueOnce([{ name: "a" }]).mockRejectedValueOnce(new Error("x"));

    const success = renderHook(() => useAgentActivity());
    await waitFor(() => expect(success.result.current.loadingAgents).toBe(false));
    expect(success.result.current.agentActivity).toEqual([{ name: "a" }]);

    const failed = renderHook(() => useAgentActivity());
    await waitFor(() => expect(failed.result.current.loadingAgents).toBe(false));
    expect(failed.result.current.agentActivity).toEqual([]);
  });

  it("useAgentActivity refetches when active API key changes", async () => {
    api.getActiveAgents
      .mockResolvedValueOnce([{ name: "tenant-a-agent" }])
      .mockResolvedValueOnce([{ name: "tenant-b-agent" }]);

    const { result, rerender } = renderHook(() => useAgentActivity());
    await waitFor(() => expect(result.current.loadingAgents).toBe(false));
    expect(api.getActiveAgents).toHaveBeenCalledTimes(1);

    userState = {
      id: "u1",
      org_id: "org-b",
      api_keys: [
        { id: "key-a", key: "org-a", is_enabled: false },
        { id: "key-b", key: "org-b", is_enabled: true },
      ],
    };
    rerender();

    await waitFor(() => expect(api.getActiveAgents).toHaveBeenCalledTimes(2));
  });

  it("useDashboardData fills fields when allowed and handles denied branches", async () => {
    api.fetchHealth.mockResolvedValue({ status: "Healthy" });
    api.getAlerts.mockResolvedValue([{}, {}]);
    api.getLogVolume.mockResolvedValue({ data: { result: [{ values: [[0, "1"]] }] } });
    api.searchDashboards.mockResolvedValue([{}]);
    api.getSilences.mockResolvedValue([{}]);
    api.getDatasources.mockResolvedValue([{}, {}]);
    api.fetchSystemMetrics.mockResolvedValue({ stress: { message: "ok" } });

    const full = renderHook(() => useDashboardData());
    await waitFor(() => expect(full.result.current.loadingSystemMetrics).toBe(false));
    expect(full.result.current.alertCount).toBe(2);
    expect(full.result.current.dashboardCount).toBe(1);
    expect(full.result.current.datasourceCount).toBe(2);

    hasPermission = (p) => p === "read:logs";
    const partial = renderHook(() => useDashboardData());
    await waitFor(() => expect(partial.result.current.loadingSystemMetrics).toBe(false));
    expect(partial.result.current.loadingAlerts).toBe(false);
    expect(partial.result.current.loadingDashboards).toBe(false);
    expect(partial.result.current.loadingDatasources).toBe(false);
  });

  it("useDashboardData refetches when active API key changes", async () => {
    api.fetchHealth.mockResolvedValue({ status: "Healthy" });
    api.getAlerts.mockResolvedValue([]);
    api.getLogVolume.mockResolvedValue({ data: { result: [] } });
    api.searchDashboards.mockResolvedValue([]);
    api.getSilences.mockResolvedValue([]);
    api.getDatasources.mockResolvedValue([]);
    api.fetchSystemMetrics.mockResolvedValue({ stress: { message: "ok" } });

    const { result, rerender } = renderHook(() => useDashboardData());
    await waitFor(() => expect(result.current.loadingSystemMetrics).toBe(false));
    expect(api.fetchHealth).toHaveBeenCalledTimes(1);

    userState = {
      id: "u1",
      org_id: "org-b",
      api_keys: [
        { id: "key-a", key: "org-a", is_enabled: false },
        { id: "key-b", key: "org-b", is_enabled: true },
      ],
    };
    rerender();

    await waitFor(() => expect(api.fetchHealth).toHaveBeenCalledTimes(2));
  });

  it("useIncidentSummary handles permission gate and successful load", async () => {
    hasPermission = () => false;
    const denied = renderHook(() => useIncidentSummary());
    expect(denied.result.current).toBeNull();

    hasPermission = () => true;
    api.getIncidentsSummary.mockResolvedValue({ open: 3 });
    const allowed = renderHook(() => useIncidentSummary());
    await waitFor(() => expect(allowed.result.current).toEqual({ open: 3 }));
  });

  it("usePersistentOrder sanitizes, persists, and handles invalid JSON", () => {
    localStorage.setItem("order", JSON.stringify([2, 2, 9, 1]));
    const { result, rerender } = renderHook(({ length }) =>
      usePersistentOrder("order", length),
      { initialProps: { length: 4 } },
    );

    expect(result.current[0]).toEqual([2, 1, 0, 3]);
    act(() => {
      result.current[1]([3, 1, 1]);
    });
    expect(JSON.parse(localStorage.getItem("order"))).toEqual([3, 1, 0, 2]);

    localStorage.setItem("order", "not-json");
    rerender({ length: 3 });
    expect(result.current[0]).toEqual([1, 0, 2]);
  });
});
