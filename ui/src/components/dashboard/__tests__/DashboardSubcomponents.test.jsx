import { fireEvent, render, screen } from "@testing-library/react";
import { AgentActivitySection } from "../AgentActivitySection";
import { DataVolume } from "../DataVolume";
import { SystemMetricsCard } from "../SystemMetricsCard";
import { DashboardLayout } from "../DashboardLayout";

let layoutModeState = { sidebarMode: true };
const setLayoutOrder = vi.fn();

vi.mock("../../../contexts/LayoutModeContext", () => ({
  useLayoutMode: () => layoutModeState,
}));

vi.mock("../../../hooks", () => ({
  usePersistentOrder: () => [[0, 1, 2, 3], setLayoutOrder],
}));

vi.mock("../../ui", () => ({
  Spinner: () => <span>spinner</span>,
  Badge: ({ children }) => <span>{children}</span>,
  Card: ({ title, children, ...props }) => (
    <div {...props}>
      {title ? <div>{title}</div> : null}
      {children}
    </div>
  ),
}));

vi.mock("../../loki/LogVolume", () => ({
  default: ({ volume }) => <div>volume:{(volume || []).length}</div>,
}));

describe("dashboard subcomponents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    layoutModeState = { sidebarMode: true };
  });

  it("renders agent activity loading, empty, and active states", () => {
    const { rerender } = render(<AgentActivitySection loading agents={[]} />);
    expect(screen.getByText(/Loading activity/i)).toBeInTheDocument();

    rerender(<AgentActivitySection loading={false} agents={[]} />);
    expect(screen.getByText(/No agent activity detected/i)).toBeInTheDocument();

    rerender(
      <AgentActivitySection
        loading={false}
        agents={[
          {
            name: "agent-abcdef",
            host_names: ["host-a"],
            metrics_count: 9,
            is_enabled: true,
            active: true,
            clean: true,
          },
          {
            name: "idle",
            host_names: [],
            metrics_count: 0,
            is_enabled: false,
            active: false,
            clean: true,
          },
        ]}
      />,
    );

    expect(screen.getByText("Metrics:")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText(/Host: host-a/i)).toBeInTheDocument();
    expect(screen.getByText("Focused")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.getByText("No activity")).toBeInTheDocument();
  });

  it("renders DataVolume loading and chart states", () => {
    const { rerender } = render(
      <DataVolume loadingLogs logVolumeSeries={[]} />,
    );
    expect(screen.getByText(/Loading logs/i)).toBeInTheDocument();

    rerender(<DataVolume loadingLogs={false} logVolumeSeries={[1, 2]} />);
    expect(screen.getByText("volume:2")).toBeInTheDocument();
  });

  it("renders SystemMetricsCard loading, error, and status branches", () => {
    const base = {
      cpu: { utilization: 25.1, threads: 4 },
      memory: { utilization: 65.4, rss_mb: 512 },
      io: { read_mb: 1.2, write_mb: 2.3 },
      network: { total_connections: 12, established: 8 },
      stress: { status: "healthy", message: "ok", issues: [] },
    };

    const { rerender } = render(<SystemMetricsCard loading systemMetrics={null} />);
    expect(screen.getByText(/Loading metrics/i)).toBeInTheDocument();

    rerender(<SystemMetricsCard loading={false} systemMetrics={null} />);
    expect(screen.getByText(/Unable to fetch system metrics/i)).toBeInTheDocument();

    rerender(<SystemMetricsCard loading={false} systemMetrics={base} />);
    expect(screen.getByText("Server Healthy")).toBeInTheDocument();

    rerender(
      <SystemMetricsCard
        loading={false}
        systemMetrics={{
          ...base,
          stress: { status: "moderate", message: "watch", issues: [] },
        }}
      />,
    );
    expect(screen.getByText("Moderate Load")).toBeInTheDocument();

    rerender(
      <SystemMetricsCard
        loading={false}
        systemMetrics={{
          ...base,
          stress: { status: "stressed", message: "high", issues: ["cpu"] },
        }}
      />,
    );
    expect(screen.getByText("Server Under Stress")).toBeInTheDocument();
    expect(screen.getByText("Active Issues")).toBeInTheDocument();
    expect(screen.getAllByText(/cpu/i).length).toBeGreaterThan(0);
  });

  it("renders DashboardLayout and handles drag-drop reorder", () => {
    const dashboardData = {
      loadingLogs: false,
      logVolumeSeries: [1],
      loadingSystemMetrics: false,
      systemMetrics: {
        stress: { status: "healthy", message: "ok", issues: [] },
        cpu: { utilization: 1, threads: 1 },
        memory: { utilization: 1, rss_mb: 1 },
        io: { read_mb: 1, write_mb: 1 },
        network: { total_connections: 1, established: 1 },
      },
    };
    const agentData = {
      loadingAgents: false,
      agentActivity: [],
    };

    const { container, rerender } = render(
      <DashboardLayout dashboardData={dashboardData} agentData={agentData} />,
    );

    expect(screen.getByText(/Welcome to Observantio/i)).toBeInTheDocument();
    expect(screen.getByText("Active OTEL Agents")).toBeInTheDocument();
    expect(screen.getByText("Proxy Plane")).toBeInTheDocument();

    const draggables = container.querySelectorAll('[draggable="true"]');
    const dataTransfer = {
      effectAllowed: "",
      dropEffect: "",
    };

    fireEvent.dragStart(draggables[0], { dataTransfer });
    fireEvent.dragOver(draggables[1], { dataTransfer });
    fireEvent.drop(draggables[1], { dataTransfer });
    fireEvent.dragEnd(draggables[1], { dataTransfer });

    expect(setLayoutOrder).toHaveBeenCalledTimes(1);

    layoutModeState = { sidebarMode: false };
    rerender(<DashboardLayout dashboardData={dashboardData} agentData={agentData} />);
    expect(container.firstChild.className).toContain("lg:grid-cols-4");
    expect(screen.queryByAltText(/Observantio wolf logo/i)).not.toBeInTheDocument();
  });
});
