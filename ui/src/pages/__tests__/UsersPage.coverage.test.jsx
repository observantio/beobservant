import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import UsersPage from "../UsersPage";
import * as api from "../../api";

let authState = {
  user: { id: "me", role: "admin" },
  hasPermission: () => true,
  authMode: { oidc_enabled: false },
};

const navigate = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();
const toast = { success: toastSuccess, error: toastError };

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
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
  Card: ({ children, title, subtitle }) => (
    <div>
      {title ? <h2>{title}</h2> : null}
      {subtitle ? <p>{subtitle}</p> : null}
      {children}
    </div>
  ),
  Button: ({ children, loading, ...props }) => (
    <button {...props} disabled={loading || props.disabled}>
      {children}
    </button>
  ),
  Input: ({ label, ...props }) =>
    label ? (
      <label>
        {label}
        <input aria-label={label} {...props} />
      </label>
    ) : (
      <input {...props} />
    ),
  Badge: ({ children }) => <span>{children}</span>,
  Spinner: () => <div>Loading</div>,
  Modal: ({ isOpen, title, children, footer }) =>
    isOpen ? (
      <div>
        {title ? <h2>{title}</h2> : null}
        {children}
        {footer}
      </div>
    ) : null,
  Checkbox: ({ label, ...props }) => (
    <label>
      <input type="checkbox" {...props} />
      {label}
    </label>
  ),
}));

vi.mock("../../components/users/CreateUserModal", () => ({
  default: ({ isOpen, onClose, onCreated }) =>
    isOpen ? (
      <div>
        <button onClick={onCreated}>created-user</button>
        <button onClick={onClose}>close-create-user</button>
      </div>
    ) : null,
}));
vi.mock("../../components/PermissionEditor", () => ({
  default: ({ onClose, onSave }) => (
    <div>
      <button onClick={() => onSave({ permissions: ["alerts:read"] })}>
        save-permissions
      </button>
      <button onClick={onClose}>close-permissions</button>
    </div>
  ),
}));
vi.mock("../../components/ConfirmModal", () => ({
  default: ({ isOpen, title, message, onConfirm, onCancel, confirmText }) =>
    isOpen ? (
      <div>
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>{confirmText || "Confirm"}</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));
vi.mock("../../components/HelpTooltip", () => ({ default: () => <span /> }));
vi.mock("../../components/TwoFactorModal", () => ({
  default: ({ isOpen }) => (isOpen ? <div>two-factor-modal</div> : null),
}));

vi.mock("../../api");

describe("UsersPage coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState = {
      user: { id: "me", role: "admin" },
      hasPermission: () => true,
      authMode: { oidc_enabled: false },
    };
    navigate.mockReset();
    toastSuccess.mockReset();
    toastError.mockReset();

    api.getUsers.mockResolvedValue([
      {
        id: "me",
        username: "me",
        email: "me@example.com",
        full_name: "Current User",
        role: "admin",
        is_active: true,
        group_ids: ["g1"],
        permissions: ["manage:users"],
      },
      {
        id: "u1",
        username: "alice",
        email: "alice@example.com",
        full_name: "Alice Smith",
        role: "user",
        is_active: false,
        must_setup_mfa: true,
        group_ids: ["g1", "g2"],
        permissions: ["alerts:read", "alerts:write"],
      },
    ]);
    api.getGroups.mockResolvedValue([{ id: "g1", name: "Platform" }]);
    api.updateUser.mockResolvedValue({ ok: true });
    api.deleteUser.mockResolvedValue({ ok: true });
    api.resetUserPasswordTemp.mockResolvedValue({
      email_sent: false,
      message: "Temporary password generated.",
    });
  });

  it("shows access denied view when user lacks management permission", () => {
    authState = {
      user: { id: "me", role: "viewer" },
      hasPermission: () => false,
    };

    render(<UsersPage />);
    expect(screen.getByText(/do not have permission to manage users/i)).toBeInTheDocument();
  });

  it("renders management page after loading data", async () => {
    render(<UsersPage />);

    await waitFor(() => {
      expect(api.getUsers).toHaveBeenCalled();
    });
    expect(screen.getByText(/User Management/i)).toBeInTheDocument();
    expect(screen.getByText(/Manage users, roles, and permissions/i)).toBeInTheDocument();

    const searchInput = await screen.findByPlaceholderText(
      /Search users by username, email, or name/i,
    );
    fireEvent.change(searchInput, {
      target: { value: "alice" },
    });
    fireEvent.click(
      await screen.findByRole("button", { name: /Search users/i }),
    );
    await waitFor(() => {
      expect(api.getUsers).toHaveBeenCalledTimes(2);
    });

    fireEvent.click(screen.getByRole("button", { name: /Groups/i }));
    expect(navigate).toHaveBeenCalledWith("/groups");

    expect(screen.getByText(/MFA required/i)).toBeInTheDocument();
    expect(screen.getByText(/Inactive/i)).toBeInTheDocument();
  });

  it("edits user profile and permissions", async () => {
    render(<UsersPage />);

    const editButton = await screen.findByRole("button", {
      name: /Edit alice/i,
    });

    fireEvent.click(editButton);
    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "AliceUpdated" },
    });
    fireEvent.change(await screen.findByLabelText("Full Name"), {
      target: { value: "Alice Updated" },
    });
    fireEvent.click(await screen.findByRole("checkbox", { name: /Active/i }));
    fireEvent.click(
      await screen.findByRole("checkbox", { name: /Require Two‑Factor/i }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /Save Changes/i }));

    await waitFor(() => {
      expect(api.updateUser).toHaveBeenCalledWith(
        "u1",
        expect.objectContaining({
          username: "aliceupdated",
          full_name: "Alice Updated",
          is_active: true,
          must_setup_mfa: false,
        }),
      );
      expect(toastSuccess).toHaveBeenCalledWith("User updated successfully");
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Edit permissions for alice/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /save-permissions/i }));

    await waitFor(() => {
      expect(api.updateUser).toHaveBeenCalledWith("u1", {
        permissions: ["alerts:read"],
      });
    });
  });

  it("handles delete and reset password flows", async () => {
    render(<UsersPage />);

    const deleteAction = await screen.findByRole("button", {
      name: /Delete alice/i,
    });

    fireEvent.click(deleteAction);
    fireEvent.click(await screen.findByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(api.deleteUser).toHaveBeenCalledWith("u1");
      expect(toastSuccess).toHaveBeenCalledWith("User deleted successfully");
    });

    fireEvent.click(
      await screen.findByRole("button", { name: /Reset password for alice/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Generate Temporary Password/i }),
    );

    await waitFor(() => {
      expect(api.resetUserPasswordTemp).toHaveBeenCalledWith("u1");
      expect(
        screen.getByRole("heading", { name: /^Temporary Password Generated$/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Email delivery was not sent/i),
    ).toBeInTheDocument();
  });

  it("shows OIDC note in reset password modal when oidc mode is enabled", async () => {
    authState = {
      user: { id: "me", role: "admin" },
      hasPermission: () => true,
      authMode: { oidc_enabled: true },
    };
    render(<UsersPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /Reset password for alice/i }),
    );

    expect(
      screen.getByText(/OIDC is currently enabled/i),
    ).toBeInTheDocument();
  });

  it("handles API error branches for load, delete and reset password", async () => {
    api.getUsers.mockRejectedValueOnce(new Error("load failed"));
    api.deleteUser.mockRejectedValueOnce(new Error("delete failed"));
    api.resetUserPasswordTemp.mockRejectedValueOnce(
      new Error("reset failed"),
    );
    render(<UsersPage />);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        "Error loading data: load failed",
      );
    });

    api.getUsers.mockResolvedValue([
      {
        id: "u1",
        username: "alice",
        email: "alice@example.com",
        role: "user",
      },
    ]);

    const searchInput = await screen.findByPlaceholderText(
      /Search users by username, email, or name/i,
    );
    fireEvent.change(searchInput, {
      target: { value: "alice" },
    });
    fireEvent.click(await screen.findByRole("button", { name: /Search users/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Delete alice/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Delete alice/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Error deleting user: delete failed");
    });

    fireEvent.click(screen.getByRole("button", { name: /Reset password for alice/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Generate Temporary Password/i }),
    );

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Error resetting password: reset failed");
    });
  });
});
