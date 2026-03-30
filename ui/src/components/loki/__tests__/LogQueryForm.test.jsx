import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LogQueryForm from "../LogQueryForm";

vi.mock("../../HelpTooltip", () => ({
  default: () => <span data-testid="tooltip" />,
}));

const baseProps = () => ({
  queryMode: "builder",
  customLogQL: "",
  setCustomLogQL: vi.fn(),
  labels: ["service", "namespace"],
  selectedLabel: "",
  setSelectedLabel: vi.fn(),
  labelValuesCache: { service: ["api", "worker"] },
  loadingValues: {},
  selectedValue: "",
  setSelectedValue: vi.fn(),
  pattern: "",
  setPattern: vi.fn(),
  rangeMinutes: 60,
  setRangeMinutes: vi.fn(),
  searchLimit: 100,
  setSearchLimit: vi.fn(),
  pageSize: 50,
  setPageSize: vi.fn(),
  addFilter: vi.fn(),
  selectedFilters: [],
  clearAllFilters: vi.fn(),
  runQuery: vi.fn((e) => e.preventDefault()),
  onQueryModeChange: vi.fn(),
  onLabelChange: vi.fn(),
  loading: false,
  onRemoveFilter: vi.fn(),
});

describe("LogQueryForm", () => {
  it("renders custom mode editor and updates query", () => {
    const props = baseProps();
    props.queryMode = "custom";
    props.customLogQL = "{app='api'}";

    render(<LogQueryForm {...props} />);

    const textarea = screen.getByDisplayValue("{app='api'}");
    fireEvent.change(textarea, { target: { value: "{app='worker'}" } });
    expect(props.setCustomLogQL).toHaveBeenCalledWith("{app='worker'}");
  });

  it("handles builder-mode label/value/filter actions", () => {
    const props = baseProps();
    render(<LogQueryForm {...props} />);

    const selects = screen.getAllByRole("combobox");
    const labelSelect = selects[0];
    const valueSelect = selects[1];

    fireEvent.change(labelSelect, { target: { value: "service" } });
    expect(props.setSelectedLabel).toHaveBeenCalledWith("service");
    expect(props.setSelectedValue).toHaveBeenCalledWith("");
    expect(props.onLabelChange).toHaveBeenCalledWith("service");

    expect(valueSelect).toBeDisabled();

    const addFilterBtn = screen.getByRole("button", { name: "Add Filter" });
    expect(addFilterBtn).toBeDisabled();

    const withValue = baseProps();
    withValue.selectedLabel = "service";
    withValue.selectedValue = "api";
    render(<LogQueryForm {...withValue} />);
    const enabledAddFilter = screen.getAllByRole("button", { name: "Add Filter" }).at(-1);
    fireEvent.click(enabledAddFilter);
    expect(withValue.addFilter).toHaveBeenCalled();
  });

  it("submits query, supports remove filter and loading button copy", () => {
    const props = baseProps();
    props.selectedLabel = "service";
    props.selectedValue = "api";
    props.selectedFilters = [{ label: "service", value: "api" }];
    props.loading = true;

    const { container } = render(<LogQueryForm {...props} />);
    const form = container.querySelector("form");
    fireEvent.submit(form);
    expect(props.runQuery).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Clear All" }));
    expect(props.clearAllFilters).toHaveBeenCalled();

    const removeButtons = container.querySelectorAll("button[type='button']");
    fireEvent.click(removeButtons[removeButtons.length - 1]);
    expect(props.onRemoveFilter).toHaveBeenCalledWith(0);

    expect(screen.getByRole("button", { name: "Running..." })).toBeDisabled();
  });
});