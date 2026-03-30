import { render, screen } from "@testing-library/react";
import { SERVICES, getMetricsConfig } from "../dashboard.jsx";

describe("dashboard constants", () => {
  it("exports service definitions", () => {
    expect(SERVICES.length).toBeGreaterThanOrEqual(4);
    SERVICES.forEach((service) => {
      expect(service.name).toBeTruthy();
      expect(service.description).toBeTruthy();
      expect(service.icon).toBeTruthy();
    });
  });

  it("builds metrics values for loading and non-loading states", () => {
    const loadingData = {
      loadingHealth: true,
      health: null,
      loadingAlerts: true,
      alertCount: null,
      loadingLogs: true,
      logVolume: null,
      loadingDashboards: true,
      dashboardCount: null,
      loadingSilences: true,
      silenceCount: null,
      loadingDatasources: true,
      datasourceCount: null,
    };

    const loadedData = {
      loadingHealth: false,
      health: { status: "Healthy" },
      loadingAlerts: false,
      alertCount: 2,
      loadingLogs: false,
      logVolume: 11,
      loadingDashboards: false,
      dashboardCount: 7,
      loadingSilences: false,
      silenceCount: 1,
      loadingDatasources: false,
      datasourceCount: 4,
    };

    const unknownData = {
      ...loadedData,
      health: null,
      alertCount: null,
      logVolume: null,
      dashboardCount: null,
      silenceCount: null,
      datasourceCount: null,
    };

    const loadingMetrics = getMetricsConfig(loadingData);
    const loadedMetrics = getMetricsConfig(loadedData);
    const unknownMetrics = getMetricsConfig(unknownData);

    expect(loadingMetrics).toHaveLength(7);
    expect(loadedMetrics).toHaveLength(7);
    expect(unknownMetrics).toHaveLength(7);

    render(
      <div>
        {loadingMetrics.map((metric) => (
          <div key={`loading-${metric.id}`}>{metric.value}</div>
        ))}
        {loadedMetrics.map((metric) => (
          <div key={`loaded-${metric.id}`}>{metric.value}</div>
        ))}
        {unknownMetrics.map((metric) => (
          <div key={`unknown-${metric.id}`}>{metric.value}</div>
        ))}
      </div>,
    );

    expect(screen.getAllByText(/Loading/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("N/A").length).toBeGreaterThan(0);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});
