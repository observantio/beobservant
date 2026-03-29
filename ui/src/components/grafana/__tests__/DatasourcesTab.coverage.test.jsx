import { fireEvent, render, screen } from "@testing-library/react";
import DatasourcesTab from "../DatasourcesTab";

vi.mock("../../ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  Input: (props) => <input {...props} />,
}));

describe("DatasourcesTab coverage", () => {
  it("renders empty state and create-first-datasource action", () => {
    const openDatasourceEditor = vi.fn();

    render(
      <DatasourcesTab
        datasources={[]}
        groups={[]}
        query=""
        setQuery={vi.fn()}
        filters={{ teamId: "", showHidden: false }}
        setFilters={vi.fn()}
        onSearch={vi.fn()}
        onClearFilters={vi.fn()}
        hasActiveFilters={false}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={vi.fn()}
        onToggleHidden={vi.fn()}
        onViewMetrics={vi.fn()}
        getDatasourceIcon={() => "I"}
        getDatasourceKeyName={() => ""}
      />,
    );

    expect(screen.getAllByText(/No Datasources Configured/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Add Your First Datasource/i }));
    expect(openDatasourceEditor).toHaveBeenCalledWith();
  });

  it("covers populated datasource cards, filters, and card actions", () => {
    const setQuery = vi.fn();
    const setFilters = vi.fn();
    const onSearch = vi.fn((e) => e?.preventDefault?.());
    const onClearFilters = vi.fn();
    const openDatasourceEditor = vi.fn();
    const onDeleteDatasource = vi.fn();
    const onToggleHidden = vi.fn();
    const onViewMetrics = vi.fn();

    render(
      <DatasourcesTab
        datasources={[
          {
            uid: "ds-1",
            name: "Mimir Main",
            type: "prometheus",
            url: "http://mimir",
            is_hidden: false,
            is_owned: false,
            isDefault: false,
            access: "proxy",
            visibility: "group",
            labels: { env: "prod" },
          },
          {
            uid: "ds-2",
            name: "Tempo Default",
            type: "tempo",
            url: "http://tempo",
            is_hidden: true,
            is_owned: true,
            isDefault: true,
            access: "direct",
            visibility: "private",
            labels: {},
          },
        ]}
        groups={[{ id: "g1", name: "Ops" }]}
        query=""
        setQuery={setQuery}
        filters={{ teamId: "", showHidden: false }}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={onClearFilters}
        hasActiveFilters
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={onDeleteDatasource}
        onToggleHidden={onToggleHidden}
        onViewMetrics={onViewMetrics}
        getDatasourceIcon={(t) => (t === "prometheus" ? "P" : "T")}
        getDatasourceKeyName={(ds) => (ds.uid === "ds-1" ? "key-main" : "")}
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText(/Search datasources by name, type, URL or UID/i),
      { target: { value: "tempo" } },
    );
    expect(setQuery).toHaveBeenCalled();

    const searchInput = screen.getByPlaceholderText(
      /Search datasources by name, type, URL or UID/i,
    );
    const form = searchInput.closest("form");
    fireEvent.submit(form);
    expect(onSearch).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /New Datasource/i }));
    expect(openDatasourceEditor).toHaveBeenCalledWith();

    fireEvent.click(screen.getByRole("button", { name: /Filters/i }));

    fireEvent.change(screen.getByLabelText(/Group:/i), {
      target: { value: "g1" },
    });
    fireEvent.click(screen.getByLabelText(/Show hidden datasources/i));
    expect(setFilters).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^Clear$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Apply$/i }));
    expect(onClearFilters).toHaveBeenCalled();

    fireEvent.click(screen.getByTitle("Hide"));
    fireEvent.click(screen.getAllByTitle("View Metrics")[0]);
    fireEvent.click(screen.getAllByTitle("Edit")[0]);
    fireEvent.click(screen.getAllByTitle("Delete")[0]);

    expect(onToggleHidden).toHaveBeenCalledWith(
      expect.objectContaining({ uid: "ds-1" }),
    );
    expect(onViewMetrics).toHaveBeenCalledWith(
      expect.objectContaining({ uid: "ds-1" }),
    );
    expect(openDatasourceEditor).toHaveBeenCalledWith(
      expect.objectContaining({ uid: "ds-1" }),
    );
    expect(onDeleteDatasource).toHaveBeenCalledWith(
      expect.objectContaining({ uid: "ds-1" }),
    );

    expect(screen.getAllByText(/Hidden/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/key-main/i)).toBeInTheDocument();
  });
});
