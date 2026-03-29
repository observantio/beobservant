import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppSidebar from "../AppSidebar";

let authState = {
  hasPermission: () => true,
  user: { role: "admin" },
};

const toggleSidebarMode = vi.fn();

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("../../contexts/LayoutModeContext", () => ({
  useLayoutMode: () => ({ toggleSidebarMode }),
}));

vi.mock("../../contexts/IncidentSummaryContext", () => ({
  useSharedIncidentSummary: () => ({ open: 0, acknowledged: 0, resolved: 0 }),
}));

vi.mock("../../utils/constants", () => ({
  NAV_ITEMS: {
    DASHBOARD: { label: "Dashboard", icon: "dashboard", path: "/" },
    TEMPO: {
      label: "Distributed Traces",
      icon: "timeline",
      path: "/tempo",
      permission: "read:traces",
    },
  },
  SIDEBAR_EXTRA_NAV: [
    { label: "Users", icon: "group", path: "/users", adminOnly: true },
    {
      label: "Audit",
      icon: "history",
      path: "/audit-compliance",
      permission: "read:audit_logs",
    },
    { label: "Docs", icon: "menu_book", path: "/docs" },
    { label: "Tempo Guide", icon: "description", path: "/docs/tempo" },
  ],
}));

vi.mock("../Header", () => ({
  NavItem: ({ item }) => <div>{item.label}</div>,
}));

describe("AppSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState = {
      hasPermission: () => true,
      user: { role: "admin" },
    };
  });

  it("renders nav sections and lets users toggle docs section", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppSidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Observability")).toBeInTheDocument();
    expect(screen.getByText("Management")).toBeInTheDocument();
    expect(screen.getByText("Guide")).toBeInTheDocument();
    expect(screen.getByText("Docs")).toBeInTheDocument();
    expect(screen.queryByText("Tempo Guide")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Guide" }));
    expect(screen.getByText("Tempo Guide")).toBeInTheDocument();
  });

  it("auto-expands docs navigation when current path is under docs", () => {
    render(
      <MemoryRouter initialEntries={["/docs/tempo"]}>
        <AppSidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Tempo Guide")).toBeInTheDocument();
  });

  it("hides admin-only items for non-admin users", () => {
    authState = {
      hasPermission: () => true,
      user: { role: "viewer" },
    };

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppSidebar />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Users")).not.toBeInTheDocument();
    expect(screen.getByText("Docs")).toBeInTheDocument();
  });

  it("hides permission-gated extra items when permission is missing", () => {
    authState = {
      hasPermission: (permission) => permission !== "read:audit_logs",
      user: { role: "admin" },
    };

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppSidebar />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Audit")).not.toBeInTheDocument();
  });

  it("triggers layout mode switch action", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppSidebar />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Switch to Top Nav" }));
    expect(toggleSidebarMode).toHaveBeenCalledTimes(1);
  });
});
