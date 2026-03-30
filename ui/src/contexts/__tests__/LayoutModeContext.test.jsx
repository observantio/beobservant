import { fireEvent, render, screen } from "@testing-library/react";
import { LayoutModeProvider, useLayoutMode } from "../LayoutModeContext";

function LayoutProbe() {
  const { sidebarMode, toggleSidebarMode } = useLayoutMode();
  return (
    <div>
      <span>sidebar:{String(sidebarMode)}</span>
      <button onClick={toggleSidebarMode}>toggle layout</button>
    </div>
  );
}

describe("LayoutModeContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("restores saved sidebar mode from localStorage", () => {
    localStorage.setItem("observantio-ui-sidebar-layout", "0");

    render(
      <LayoutModeProvider>
        <LayoutProbe />
      </LayoutModeProvider>,
    );

    expect(screen.getByText("sidebar:false")).toBeInTheDocument();
  });

  it("toggles sidebar mode and persists changes", () => {
    render(
      <LayoutModeProvider>
        <LayoutProbe />
      </LayoutModeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "toggle layout" }));

    expect(screen.getByText("sidebar:false")).toBeInTheDocument();
    expect(localStorage.getItem("observantio-ui-sidebar-layout")).toBe("0");
  });

  it("returns safe defaults when used outside provider", () => {
    render(<LayoutProbe />);
    expect(screen.getByText("sidebar:true")).toBeInTheDocument();
  });
});
