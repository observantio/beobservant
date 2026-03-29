import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import GroupsPage from "../GroupsPage";
import * as api from "../../api";

let canManageGroups = true;
const navigate = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();
const toast = { success: toastSuccess, error: toastError };

vi.mock("../../hooks/usePermissions", () => ({
  usePermissions: () => ({ canManageGroups }),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1" } }),
}));

vi.mock("../../contexts/LayoutModeContext", () => ({
  useLayoutMode: () => ({ sidebarMode: true }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../components/ui", () => ({
  Card: ({ children, className }) => <div className={className}>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ ...props }) => <input {...props} />,
  Modal: ({ isOpen, title, children, footer }) =>
    isOpen ? (
      <div>
        <h2>{title}</h2>
        {children}
        {footer}
      </div>
    ) : null,
  ConfirmDialog: ({ isOpen, title, message, onConfirm, onClose, confirmText }) =>
    isOpen ? (
      <div role="dialog">
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>{confirmText || "Confirm"}</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
  Alert: ({ children }) => <div>{children}</div>,
}));

vi.mock("../../components/HelpTooltip", () => ({ default: () => <span>?</span> }));

vi.mock("../../components/groups/MemberList", () => ({
  default: ({ users = [], toggleMember }) => (
    <div>
      <button onClick={() => toggleMember(users[0]?.id || "u2")}>toggle-member</button>
    </div>
  ),
}));

vi.mock("../../components/alertmanager/RuleEditorWizard", () => ({
  default: ({ onNext, onPrevious, onSubmit, onStepClick, showButtons = true }) => (
    <div>
      <button onClick={() => onStepClick?.(0)}>step-0</button>
      <button onClick={() => onStepClick?.(1)}>step-1</button>
      <button onClick={() => onStepClick?.(2)}>step-2</button>
      {showButtons !== false && (
        <>
          <button onClick={onPrevious}>prev</button>
          <button onClick={onNext}>next</button>
          <button onClick={onSubmit}>submit</button>
        </>
      )}
    </div>
  ),
}));

vi.mock("../../components/groups/GroupForm", () => ({
  default: ({ formData, setFormData }) => (
    <input
      aria-label="group-name"
      value={formData.name || ""}
      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
    />
  ),
}));

vi.mock("../../components/groups/GroupPermissions", () => ({
  default: ({ togglePermission, addPerms, removePerms }) => (
    <div>
      <button onClick={() => togglePermission("read:logs")}>toggle-perm</button>
      <button onClick={() => addPerms([{ name: "read:logs" }])}>add-perms</button>
      <button onClick={() => removePerms([{ name: "read:logs" }])}>remove-perms</button>
    </div>
  ),
}));

vi.mock("../../components/groups/GroupCard", () => ({
  default: ({ group, onOpenPermissions, onEdit, onDelete }) => (
    <div>
      <span>{group.name}</span>
      <button onClick={() => onOpenPermissions(group)}>open-permissions</button>
      <button onClick={() => onEdit(group)}>open-edit</button>
      <button onClick={() => onDelete(group)}>open-delete</button>
    </div>
  ),
}));

vi.mock("../../api");

describe("GroupsPage coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    canManageGroups = true;

    api.getGroups.mockResolvedValue([{ id: "g1", name: "Ops", permissions: [] }]);
    api.getPermissions.mockResolvedValue([{ id: "p1", name: "read:logs", resource_type: "logs" }]);
    api.getUsers.mockResolvedValue([
      { id: "u1", username: "owner", group_ids: [] },
      { id: "u2", username: "alice", group_ids: ["g1"] },
    ]);

    api.createGroup.mockResolvedValue({ id: "g2" });
    api.updateGroup.mockResolvedValue({ ok: true });
    api.deleteGroup.mockResolvedValue({ ok: true });
    api.updateGroupPermissions.mockResolvedValue({ ok: true });
    api.updateGroupMembers.mockResolvedValue({ ok: true });
  });

  it("shows access denied when permissions are missing", async () => {
    canManageGroups = false;
    render(<GroupsPage />);
    expect(await screen.findByText(/Access Denied/i)).toBeInTheDocument();
  });

  it("covers search, navigation, create wizard and empty-state paths", async () => {
    api.getGroups.mockResolvedValueOnce([]).mockResolvedValueOnce([{ id: "g1", name: "Ops", permissions: [] }]);

    render(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText(/No groups yet/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Create Group/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Group name is required");
    });

    fireEvent.change(screen.getByLabelText("group-name"), { target: { value: "Platform" } });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /toggle-perm/i }));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /toggle-member/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => {
      expect(api.createGroup).toHaveBeenCalledWith(expect.objectContaining({ name: "Platform" }));
      expect(api.updateGroupPermissions).toHaveBeenCalledWith("g2", ["read:logs"]);
      expect(api.updateGroupMembers).toHaveBeenCalledWith("g2", expect.arrayContaining(["u1", "u2"]));
      expect(toastSuccess).toHaveBeenCalledWith("Group created successfully");
    });

    const search = screen.getByPlaceholderText(/Search groups by name or description/i);
    fireEvent.change(search, { target: { value: "ops" } });
    fireEvent.keyDown(search, { key: "Enter" });

    await waitFor(() => {
      expect(api.getGroups).toHaveBeenCalledWith({ q: "ops" });
    });

    fireEvent.click(screen.getByRole("button", { name: /Users/i }));
    expect(navigate).toHaveBeenCalledWith("/users");
  });

  it("covers edit, permissions, and delete confirmation flows", async () => {
    render(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Ops")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /open-edit/i }));
    fireEvent.change(screen.getByLabelText("group-name"), { target: { value: "Ops Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /toggle-member/i }));
    fireEvent.click(screen.getByRole("button", { name: /Save Changes/i }));

    await waitFor(() => {
      expect(api.updateGroup).toHaveBeenCalledWith("g1", expect.objectContaining({ name: "Ops Updated" }));
      expect(api.updateGroupMembers).toHaveBeenCalledWith("g1", expect.any(Array));
      expect(toastSuccess).toHaveBeenCalledWith("Group updated successfully");
    });

    fireEvent.click(screen.getByRole("button", { name: /open-permissions/i }));
    fireEvent.click(screen.getByRole("button", { name: /toggle-perm/i }));
    fireEvent.click(screen.getByRole("button", { name: /toggle-member/i }));
    fireEvent.click(screen.getByRole("button", { name: /Save Permissions/i }));

    await waitFor(() => {
      expect(api.updateGroupPermissions).toHaveBeenCalledWith("g1", ["read:logs"]);
      expect(api.updateGroupMembers).toHaveBeenCalledWith("g1", expect.any(Array));
      expect(toastSuccess).toHaveBeenCalledWith("Permissions updated successfully");
    });

    fireEvent.click(screen.getByRole("button", { name: /open-delete/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(api.deleteGroup).toHaveBeenCalledWith("g1");
      expect(toastSuccess).toHaveBeenCalledWith("Group deleted successfully");
    });
  });

  it("covers fetch and create rollback failures", async () => {
    api.getGroups.mockRejectedValueOnce(new Error("load failed"));
    api.createGroup.mockResolvedValueOnce({ id: "g-rollback" });
    api.updateGroupPermissions.mockRejectedValueOnce(new Error("perm failed"));

    render(<GroupsPage />);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Failed to load groups: load failed");
    });

    fireEvent.click(screen.getByRole("button", { name: /Create Group/i }));
    fireEvent.change(screen.getByLabelText("group-name"), { target: { value: "Rollback Group" } });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /toggle-perm/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));

    await waitFor(() => {
      expect(api.deleteGroup).toHaveBeenCalledWith("g-rollback");
      expect(toastError).toHaveBeenCalledWith("Failed to create group: perm failed");
    });
  });
});
