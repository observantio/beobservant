import { fireEvent, render, screen } from "@testing-library/react";
import ThemeToggle from "../ThemeToggle";

let themeState = {
  theme: "dark",
  toggleTheme: vi.fn(),
};

vi.mock("../../contexts/ThemeContext", () => ({
  useTheme: () => themeState,
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    themeState = {
      theme: "dark",
      toggleTheme: vi.fn(),
    };
  });

  it("renders dark-mode toggle affordance and triggers toggle", () => {
    render(<ThemeToggle className="custom" />);

    const btn = screen.getByRole("button", { name: /Switch to light mode/i });
    fireEvent.click(btn);

    expect(btn.className).toContain("custom");
    expect(themeState.toggleTheme).toHaveBeenCalledTimes(1);
  });

  it("renders light-mode toggle affordance", () => {
    themeState = {
      theme: "light",
      toggleTheme: vi.fn(),
    };

    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /Switch to dark mode/i })).toBeInTheDocument();
  });
});
