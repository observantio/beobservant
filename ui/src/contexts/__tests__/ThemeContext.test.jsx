import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider, useTheme } from "../ThemeContext";

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span>theme:{theme}</span>
      <button onClick={toggleTheme}>toggle</button>
    </div>
  );
}

describe("ThemeContext", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
    document.documentElement.removeAttribute("data-theme");
    document.body.removeAttribute("data-theme");
  });

  it("uses saved theme and applies document attributes", () => {
    localStorage.setItem("theme", "dark");

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );

    expect(screen.getByText("theme:dark")).toBeInTheDocument();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.body.getAttribute("data-theme")).toBe("dark");
  });

  it("toggles between dark and light and persists in localStorage", () => {
    localStorage.setItem("theme", "light");

    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "toggle" }));

    expect(screen.getByText("theme:dark")).toBeInTheDocument();
    expect(localStorage.getItem("theme")).toBe("dark");
  });
});
