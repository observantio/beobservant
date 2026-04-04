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
  Modal: ({ isOpen, children, onClose, footer, title }) =>
    isOpen ? (
      <div>
        {title ? <div>{title}</div> : null}
        <button onClick={onClose}>Modal Close</button>
        {children}
        {footer}
      </div>
    ) : null,
  Spinner: () => <div>Loading</div>,
  ConfirmDialog: ({
    isOpen,
    title,
    message,
    onConfirm,
    onCancel,
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
    filters,
    setFilters,
    openDashboardEditor,
    openDatasourceEditor,
    onCreateFolder,
    onEditFolder,
    onSearch,
    onClearFilters,
    hasActiveFilters,
    onOpenGrafana,
    onDeleteDashboard,
    onToggleDashboardHidden,
    onDeleteDatasource,
    onToggleDatasourceHidden,
    onDeleteFolder,
    onToggleFolderHidden,
    datasources = [],
    getDatasourceKeyName,
    onViewDatasourceMetrics,
  }) => (
    <div>
      <div data-testid="active-query">{query || ""}</div>
      <div data-testid="active-filters">{JSON.stringify(filters || {})}</div>
      <div data-testid="has-active-filters">{String(Boolean(hasActiveFilters))}</div>
      <button
        onClick={() =>
          setQuery(activeTab === "dashboards" ? "dashboard-only" : "datasource-only")
        }
      >
        Set Active Query
      </button>
      <button
        onClick={() =>
          setFilters?.({
            teamId: "g-1",
            folderKey: "folder-1",
            showHidden: true,
          })
        }
      >
        Set Active Filters
      </button>
      <button onClick={() => openDashboardEditor()}>Open Dashboard Editor</button>
      <button onClick={() => openDatasourceEditor?.()}>Open Datasource Editor</button>
      <button onClick={() => onCreateFolder?.()}>Open Folder Creator</button>
      <button
        onClick={() =>
          onEditFolder?.({
            uid: "f-1",
            title: "Existing Folder",
            visibility: "group",
            sharedGroupIds: ["g-1"],
            allowDashboardWrites: true,
          })
        }
      >
        Open Folder Editor
      </button>
      <button onClick={() => onSearch?.({ preventDefault: () => {} })}>Search Action</button>
      <button onClick={() => onClearFilters?.()}>Clear Filters Action</button>
      <button onClick={() => onOpenGrafana?.("/explore")}>Open Grafana Path</button>
      <button
        onClick={() =>
          onDeleteDashboard?.({ uid: "db-1", title: "CPU Dashboard", is_hidden: false })
        }
      >
        Delete Dashboard Action
      </button>
      <button
        onClick={() =>
          onToggleDashboardHidden?.({ uid: "db-1", title: "CPU Dashboard", is_hidden: false })
        }
      >
        Hide Dashboard Action
      </button>
      <button
        onClick={() =>
          onToggleDashboardHidden?.({ uid: "db-2", title: "Old Dashboard", is_hidden: true })
        }
      >
        Unhide Dashboard Action
      </button>
      <button
        onClick={() =>
          onDeleteDatasource?.({ uid: "ds-1", name: "Primary DS", is_hidden: false })
        }
      >
        Delete Datasource Action
      </button>
      <button
        onClick={() =>
          onToggleDatasourceHidden?.({ uid: "ds-1", name: "Primary DS", is_hidden: false })
        }
      >
        Hide Datasource Action
      </button>
      <button
        onClick={() =>
          onToggleDatasourceHidden?.({ uid: "ds-2", name: "Legacy DS", is_hidden: true })
        }
      >
        Unhide Datasource Action
      </button>
      <button
        onClick={() =>
          onDeleteFolder?.({ uid: "f-1", title: "Folder One", is_hidden: false })
        }
      >
        Delete Folder Action
      </button>
      <button
        onClick={() =>
          onToggleFolderHidden?.({ uid: "f-1", title: "Folder One", is_hidden: false })
        }
      >
        Hide Folder Action
      </button>
      <button
        onClick={() =>
          onToggleFolderHidden?.({ uid: "f-2", title: "Folder Two", is_hidden: true })
        }
      >
        Unhide Folder Action
      </button>
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
        <button onClick={() => onSave("{invalid-json")}>Save Invalid Dashboard JSON</button>
        <div>{dashboardForm.datasourceUid}</div>
      </div>
    ) : null,
}));

vi.mock("../../components/grafana/DatasourceEditorModal", () => ({
  default: ({ isOpen, setDatasourceForm, onSave }) =>
    isOpen ? (
      <div>
        <button
          onClick={() =>
            setDatasourceForm((prev) => ({
              ...prev,
              name: "Mimir DS",
              type: "prometheus",
              url: "http://mimir",
              apiKeyId: "k-target",
              visibility: "private",
            }))
          }
        >
          Configure Datasource
        </button>
        <button
          onClick={() =>
            setDatasourceForm((prev) => ({
              ...prev,
              name: "No Key DS",
              type: "prometheus",
              url: "http://mimir",
              apiKeyId: "",
              visibility: "private",
            }))
          }
        >
          Configure Datasource Without Key
        </button>
        <button onClick={() => onSave()}>Save Datasource</button>
      </div>
    ) : null,
}));

vi.mock("../../components/grafana/FolderCreatorModal", () => ({
  default: ({ isOpen, setFolderName, onCreate, onClose }) =>
    isOpen ? (
      <div>
        <button onClick={() => setFolderName("Ops Folder")}>Configure Folder</button>
        <button onClick={() => onCreate()}>Save Folder</button>
        <button onClick={() => onClose?.()}>Close Folder Modal</button>
      </div>
    ) : null,
}));

import GrafanaPage from "../GrafanaPage";
import {
  createDatasource,
  createFolder,
  createDashboard,
  createGrafanaBootstrapSession,
  deleteDashboard,
  deleteDatasource,
  deleteFolder,
  getDashboardFilterMeta,
  getDatasourceFilterMeta,
  getDatasources,
  getFolders,
  getGroups,
  getDashboard,
  searchDashboards,
  listMetricNames,
  toggleDashboardHidden,
  toggleDatasourceHidden,
  toggleFolderHidden,
  updateDatasource,
  updateFolder,
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

describe("GrafanaPage state behavior", () => {
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
    updateFolder.mockResolvedValue({});
    setupDatasources();
  });

  it("does not load activeTab from localStorage", async () => {
    localStorage.setItem("grafana-active-tab", JSON.stringify("datasources"));
    render(<GrafanaPage />);

    const dashboardsBtn = await waitFor(() =>
      screen.getByRole("tab", { name: /Dashboards/i }),
    );
    expect(dashboardsBtn).toHaveClass("text-sre-primary");
  });

  it("does not persist activeTab changes", async () => {
    render(<GrafanaPage />);
    await waitFor(() => expect(getDatasources).toHaveBeenCalled());
    await screen.findByRole("tab", { name: /Dashboards/i });

    expect(localStorage.getItem("grafana-active-tab")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: /Folders/i }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Folders/i })).toHaveClass("text-sre-primary"),
    );
    expect(localStorage.getItem("grafana-active-tab")).toBeNull();
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

  it("resets grafana filters when switching tabs", async () => {
    render(<GrafanaPage />);

    expect(screen.getByTestId("active-filters")).toHaveTextContent(
      JSON.stringify({
        teamId: "",
        folderKey: "",
        showHidden: false,
      }),
    );

    expect(screen.getByTestId("has-active-filters")).toHaveTextContent("false");

    fireEvent.click(screen.getByText("Set Active Filters"));
    expect(screen.getByTestId("active-filters")).toHaveTextContent(
      JSON.stringify({
        teamId: "g-1",
        folderKey: "folder-1",
        showHidden: true,
      }),
    );
    expect(screen.getByTestId("has-active-filters")).toHaveTextContent("true");

    fireEvent.click(screen.getByRole("tab", { name: /Datasources/i }));
    await waitFor(() =>
      expect(screen.getByTestId("active-filters")).toHaveTextContent(
        JSON.stringify({
          teamId: "",
          folderKey: "",
          showHidden: false,
        }),
      ),
    );
    expect(screen.getByTestId("has-active-filters")).toHaveTextContent("false");
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

  it("saves dashboard only when sync prompt is cancelled", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    fireEvent.click(await screen.findByText("No, dashboard only"));

    await waitFor(() => {
      expect(createDashboard).toHaveBeenCalledTimes(1);
      expect(updateDatasource).not.toHaveBeenCalled();
    });
  });

  it("syncs datasource visibility when sync prompt is confirmed", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    fireEvent.click(await screen.findByText("Yes, sync datasource"));

    await waitFor(() => {
      expect(createDashboard).toHaveBeenCalledTimes(1);
      expect(updateDatasource).toHaveBeenCalledTimes(1);
    });
  });

  it("shows validation error when saving dashboard without datasource", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Save Dashboard"));

    expect(toast.error).toHaveBeenCalledWith(
      "Select a default datasource before saving the dashboard",
    );
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

  it("opens Grafana through bootstrap and falls back when bootstrap fails", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    createGrafanaBootstrapSession
      .mockResolvedValueOnce({ launch_url: "/launch?token=abc" })
      .mockRejectedValueOnce(new Error("bootstrap failed"));

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Grafana"));
    fireEvent.click(await screen.findByText("Continue to Grafana"));

    await waitFor(() => {
      expect(createGrafanaBootstrapSession).toHaveBeenCalledWith("/");
      expect(openSpy).toHaveBeenCalled();
    });

    fireEvent.click(await screen.findByText("Open Grafana Path"));
    fireEvent.click(await screen.findByText("Continue to Grafana"));

    await waitFor(() => {
      expect(createGrafanaBootstrapSession).toHaveBeenCalledWith("/explore");
      expect(openSpy).toHaveBeenCalledTimes(2);
    });

    openSpy.mockRestore();
  });

  it("does not bootstrap Grafana when launch confirmation is cancelled", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Grafana Path"));
    fireEvent.click(await screen.findByText("Cancel"));

    expect(createGrafanaBootstrapSession).not.toHaveBeenCalled();
  });

  it("executes hide and delete actions via confirm dialog", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Hide Dashboard Action"));
    fireEvent.click(await screen.findByText("Hide"));
    await waitFor(() => {
      expect(toggleDashboardHidden).toHaveBeenCalledWith("db-1", true);
    });

    fireEvent.click(await screen.findByText("Delete Dashboard Action"));
    fireEvent.click(await screen.findByText("Delete"));
    await waitFor(() => {
      expect(deleteDashboard).toHaveBeenCalledWith("db-1");
    });

    fireEvent.click(await screen.findByText("Hide Datasource Action"));
    fireEvent.click(await screen.findByText("Hide"));
    await waitFor(() => {
      expect(toggleDatasourceHidden).toHaveBeenCalledWith("ds-1", true);
    });

    fireEvent.click(await screen.findByText("Delete Datasource Action"));
    fireEvent.click(
      await screen.findByRole("button", { name: /^Delete(?: Anyway)?$/i }),
    );
    await waitFor(() => {
      expect(deleteDatasource).toHaveBeenCalledWith("ds-1");
    });

    fireEvent.click(await screen.findByText("Hide Folder Action"));
    fireEvent.click(await screen.findByText("Hide"));
    await waitFor(() => {
      expect(toggleFolderHidden).toHaveBeenCalledWith("f-1", true);
    });

    fireEvent.click(await screen.findByText("Unhide Dashboard Action"));
    fireEvent.click(await screen.findByText("Unhide"));
    await waitFor(() => {
      expect(toggleDashboardHidden).toHaveBeenCalledWith("db-2", false);
    });

    fireEvent.click(await screen.findByText("Unhide Datasource Action"));
    fireEvent.click(await screen.findByText("Unhide"));
    await waitFor(() => {
      expect(toggleDatasourceHidden).toHaveBeenCalledWith("ds-2", false);
    });

    fireEvent.click(await screen.findByText("Unhide Folder Action"));
    fireEvent.click(await screen.findByText("Unhide"));
    await waitFor(() => {
      expect(toggleFolderHidden).toHaveBeenCalledWith("f-2", false);
    });

    fireEvent.click(await screen.findByText("Delete Folder Action"));
    fireEvent.click(await screen.findByText("Delete"));
    await waitFor(() => {
      expect(deleteFolder).toHaveBeenCalledWith("f-1");
    });
  });

  it("surfaces errors from hide actions", async () => {
    toggleDashboardHidden.mockRejectedValueOnce(new Error("toggle failed"));

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Hide Dashboard Action"));
    fireEvent.click(await screen.findByText("Hide"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it("shows delete-anyway warning when datasource is linked to dashboards", async () => {
    searchDashboards.mockResolvedValue([
      { uid: "db-linked", title: "Linked Dashboard", slug: "linked" },
    ]);
    getDashboard.mockResolvedValue({
      dashboard: { panels: [{ datasourceUid: "ds-1" }] },
    });

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Delete Datasource Action"));
    expect(
      await screen.findByText("Datasource Linked to Dashboards"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Delete Anyway/i }));
    await waitFor(() => {
      expect(deleteDatasource).toHaveBeenCalledWith("ds-1");
    });
  });

  it("shows invalid json error when saving dashboard from malformed JSON", async () => {
    setupDatasources({ isDefault: true });
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Dashboard Editor"));
    fireEvent.click(screen.getByText("Configure Dashboard"));
    fireEvent.click(screen.getByText("Save Invalid Dashboard JSON"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Invalid JSON — please fix and try again");
      expect(createDashboard).not.toHaveBeenCalled();
    });
  });

  it("requires API key for multi-tenant datasource types", async () => {
    mockAuthState.user = { api_keys: [] };
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Datasource Editor"));
    fireEvent.click(screen.getByText("Configure Datasource Without Key"));
    fireEvent.click(screen.getByText("Save Datasource"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "API key is required for Prometheus, Loki, and Tempo datasources",
      );
      expect(createDatasource).not.toHaveBeenCalled();
    });
  });

  it("saves datasource and folder through editor modals", async () => {
    mockAuthState.user = {
      api_keys: [
        { id: "k-target", key: "scope-target", name: "Target Key", is_enabled: true },
      ],
    };

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Datasource Editor"));
    fireEvent.click(await screen.findByText("Configure Datasource"));
    fireEvent.click(await screen.findByText("Save Datasource"));

    await waitFor(() => {
      expect(createDatasource).toHaveBeenCalled();
    });

    fireEvent.click(await screen.findByText("Open Folder Creator"));
    fireEvent.click(await screen.findByText("Configure Folder"));
    fireEvent.click(await screen.findByText("Save Folder"));

    await waitFor(() => {
      expect(createFolder).toHaveBeenCalledWith(
        "Ops Folder",
        expect.any(String),
        expect.any(Boolean),
      );
    });
  });

  it("shows datasource metrics error and empty states", async () => {
    listMetricNames
      .mockRejectedValueOnce(new Error("metrics failed"))
      .mockResolvedValueOnce({ metrics: [] });

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("View Metrics ds-1"));
    await waitFor(() => {
      expect(screen.getByText(/metrics failed/i)).toBeInTheDocument();
    });

    fireEvent.click(await screen.findByText("View Metrics ds-1"));
    await waitFor(() => {
      expect(screen.getByText(/No metrics found/i)).toBeInTheDocument();
    });
  });

  it("renders datasource metrics list and closes modal", async () => {
    listMetricNames.mockResolvedValue({ metrics: ["z_metric", "a_metric"] });

    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("View Metrics ds-1"));
    await waitFor(() => {
      expect(screen.getByText("a_metric")).toBeInTheDocument();
      expect(screen.getByText("z_metric")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Modal Close"));
    await waitFor(() => {
      expect(screen.queryByText("a_metric")).not.toBeInTheDocument();
    });

    fireEvent.click(await screen.findByText("View Metrics ds-1"));
    await waitFor(() => {
      expect(screen.getByText("a_metric")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Close$/i }));
    await waitFor(() => {
      expect(screen.queryByText("a_metric")).not.toBeInTheDocument();
    });
  });

  it("updates an existing folder from folder editor", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Folder Editor"));
    fireEvent.click(screen.getByText("Configure Folder"));
    fireEvent.click(screen.getByText("Save Folder"));

    await waitFor(() => {
      expect(updateFolder).toHaveBeenCalledWith(
        "f-1",
        expect.objectContaining({ title: "Ops Folder" }),
        expect.any(String),
      );
    });
  });

  it("resets folder draft when closing folder modal", async () => {
    render(<GrafanaPage />);

    fireEvent.click(await screen.findByText("Open Folder Creator"));
    fireEvent.click(screen.getByText("Configure Folder"));
    fireEvent.click(screen.getByText("Close Folder Modal"));

    fireEvent.click(screen.getByText("Open Folder Creator"));
    fireEvent.click(screen.getByText("Save Folder"));

    await waitFor(() => {
      expect(createFolder).not.toHaveBeenCalled();
    });
  });
});
