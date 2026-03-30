import * as dashboardExports from "../index";

describe("dashboard index exports", () => {
  it("exports dashboard building blocks", () => {
    expect(dashboardExports.MetricsGrid).toBeTypeOf("function");
    expect(dashboardExports.AgentActivitySection).toBeTypeOf("function");
    expect(dashboardExports.SystemMetricsCard).toBeTypeOf("function");
    expect(dashboardExports.DataVolume).toBeTypeOf("function");
    expect(dashboardExports.DashboardLayout).toBeTypeOf("function");
  });
});
