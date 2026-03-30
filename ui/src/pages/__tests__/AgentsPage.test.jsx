import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = {
  user: {
    api_keys: [
      { id: "k1", name: "Tenant A", key: "tenant-a", is_enabled: true },
      { id: "k2", name: "Tenant B", key: "tenant-b", is_enabled: false },
    ],
  },
};

vi.mock("../../api", () => ({
  getAgents: vi.fn(),
  getActiveAgents: vi.fn(),
  getAgentMetricVolume: vi.fn(),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

import * as api from "../../api";
import AgentsPage from "../AgentsPage";

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      api_keys: [
        { id: "k1", name: "Tenant A", key: "tenant-a", is_enabled: true },
        { id: "k2", name: "Tenant B", key: "tenant-b", is_enabled: false },
      ],
    };

    vi.mocked(api.getAgents).mockResolvedValue([
      {
        id: "a1",
        name: "edge-a",
        tenant_id: "tenant-a",
        host_name: "host-a",
        last_seen: "2026-03-26T08:00:00Z",
        signals: ["metrics", "logs"],
        attributes: {},
      },
      {
        id: "b1",
        name: "edge-b",
        tenant_id: "tenant-b",
        host_name: "host-b",
        last_seen: "2026-03-26T08:01:00Z",
        signals: ["metrics"],
        attributes: {},
      },
    ]);
    vi.mocked(api.getActiveAgents).mockResolvedValue([
      {
        name: "Tenant A",
        tenant_id: "tenant-a",
        active: true,
        metrics_count: 9,
        host_names: ["host-a"],
      },
      {
        name: "Tenant B",
        tenant_id: "tenant-b",
        active: false,
        metrics_count: 2,
        host_names: ["host-b"],
      },
    ]);
    vi.mocked(api.getAgentMetricVolume).mockResolvedValue({
      tenant_id: "tenant-a",
      current: 9,
      peak: 12,
      average: 8,
      points: [
        { ts: 1, value: 4 },
        { ts: 2, value: 9 },
      ],
    });
  });

  it("renders scoped agent details and metric volume", async () => {
    render(<AgentsPage />);

    expect(await screen.findByText(/Metric Volume/i)).toBeInTheDocument();
    expect(await screen.findByText("edge-a")).toBeInTheDocument();
    expect(screen.queryByText("edge-b")).not.toBeInTheDocument();
    expect(await screen.findByText(/Metric names right now:/i)).toBeInTheDocument();
    expect(await screen.findByText(/Latest sampled metric count/i)).toBeInTheDocument();

    await waitFor(() =>
      expect(api.getAgentMetricVolume).toHaveBeenCalledWith(
        expect.objectContaining({ tenantId: "tenant-a", stepSeconds: 60 }),
      ),
    );
  });

  it("refreshes scope when the enabled api key changes", async () => {
    const { rerender } = render(<AgentsPage />);

    await waitFor(() =>
      expect(api.getAgentMetricVolume).toHaveBeenCalledWith(
        expect.objectContaining({ tenantId: "tenant-a", stepSeconds: 60 }),
      ),
    );

    vi.mocked(api.getAgentMetricVolume).mockResolvedValueOnce({
      tenant_id: "tenant-b",
      current: 2,
      peak: 3,
      average: 2,
      points: [{ ts: 1, value: 2 }],
    });
    authState.user = {
      api_keys: [
        { id: "k1", name: "Tenant A", key: "tenant-a", is_enabled: false },
        { id: "k2", name: "Tenant B", key: "tenant-b", is_enabled: true },
      ],
    };

    rerender(<AgentsPage />);

    await waitFor(() =>
      expect(api.getAgentMetricVolume).toHaveBeenLastCalledWith(
        expect.objectContaining({ tenantId: "tenant-b", stepSeconds: 60 }),
      ),
    );
    expect(await screen.findByText("edge-b")).toBeInTheDocument();
    expect(screen.queryByText("edge-a")).not.toBeInTheDocument();
  });

  it("falls back to metric activity when heartbeat data is missing", async () => {
    vi.mocked(api.getAgents).mockResolvedValueOnce([]);
    vi.mocked(api.getActiveAgents).mockResolvedValueOnce([
      {
        name: "Tenant A",
        tenant_id: "tenant-a",
        active: true,
        metrics_count: 245,
        host_names: [],
        agent_estimate: 4,
        host_estimate: 2,
      },
    ]);
    vi.mocked(api.getAgentMetricVolume).mockResolvedValueOnce({
      tenant_id: "tenant-a",
      current: 0,
      peak: 0,
      average: 0,
      points: [],
    });

    render(<AgentsPage />);

    expect(await screen.findByText(/Metrics are active for this API key scope/i)).toBeInTheDocument();
    expect(await screen.findByText(/Heartbeat optional/i)).toBeInTheDocument();
    expect(await screen.findByText(/Metrics active/i)).toBeInTheDocument();
    expect(await screen.findByText(/Metric names right now:/i)).toBeInTheDocument();
    expect(await screen.findByText(/Estimated from metric labels: 4 active metric sources/i)).toBeInTheDocument();
    expect(await screen.findByText(/Estimated from metric labels: 2 hosts/i)).toBeInTheDocument();
    expect(screen.getAllByText("245").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });
});
