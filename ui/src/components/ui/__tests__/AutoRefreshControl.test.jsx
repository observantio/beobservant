import { fireEvent, render, screen } from "@testing-library/react";
import AutoRefreshControl from "../AutoRefreshControl";

vi.mock("../../HelpTooltip", () => ({
  default: () => <span>?</span>,
}));

describe("AutoRefreshControl", () => {
  it("toggles refresh and renders interval selector when enabled", () => {
    const onToggle = vi.fn();
    const onIntervalChange = vi.fn();

    const { rerender } = render(
      <AutoRefreshControl
        enabled={false}
        onToggle={onToggle}
        interval={30}
        onIntervalChange={onIntervalChange}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox"));
    expect(onToggle).toHaveBeenCalledWith(true);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    rerender(
      <AutoRefreshControl
        enabled
        onToggle={onToggle}
        interval={30}
        onIntervalChange={onIntervalChange}
        label="Live refresh"
        tooltip="refresh tooltip"
        intervalOptions={[
          { value: 10, label: "10s" },
          { value: 30, label: "30s" },
        ]}
      />,
    );

    expect(screen.getByText("Live refresh")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "10" } });
    expect(onIntervalChange).toHaveBeenCalledWith(10);
  });
});
