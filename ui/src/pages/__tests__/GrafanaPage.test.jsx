import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const toast = { success: vi.fn(), error: vi.fn() };
const mockAuthState = {
  user: { api_keys: [] },
  hasPermission: () => true,
};

vi.mock("../../hooks", async () => {
  const actual = await vi.importActual("../../hooks");
  return { ...actual };
});

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockAuthState,
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../api", () => ({
  searchDashboards: vi.fn().mockResolvedValue([]),
  createDashboard: vi.fn().mockResolvedValue({}),
  updateDashboard: vi.fn().mockResolvedValue({}),
  deleteDashboard: vi.fn().mockResolvedValue(true),
  getDatasources: vi.fn().mockResolvedValue([]),
  createDatasource: vi.fn().mockResolvedValue({}),
  updateDatasource: vi.fn().mockResolvedValue({}),
  deleteDatasource: vi.fn().mockResolvedValue(true),
  getFolders: vi.fn().mockResolvedValue([]),
  createFolder: vi.fn().mockResolvedValue({}),
  updateFolder: vi.fn().mockResolvedValue({}),
  deleteFolder: vi.fn().mockResolvedValue(true),
  toggleFolderHidden: vi.fn().mockResolvedValue({}),
  getGroups: vi.fn().mockResolvedValue([]),
  toggleDashboardHidden: vi.fn().mockResolvedValue({}),
  toggleDatasourceHidden: vi.fn().mockResolvedValue({}),
  getDashboard: vi.fn().mockResolvedValue(null),
  getDashboardFilterMeta: vi.fn().mockResolvedValue({}),
  getDatasourceFilterMeta: vi.fn().mockResolvedValue({}),
  createGrafanaBootstrapSession: vi.fn().mockResolvedValue({}),
  listMetricNames: vi.fn().mockResolvedValue({ metrics: [] }),
}));

vi.mock("../../components/ui", () => ({
  Button: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
  Modal: ({ isOpen, children }) => (isOpen ? <div>{children}</div> : null),
  Spinner: () => <div>Loading</div>,
  ConfirmDialog: ({
    isOpen,
    title,
    message,
    onConfirm,
    onClose,
    confirmText = "Confirm",
    cancelText = "Cancel",
  }) =>
    isOpen ? (
      <div>
        <div>{title}</div>
        <div>{message}</div>
        <button onClick={onConfirm}>{confirmText}</button>
        <button onClick={onClose}>{cancelText}</button>
      </div>
    ) : null,
}));

vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));

vi.mock("../../components/grafana/GrafanaTabs", () => ({
  default: ({ activeTab, onChange }) => (
    <div>
      <button
        className={activeTab === "dashboards" ? "text-sre-primary" : ""}
        onClick={() => onChange("dashboards")}
        role="tab"
      >
        Dashboards
      </button>
      <button
        className={activeTab === "datasources" ? "text-sre-primary" : ""}
        onClick={() => onChange("datasources")}
        role="tab"
      >
        Datasources
      </button>
      <button
        className={activeTab === "folders" ? "text-sre-primary" : ""}
        onClick={() => onChange("folders")}
        role="tab"
      >
        Folders
      </button>
    </div>
  ),
}));

vi.mock("../../components/grafana/GrafanaContent", () => ({
  default: ({
    activeTab,
    query,
    setQuery,
    openDashboardEditor,
    datasources = [],
    getDatasourceKeyName,
    onViewDatasourceMetrics,
  }) => (
    <div>
      <div data-testid="active-query">{query || ""}</div>
      <button
        onClick={() =>
          setQuery(activeTab === "dashboards" ? "dashboard-only" : "datasource-only")
        }
      >
        Set Active Query
      </button>
      <button onClick={() => openDashboardEditor()}>Open Dashboard Editor</button>
      {datasources.map((ds) => (
        <div key={ds.uid}>
          <div data-testid={`datasource-key-${ds.uid}`}>
            {getDatasourceKeyName?.(ds) || ""}
          </div>
          <button onClick={() => onViewDatasourceMetrics?.(ds)}>
            View Metrics {ds.uid}
          </button>
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../components/grafana/DashboardEditorModal", () => ({
  default: ({ isOpen, dashboardForm, setDashboardForm, onSave }) =>
    isOpen ? (
      <div>
        <button
          onClick={() =>
            setDashboardForm((prev) => ({
              ...prev,
              title: "CPU",
              datasourceUid: "ds-1",
              visibility: "tenant",
              sharedGroupIds: [],
            }))
          }
        >
          Configure Dashboard
        </button>
        <button onClick={() => onSave()}>Save Dashboard</button>
        <div>{dashboardForm.datasourceUid}</div>
      </div>
    ) : null,
}));

vi.mock("../../components/grafana/DatasourceEditorModal", () => ({
  default: () => null,
}));

vi.mock("../../components/grafana/FolderCreatorModal", () => ({
  default: () => null,
}));

import GrafanaPage from "../GrafanaPage";
import {
  createDashboard,
  createGrafanaBootstrapSession,
  getDashboardFilterMeta,
  getDatasourceFilterMeta,
  getDatasources,
  getFolders,
  getGroups,
  searchDashboards,
  listMetricNames,
  updateDatasource,
} from "../../api";

function setupDatasources(datasourceOverrides = {}) {
  getDatasources.mockResolvedValue([
    {
      uid: "ds-1",
      name: "Primary DS",
      type: "prometheus",
      visibility: "private",
      sharedGroupIds: [],
      is_owned: true,
      isDefault: false,
      ...datasourceOverrides,
    },
  ]);
}

describe("GrafanaPage state persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockAuthState.user = { api_keys: [] };
    searchDashboards.mockResolvedValue([]);
    getFolders.mockResolvedValue([]);
    getGroups.mockResolvedValue([]);
    getDashboardFilterMeta.mockResolvedValue({});
    getDatasourceFilterMeta.mockResolvedValue({});
    createGrafanaBootstrapSession.mockResolvedValue({});
    createDashboard.mockResolvedValue({});
    updateDatasource.mockResolvedValue({});
    setupDatasources();
  });

  it("loads activeTab from localStorage", async () => {
    localStorage.setItem("grafana-active-tab", JSON.stringify("datasources"));
    render(<GrafanaPage />);

    const dsBtn = await waitFor(() =>
      screen.getByRole("tab", { name: /Datasources/i }),
    );
    expect(dsBtn).toHaveClass("text-sre-primary");
  });

  it("persists activeTab changes", async () => {
    render(<GrafanaPage />);

    const init = JSON.parse(localStorage.getItem("grafana-active-tab"));
    expect([null, "dashboards"]).toContain(init);

    fireEvent.click(screen.getByRole("tab", { name: /Folders/i }));
    expect(JSON.parse(localStorage.getItem("grafana-active-tab"))).toBe(
      "folders",
    );
  });

  it("keeps dashboard and datasource search queries separate", async () => {
    render(<GrafanaPage />);

    expect(screen.getByTestId("active-query")).toHaveTextContent("");
    fireEvent.click(screen.getByText("Set Active Query"));
    expect(screen.getByTestId("active-query")).toHaveTextContent("dashboard-only");

    fireEvent.click(screen.getByRole("tab", { name: /Datasources/i }));
    await waitFor(() =>
      expect(screen.getByTestId("active-query")).toHaveTextContent(""),
    );
    fireEvent.click(screen.getByText("Set Active Query"));
    expect(screen.getByTestId("active-query")).toHaveTextContent(
      "datasource-only",
    );

    fireEvent.click(screen.getByRole("tab", { name: /Dashboards/i }));
    await waitFor(() =>
      expect(screen.getByTestId("active-query")).toHaveTextContent(
        "dashboard-only",
      ),
    );
  });

  it("prompts to sync datasource visibility only for owned non-default datasources", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    expect(
      await screen.findByText("Sync Datasource Visibility?"),
    ).toBeInTheDocument();
    expect(createDashboard).not.toHaveBeenCalled();
  });

  it("skips the sync prompt for the default datasource", async () => {
    setupDatasources({ isDefault: true });
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    await waitFor(() => expect(createDashboard).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Sync Datasource Visibility?")).not.toBeInTheDocument();
  });

  it("skips the sync prompt for datasources the user does not own", async () => {
    setupDatasources({ is_owned: false });
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    await waitFor(() => expect(createDashboard).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Sync Datasource Visibility?")).not.toBeInTheDocument();
  });

  it("resolves datasource key name from datasource scope metadata", async () => {
    mockAuthState.user = {
      api_keys: [
        { id: "k-active", key: "scope-active", name: "Active Key", is_enabled: true },
        { id: "k-target", key: "scope-target", name: "Target Key", is_enabled: true },
      ],
    };
    setupDatasources({
      orgId: 1,
      jsonData: { watchdogScopeKey: "scope-target", watchdogApiKeyId: "k-target" },
    });

    render(<GrafanaPage />);

    await waitFor(() =>
      expect(screen.getByTestId("datasource-key-ds-1")).toHaveTextContent(
        "Target Key",
      ),
    );
  });

  it("does not fall back to active/default key when datasource has no key mapping", async () => {
    mockAuthState.user = {
      api_keys: [
        { id: "k-default", key: "scope-default", name: "Default Key", is_default: true },
      ],
    };
    setupDatasources({
      orgId: 1,
      jsonData: {},
    });

    render(<GrafanaPage />);

    await waitFor(() =>
      expect(screen.getByTestId("datasource-key-ds-1")).toHaveTextContent(""),
    );
  });

  it("uses datasource scope key when loading datasource metrics", async () => {
    mockAuthState.user = {
      api_keys: [
        { id: "k-active", key: "scope-active", name: "Active Key", is_enabled: true },
        { id: "k-target", key: "scope-target", name: "Target Key", is_enabled: true },
      ],
    };
    setupDatasources({
      orgId: 1,
      jsonData: { watchdogScopeKey: "scope-target", watchdogApiKeyId: "k-target" },
    });

    render(<GrafanaPage />);

    await waitFor(() => expect(screen.getByText("View Metrics ds-1")).toBeInTheDocument());
    fireEvent.click(screen.getByText("View Metrics ds-1"));

    await waitFor(() => expect(listMetricNames).toHaveBeenCalledWith("scope-target"));
  });
});
