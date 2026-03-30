import React from "react";
import { fireEvent, render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("../../../contexts/LayoutModeContext", () => ({
  useLayoutMode: vi.fn(() => ({ sidebarMode: false })),
}));

import { MetricsGrid } from "../MetricsGrid";

const baseMetrics = [
  {
    id: "a",
    label: "A",
    value: "1",
    trend: "",
    status: "default",
    icon: null,
  },
  {
    id: "b",
    label: "B",
    value: "2",
    trend: "",
    status: "default",
    icon: null,
  },
  {
    id: "c",
    label: "C",
    value: "3",
    trend: "",
    status: "default",
    icon: null,
  },
];

describe("MetricsGrid", () => {
  it("ignores stale metricOrder indices that do not exist in metrics", () => {
    const metrics = baseMetrics.slice(0, 2);
    const metricOrder = [0, 1, 2]; 

    const { getByText } = render(
      <MetricsGrid
        metrics={metrics}
        metricOrder={metricOrder}
        onMetricOrderChange={vi.fn()}
      />,
    );

    expect(getByText("A")).toBeInTheDocument();
    expect(getByText("B")).toBeInTheDocument();
  });

  it("reorders metrics on drag/drop between different indices", () => {
    const onMetricOrderChange = vi.fn();
    const { container } = render(
      <MetricsGrid
        metrics={baseMetrics}
        metricOrder={[0, 1, 2]}
        onMetricOrderChange={onMetricOrderChange}
      />,
    );

    const cards = container.querySelectorAll("button[draggable='true']");
    const dragSource = cards[0];
    const dropTarget = cards[2];

    const dataTransfer = {
      effectAllowed: "",
      dropEffect: "",
      setData: vi.fn(),
      getData: vi.fn(),
    };

    fireEvent.dragStart(dragSource, { dataTransfer });
    fireEvent.dragOver(dropTarget, { dataTransfer });
    fireEvent.drop(dropTarget, { dataTransfer });

    expect(onMetricOrderChange).toHaveBeenCalledWith([1, 2, 0]);
  });

  it("does not reorder when dropped onto same index", () => {
    const onMetricOrderChange = vi.fn();
    const { container } = render(
      <MetricsGrid
        metrics={baseMetrics}
        metricOrder={[0, 1, 2]}
        onMetricOrderChange={onMetricOrderChange}
      />,
    );

    const cards = container.querySelectorAll("button[draggable='true']");
    const sameCard = cards[1];
    const dataTransfer = {
      effectAllowed: "",
      dropEffect: "",
      setData: vi.fn(),
      getData: vi.fn(),
    };

    fireEvent.dragStart(sameCard, { dataTransfer });
    fireEvent.drop(sameCard, { dataTransfer });

    expect(onMetricOrderChange).not.toHaveBeenCalled();
  });
});
