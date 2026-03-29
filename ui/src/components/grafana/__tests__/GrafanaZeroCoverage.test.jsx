import { fireEvent, render, screen } from "@testing-library/react";
import DashboardsTab from "../DashboardsTab";
import DatasourcesTab from "../DatasourcesTab";
import FoldersTab from "../FoldersTab";
import GrafanaTabs from "../GrafanaTabs";
import GrafanaContent from "../GrafanaContent";

const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock("../../ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ ...props }) => <input {...props} />,
  Badge: ({ children }) => <span>{children}</span>,
  Spinner: () => <div>Loading</div>,
}));

vi.mock("../../../contexts/ToastContext", () => ({
  useToast: () => ({ success: toastSuccess, error: toastError }),
}));

vi.mock("../../../utils/helpers", () => ({
  copyToClipboard: vi.fn().mockResolvedValue(true),
}));

describe("Grafana target components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("GrafanaTabs changes selected tab", () => {
    const onChange = vi.fn();
    render(<GrafanaTabs activeTab="dashboards" onChange={onChange} />);

    fireEvent.click(screen.getByRole("tab", { name: /Datasources/i }));
    expect(onChange).toHaveBeenCalledWith("datasources");
  });

  it("DashboardsTab renders, filters, and dashboard actions", async () => {
    vi.useFakeTimers();
    try {
      const setFilters = vi.fn();
      const setQuery = vi.fn();
      const openDashboardEditor = vi.fn();
      const onOpenGrafana = vi.fn();
      const onDeleteDashboard = vi.fn();
      const onToggleHidden = vi.fn();

      render(
        <DashboardsTab
          dashboards={[
            {
              uid: "d1",
              title: "Main Board",
              slug: "main-board",
              is_hidden: false,
              tags: ["prod"],
              visibility: "private",
              labels: { team: "sre" },
            },
          ]}
          groups={[{ id: "g1", name: "Ops" }]}
          folders={[{ uid: "f1", title: "Core" }]}
          query=""
          setQuery={setQuery}
          filters={{ teamId: "", folderKey: "", showHidden: false }}
          setFilters={setFilters}
          onSearch={(e) => e?.preventDefault?.()}
          onClearFilters={vi.fn()}
          hasActiveFilters
          openDashboardEditor={openDashboardEditor}
          onOpenGrafana={onOpenGrafana}
          onDeleteDashboard={onDeleteDashboard}
          onToggleHidden={onToggleHidden}
          dashboardKeyNamesByUid={{ d1: ["api-key-a"] }}
        />,
      );

      fireEvent.change(screen.getByPlaceholderText(/Search dashboards/i), {
        target: { value: "main" },
      });
      expect(setQuery).toHaveBeenCalled();

      fireEvent.click(screen.getByText("Filters"));
      fireEvent.click(screen.getByText("Apply"));

      fireEvent.click(screen.getByTitle("Hide"));
      fireEvent.click(screen.getByTitle("Open in Grafana"));
      fireEvent.click(screen.getByTitle("Edit"));
      fireEvent.click(screen.getByTitle("Delete"));
      fireEvent.click(screen.getByTitle("Copy dashboard link"));
      await vi.runAllTimersAsync();

      expect(onToggleHidden).toHaveBeenCalled();
      expect(onOpenGrafana).toHaveBeenCalled();
      expect(openDashboardEditor).toHaveBeenCalled();
      expect(onDeleteDashboard).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("DatasourcesTab and FoldersTab render empty and action branches", () => {
    const openDatasourceEditor = vi.fn();
    const onDeleteDatasource = vi.fn();
    const onToggleHidden = vi.fn();
    const onViewMetrics = vi.fn();

    const { rerender } = render(
      <DatasourcesTab
        datasources={[]}
        groups={[]}
        query=""
        setQuery={vi.fn()}
        filters={{ teamId: "", showHidden: false }}
        setFilters={vi.fn()}
        onSearch={(e) => e?.preventDefault?.()}
        onClearFilters={vi.fn()}
        hasActiveFilters={false}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={onDeleteDatasource}
        onToggleHidden={onToggleHidden}
        onViewMetrics={onViewMetrics}
        getDatasourceIcon={() => "I"}
        getDatasourceKeyName={() => "k"}
      />,
    );

    fireEvent.click(screen.getByText(/Add Your First Datasource/i));
    expect(openDatasourceEditor).toHaveBeenCalled();

    rerender(
      <FoldersTab
        folders={[
          { uid: "f1", title: "Folder 1", is_owned: false, is_hidden: true },
        ]}
        filters={{ showHidden: false }}
        setFilters={vi.fn()}
        onClearFilters={vi.fn()}
        hasActiveFilters
        onCreateFolder={vi.fn()}
        onEditFolder={vi.fn()}
        onDeleteFolder={vi.fn()}
        onToggleHidden={vi.fn()}
      />,
    );

    expect(screen.getByText(/Folders/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Search folders/i), {
      target: { value: "folder" },
    });
  });

  it("GrafanaContent switches between loading and tab content", () => {
    const baseProps = {
      dashboards: [],
      datasources: [],
      folders: [],
      groups: [],
      query: "",
      setQuery: vi.fn(),
      filters: {},
      setFilters: vi.fn(),
      onSearch: vi.fn(),
      onClearFilters: vi.fn(),
      hasActiveFilters: false,
      openDashboardEditor: vi.fn(),
      onOpenGrafana: vi.fn(),
      onDeleteDashboard: vi.fn(),
      onToggleDashboardHidden: vi.fn(),
      openDatasourceEditor: vi.fn(),
      onDeleteDatasource: vi.fn(),
      onToggleDatasourceHidden: vi.fn(),
      onViewDatasourceMetrics: vi.fn(),
      getDatasourceIcon: vi.fn(() => "I"),
      getDatasourceKeyName: vi.fn(() => "key"),
      dashboardKeyNamesByUid: {},
      onCreateFolder: vi.fn(),
      onEditFolder: vi.fn(),
      onDeleteFolder: vi.fn(),
      onToggleFolderHidden: vi.fn(),
    };

    const { rerender } = render(
      <GrafanaContent loading activeTab="dashboards" {...baseProps} />,
    );
    expect(screen.getByText("Loading")).toBeInTheDocument();

    rerender(<GrafanaContent loading={false} activeTab="dashboards" {...baseProps} />);
    expect(screen.getByText(/No Dashboards Found/i)).toBeInTheDocument();

    rerender(<GrafanaContent loading={false} activeTab="datasources" {...baseProps} />);
    expect(screen.getAllByText(/No Datasources Configured/i).length).toBeGreaterThan(0);

    rerender(<GrafanaContent loading={false} activeTab="folders" {...baseProps} />);
    expect(screen.getByText(/No Folders Available/i)).toBeInTheDocument();
  });
});
