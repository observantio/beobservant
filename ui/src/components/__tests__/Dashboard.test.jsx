import { render, screen } from "@testing-library/react";
import Dashboard from "../Dashboard";

const dashboardData = { uptime: 99 };
const agentData = { active: 3 };
const metricOrder = [0, 1, 2];
const setMetricOrder = vi.fn();

vi.mock("../../hooks", () => ({
  useDashboardData: () => dashboardData,
  useAgentActivity: () => agentData,
  usePersistentOrder: () => [metricOrder, setMetricOrder],
}));

vi.mock("../../constants/dashboard.jsx", () => ({
  getMetricsConfig: () => [
    { key: "cpu", label: "CPU" },
    { key: "mem", label: "Memory" },
  ],
}));

vi.mock("../dashboard/index.js", () => ({
  MetricsGrid: ({ metrics, metricOrder: order, onMetricOrderChange }) => (
    <button onClick={() => onMetricOrderChange([1, 0])}>
      metrics:{metrics.length}-order:{order.join(",")}
    </button>
  ),
  DashboardLayout: ({ dashboardData: data, agentData: agents }) => (
    <div>
      layout:{String(Boolean(data))}:{String(Boolean(agents))}
    </div>
  ),
}));

vi.mock("../ui/PageHeader", () => ({
  default: ({ title }) => <div>{title}</div>,
}));

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders dashboard composition and forwards reorder callback", () => {
    render(<Dashboard />);

    expect(screen.getByText("Observability")).toBeInTheDocument();
    expect(screen.getByText("metrics:2-order:0,1,2")).toBeInTheDocument();
    expect(screen.getByText("layout:true:true")).toBeInTheDocument();

    screen.getByRole("button", { name: "metrics:2-order:0,1,2" }).click();
    expect(setMetricOrder).toHaveBeenCalledWith([1, 0]);
  });
});
