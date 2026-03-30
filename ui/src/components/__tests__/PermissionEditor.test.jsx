import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PermissionEditor from "../PermissionEditor";
import * as api from "../../api";
import { USER_ROLES } from "../../utils/constants";
import { ToastProvider } from "../../contexts/ToastContext";

vi.mock("../../api", () => ({
  getPermissions: vi.fn(),
  getRoleDefaults: vi.fn(),
  updateUserPermissions: vi.fn(),
}));

const authUser = {
  id: "admin-1",
  role: "admin",
  permissions: ["manage:users"],
  is_superuser: false,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: authUser }),
}));

describe("PermissionEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authUser.id = "admin-1";
    authUser.role = "admin";
    authUser.permissions = ["manage:users"]; // intentionally limited to test role filtering
    authUser.is_superuser = false;

    api.getPermissions.mockResolvedValue([
      {
        id: "perm-read-users",
        name: "Read Users",
        resource_type: "users",
        description: "View users",
      },
      {
        id: "perm-write-users",
        name: "Write Users",
        resource_type: "users",
        description: "Modify users",
      },
      {
        id: "perm-read-alerts",
        name: "Read Alerts",
        resource_type: "alerts",
        description: "View alerts",
      },
    ]);
    api.getRoleDefaults.mockResolvedValue({
      viewer: ["Read Users"],
      user: ["Read Users", "Read Alerts"],
      admin: ["Read Users", "Read Alerts", "Write Users"],
      provisioning: [],
    });
    api.updateUserPermissions.mockResolvedValue({ ok: true });
  });

  it("renders without crashing and shows role options from constants", async () => {
    const user = {
      id: "u1",
      username: "bob",
      role: "user",
      group_ids: [],
      direct_permissions: [],
    };
    render(
      <ToastProvider>
        <PermissionEditor
          user={user}
          groups={[]}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />
      </ToastProvider>,
    );

    await waitFor(() => expect(api.getPermissions).toHaveBeenCalled());
    const roleSelect = screen.getByLabelText(/Role/i);
    expect(roleSelect).toBeInTheDocument();

    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThan(0);
    const optionValues = options.map((opt) => opt.getAttribute("value"));
    optionValues.forEach((value) => {
      expect(USER_ROLES.some((r) => r.value === value)).toBe(true);
    });

    expect(roleSelect).toHaveValue("provisioning");
  });

  it("supports group selection/search, permission toggles, and successful save", async () => {
    const onClose = vi.fn();
    const onSave = vi.fn().mockResolvedValue({ ok: true });
    const user = {
      id: "u1",
      username: "bob",
      role: "viewer",
      group_ids: ["g2"],
      direct_permissions: ["Read Alerts"],
    };
    const groups = [
      {
        id: "g1",
        name: "Ops",
        description: "Operations group",
        permissions: [{ id: "p1", display_name: "Read Users" }],
      },
      {
        id: "g2",
        name: "Platform",
        description: "Platform group",
        permissions: ["Read Alerts"],
      },
      {
        id: "g3",
        name: "Security",
        permissions: [],
      },
      { id: "g4", name: "DevEx", permissions: [] },
      { id: "g5", name: "SRE", permissions: [] },
      { id: "g6", name: "Audit", permissions: [] },
    ];

    render(
      <ToastProvider>
        <PermissionEditor user={user} groups={groups} onClose={onClose} onSave={onSave} />
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(api.getRoleDefaults).toHaveBeenCalled();
      expect(screen.getByText(/Group Membership/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/Search groups/i), {
      target: { value: "ops" },
    });
    expect(screen.getByText("Ops")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "" }));

    const selectAllButtons = screen.getAllByRole("button", {
      name: "Select All",
    });
    const clearButtons = screen.getAllByRole("button", { name: "Clear" });
    fireEvent.click(selectAllButtons.find((b) => !b.disabled) || selectAllButtons[0]);
    fireEvent.click(clearButtons.find((b) => !b.disabled) || clearButtons[0]);

    const readUsersCheckbox = screen.getByRole("checkbox", { name: /Read Users/i });
    fireEvent.click(readUsersCheckbox);

    fireEvent.click(screen.getByRole("button", { name: /Save Changes/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          role: expect.any(String),
          group_ids: expect.any(Array),
        }),
      );
      expect(api.updateUserPermissions).toHaveBeenCalledWith(
        "u1",
        expect.any(Array),
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("shows load failure and save failure paths", async () => {
    api.getPermissions.mockRejectedValueOnce(new Error("load failed"));
    const onClose = vi.fn();
    const onSave = vi.fn().mockRejectedValue(new Error("save failed"));
    const user = {
      id: "u2",
      username: "alice",
      role: "viewer",
      group_ids: [],
      direct_permissions: [],
    };

    const { rerender } = render(
      <ToastProvider>
        <PermissionEditor user={user} groups={[]} onClose={onClose} onSave={onSave} />
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(api.getPermissions).toHaveBeenCalled();
      expect(screen.getByText(/No groups available/i)).toBeInTheDocument();
    });

    api.getPermissions.mockResolvedValueOnce([]);
    api.getRoleDefaults.mockResolvedValueOnce({ viewer: [] });

    rerender(
      <ToastProvider>
        <PermissionEditor user={user} groups={[]} onClose={onClose} onSave={onSave} />
      </ToastProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Save Changes/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Save Changes/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
