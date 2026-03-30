import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { fetchInfo } from "../api";

let authState = {
  isAuthenticated: false,
  loading: false,
  user: null,
  refreshUser: vi.fn(),
  authMode: { oidc_enabled: false, password_enabled: true },
  hasPermission: () => true,
};

let layoutState = {
  sidebarMode: true,
};

vi.mock("../api", () => ({
  fetchInfo: vi.fn(),
}));

vi.mock("../contexts/ThemeContext", () => ({
  ThemeProvider: ({ children }) => <>{children}</>,
}));

vi.mock("../contexts/LayoutModeContext", () => ({
  LayoutModeProvider: ({ children }) => <>{children}</>,
  useLayoutMode: () => layoutState,
}));

vi.mock("../contexts/IncidentSummaryContext", () => ({
  IncidentSummaryProvider: ({ children }) => <>{children}</>,
}));

vi.mock("../contexts/AuthContext", () => ({
  AuthProvider: ({ children }) => <>{children}</>,
  useAuth: () => authState,
}));

vi.mock("../contexts/ToastContext", () => ({
  ToastProvider: ({ children }) => <>{children}</>,
}));

vi.mock("../components/Header", () => ({
  default: () => <div>Header</div>,
}));

vi.mock("../components/AppSidebar", () => ({
  default: () => <div>Sidebar</div>,
}));

vi.mock("../components/Dashboard", () => ({
  default: ({ info }) => <div>Dashboard {info ? "with info" : "no info"}</div>,
}));

vi.mock("../components/ErrorBoundary", () => ({
  default: ({ children }) => <>{children}</>,
}));

vi.mock("../components/ChangePasswordModal", () => ({
  default: ({ isOpen }) => (isOpen ? <div>Change Password</div> : null),
}));

vi.mock("../components/ui", () => ({
  Spinner: () => <div>Loading</div>,
}));

vi.mock("../pages/TempoPage", () => ({ default: () => <div>Tempo page</div> }));
vi.mock("../pages/LokiPage", () => ({ default: () => <div>Loki page</div> }));
vi.mock("../pages/AlertManagerPage", () => ({ default: () => <div>Alerts page</div> }));
vi.mock("../pages/IncidentBoardPage", () => ({ default: () => <div>Incidents page</div> }));
vi.mock("../pages/GrafanaPage", () => ({ default: () => <div>Grafana page</div> }));
vi.mock("../pages/LoginPage", () => ({ default: () => <div>Login page</div> }));
vi.mock("../pages/OIDCCallbackPage", () => ({ default: () => <div>OIDC callback</div> }));
vi.mock("../pages/UsersPage", () => ({ default: () => <div>Users page</div> }));
vi.mock("../pages/GroupsPage", () => ({ default: () => <div>Groups page</div> }));
vi.mock("../pages/ApiKeyPage", () => ({ default: () => <div>API key page</div> }));
vi.mock("../pages/IntegrationsPage", () => ({ default: () => <div>Integrations page</div> }));
vi.mock("../pages/DocumentationPage", () => ({ default: () => <div>Docs page</div> }));
vi.mock("../pages/AuditCompliancePage", () => ({ default: () => <div>Audit page</div> }));
vi.mock("../pages/RCAPage", () => ({ default: () => <div>RCA page</div> }));
vi.mock("../pages/QuotasPage", () => ({ default: () => <div>Quotas page</div> }));
vi.mock("../pages/AgentsPage", () => ({ default: () => <div>Agents page</div> }));

describe("App shell routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, "", "/");
    authState = {
      isAuthenticated: false,
      loading: false,
      user: null,
      refreshUser: vi.fn(),
      authMode: { oidc_enabled: false, password_enabled: true },
      hasPermission: () => true,
    };
    layoutState = { sidebarMode: true };
    fetchInfo.mockResolvedValue({ status: "ok" });
  });

  it("shows login when user is not authenticated", async () => {
    window.history.pushState({}, "", "/login");

    render(<App />);

    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(fetchInfo).not.toHaveBeenCalled();
    expect(screen.queryByText("Header")).not.toBeInTheDocument();
  });

  it("renders authenticated shell and fetches info", async () => {
    authState = {
      ...authState,
      isAuthenticated: true,
      user: { id: "u1", auth_provider: "password", needs_password_change: false },
    };

    render(<App />);

    expect(await screen.findByText(/Dashboard/)).toBeInTheDocument();
    expect(screen.getByText("Sidebar")).toBeInTheDocument();
    expect(screen.getByText("Header")).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchInfo).toHaveBeenCalledTimes(1);
    });
  });

  it("shows access denied for protected pages without permission", async () => {
    window.history.pushState({}, "", "/tempo");
    authState = {
      ...authState,
      isAuthenticated: true,
      user: { id: "u1", auth_provider: "password", needs_password_change: false },
      hasPermission: (permission) => permission !== "read:traces",
    };

    render(<App />);

    expect(await screen.findByText("You don't have access to this page.")).toBeInTheDocument();
  });

  it("hides forced password modal in oidc-only mode", async () => {
    authState = {
      ...authState,
      isAuthenticated: true,
      user: { id: "u1", auth_provider: "oidc", needs_password_change: true },
      authMode: { oidc_enabled: true, password_enabled: false },
    };

    render(<App />);

    expect(await screen.findByText(/Dashboard/)).toBeInTheDocument();
    expect(screen.queryByText("Change Password")).not.toBeInTheDocument();
  });
});
