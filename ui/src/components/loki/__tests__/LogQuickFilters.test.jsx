import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LogQuickFilters from "../LogQuickFilters";

describe("LogQuickFilters", () => {
  it("renders empty-state copy when no label values exist", () => {
    render(<LogQuickFilters labelValuesCache={{}} onSelectLabelValue={vi.fn()} />);

    expect(screen.getByText("No labels available yet.")).toBeInTheDocument();
    expect(screen.getByText("Try running a query first.")).toBeInTheDocument();
  });

  it("renders labels/values and triggers selection callback", () => {
    const onSelectLabelValue = vi.fn();
    render(
      <LogQuickFilters
        labelValuesCache={{
          service_name: ["checkout", "billing"],
          empty_label: [],
        }}
        onSelectLabelValue={onSelectLabelValue}
      />,
    );

    expect(screen.getByText("service name")).toBeInTheDocument();
    expect(screen.getByText("checkout")).toBeInTheDocument();
    expect(screen.getByText("billing")).toBeInTheDocument();
    expect(screen.queryByText("empty label")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /checkout/i }));
    expect(onSelectLabelValue).toHaveBeenCalledWith("service_name", "checkout");
  });
});