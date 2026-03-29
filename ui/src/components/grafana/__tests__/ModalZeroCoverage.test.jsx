import { fireEvent, render, screen } from "@testing-library/react";
import DatasourceEditorModal from "../DatasourceEditorModal";
import FolderCreatorModal from "../FolderCreatorModal";

vi.mock("../../ui", () => ({
  Modal: ({ isOpen, title, children, footer }) =>
    isOpen ? (
      <div>
        <h1>{title}</h1>
        {children}
        <div>{footer}</div>
      </div>
    ) : null,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
}));

vi.mock("../VisibilitySelector", () => ({
  default: ({ onVisibilityChange, onSharedGroupIdsChange }) => (
    <div>
      <button onClick={() => onVisibilityChange("public")}>set-public</button>
      <button onClick={() => onSharedGroupIdsChange(["g1", "g2"])}>set-groups</button>
    </div>
  ),
}));

describe("Grafana zero-coverage modals", () => {
  it("covers datasource modal create/edit flows and field interactions", () => {
    const setDatasourceForm = vi.fn();
    const onSave = vi.fn();
    const onClose = vi.fn();

    const baseForm = {
      name: "",
      type: "prometheus",
      url: "",
      access: "proxy",
      apiKeyId: "",
      isDefault: false,
      visibility: "private",
      sharedGroupIds: ["g0"],
    };

    const user = {
      api_keys: [
        { id: "d", name: "default", is_default: true },
        { id: "k2", name: "team-key", is_default: false },
      ],
    };

    const { rerender } = render(
      <DatasourceEditorModal
        isOpen
        onClose={onClose}
        editingDatasource={null}
        datasourceForm={baseForm}
        setDatasourceForm={setDatasourceForm}
        user={user}
        groups={[{ id: "g1", name: "Ops" }]}
        onSave={onSave}
      />,
    );

    expect(setDatasourceForm).toHaveBeenCalled();
    expect(screen.getByText(/Create New Datasource/i)).toBeInTheDocument();

    const createButton = screen.getByRole("button", { name: /Create Datasource/i });
    expect(createButton).toBeDisabled();

    const textboxes = screen.getAllByRole("textbox");
    const comboboxes = screen.getAllByRole("combobox");

    fireEvent.change(textboxes[0], {
      target: { value: "My DS" },
    });
    fireEvent.change(comboboxes[0], {
      target: { value: "loki" },
    });
    fireEvent.change(textboxes[1], {
      target: { value: "http://loki" },
    });
    fireEvent.change(comboboxes[2], {
      target: { value: "d" },
    });
    fireEvent.click(screen.getByText("set-public"));
    fireEvent.click(screen.getByText("set-groups"));

    expect(setDatasourceForm).toHaveBeenCalled();

    rerender(
      <DatasourceEditorModal
        isOpen
        onClose={onClose}
        editingDatasource={{ uid: "x" }}
        datasourceForm={{ ...baseForm, name: "existing", url: "http://x", apiKeyId: "d" }}
        setDatasourceForm={setDatasourceForm}
        user={user}
        groups={[]}
        onSave={onSave}
      />,
    );

    expect(screen.getByText(/Edit Datasource/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Update Datasource/i })).toBeEnabled();
    expect(screen.getAllByRole("combobox")[0]).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Update Datasource/i }));
    expect(onSave).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("covers folder creator modal actions and reset-on-close behavior", () => {
    const onClose = vi.fn();
    const onCreate = vi.fn();
    const setFolderName = vi.fn();
    const setFolderVisibility = vi.fn();
    const setFolderSharedGroupIds = vi.fn();
    const setAllowDashboardWrites = vi.fn();

    render(
      <FolderCreatorModal
        isOpen
        onClose={onClose}
        editingFolder={null}
        folderName="My Folder"
        setFolderName={setFolderName}
        folderVisibility="private"
        setFolderVisibility={setFolderVisibility}
        folderSharedGroupIds={[]}
        setFolderSharedGroupIds={setFolderSharedGroupIds}
        allowDashboardWrites={false}
        setAllowDashboardWrites={setAllowDashboardWrites}
        groups={[{ id: "g1", name: "Ops" }]}
        onCreate={onCreate}
      />,
    );

    fireEvent.click(screen.getByText("set-public"));
    fireEvent.click(screen.getByText("set-groups"));
    expect(setFolderVisibility).toHaveBeenCalledWith("public");
    expect(setFolderSharedGroupIds).toHaveBeenCalledWith(["g1", "g2"]);

    fireEvent.change(screen.getByPlaceholderText(/Production Dashboards/i), {
      target: { value: "Edited" },
    });
    expect(setFolderName).toHaveBeenCalled();

    fireEvent.keyDown(screen.getByPlaceholderText(/Production Dashboards/i), {
      key: "Enter",
    });
    expect(onCreate).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(setAllowDashboardWrites).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(onClose).toHaveBeenCalled();
    expect(setFolderName).toHaveBeenCalledWith("");
    expect(setFolderVisibility).toHaveBeenCalledWith("private");
    expect(setFolderSharedGroupIds).toHaveBeenCalledWith([]);
    expect(setAllowDashboardWrites).toHaveBeenCalledWith(false);
  });
});
