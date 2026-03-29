import { beforeEach, describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen, within, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import CreateUserModal from "../CreateUserModal";
import * as api from "../../../api";
import * as helpers from "../../../utils/helpers";

expect.extend(toHaveNoViolations);

const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock("../../../contexts/ToastContext", () => ({
  useToast: vi.fn(() => ({ success: toastSuccess, error: toastError })),
}));
let authState = {
  authMode: { oidc_enabled: false, password_enabled: true },
  user: {
    role: "admin",
    permissions: ["auth:users:write", "auth:groups:read"],
    is_superuser: false,
  },
};
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => authState),
}));
vi.mock("../../../api", () => ({
  getRoleDefaults: vi.fn(async () => ({})),
  createUser: vi.fn(async () => ({ id: "u-1" })),
}));
vi.mock("../../../utils/helpers", async () => {
  const actual = await vi.importActual("../../../utils/helpers");
  return {
    ...actual,
    copyToClipboard: vi.fn(async () => true),
  };
});

describe("CreateUserModal — accessibility & keyboard interactions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState = {
      authMode: { oidc_enabled: false, password_enabled: true },
      user: {
        role: "admin",
        permissions: ["auth:users:write", "auth:groups:read"],
        is_superuser: false,
      },
    };
    api.getRoleDefaults.mockResolvedValue({
      admin: ["auth:users:write"],
      user: ["auth:groups:read"],
      viewer: [],
      provisioning: [],
    });
  });

  it("toggles group selection with Enter/Space and has no a11y violations", async () => {
    const groups = [
      { id: "g1", name: "Group One" },
      { id: "g2", name: "Group Two" },
    ];
    const { container } = render(
      <CreateUserModal
        isOpen
        onClose={() => {}}
        onCreated={() => {}}
        groups={groups}
        users={[]}
      />,
    );

    
    const labelEl = screen.getByText("Group One");
    const card = labelEl.closest('[role="checkbox"]');
    expect(card).toBeInTheDocument();
    expect(card).toHaveAttribute("tabindex");

    
    const innerCheckbox = within(card).getByRole("checkbox");
    expect(innerCheckbox).not.toBeChecked();

    
    card.focus();
    fireEvent.keyDown(card, { key: "Enter", code: "Enter", charCode: 13 });
    expect(innerCheckbox).toBeChecked();

    
    fireEvent.keyDown(card, { key: " ", code: "Space", charCode: 32 });
    expect(innerCheckbox).not.toBeChecked();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("hides password input when OIDC is enabled and local auth is disabled", () => {
    authState = {
      authMode: { oidc_enabled: true, password_enabled: false },
    };

    render(
      <CreateUserModal
        isOpen
        onClose={() => {}}
        onCreated={() => {}}
        groups={[]}
        users={[]}
      />,
    );

    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.getByText(/OIDC is enabled/i)).toBeInTheDocument();
    expect(
      screen.getByText(/reset the user password to generate a local password/i),
    ).toBeInTheDocument();
  });

  it("generates and copies password, then submits a valid user", async () => {
    const onClose = vi.fn();
    const onCreated = vi.fn();
    api.createUser.mockResolvedValue({ id: "u-2" });

    render(
      <CreateUserModal
        isOpen
        onClose={onClose}
        onCreated={onCreated}
        groups={[{ id: "g1", name: "Platform" }]}
        users={[]}
      />,
    );

    fireEvent.click(screen.getByLabelText("Generate password"));
    expect(toastSuccess).toHaveBeenCalledWith("Password generated successfully");

    fireEvent.click(screen.getByLabelText("Copy password"));
    await waitFor(() =>
      expect(helpers.copyToClipboard).toHaveBeenCalled(),
    );

    fireEvent.change(screen.getByPlaceholderText("Username"), {
      target: { value: "New.User" },
    });
    fireEvent.change(screen.getByPlaceholderText("me@company.com"), {
      target: { value: "new.user@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("••••••••••••••"), {
      target: { value: "StrongPass123!" },
    });
    fireEvent.change(screen.getByPlaceholderText("Full Name (optional)"), {
      target: { value: "New User" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    await waitFor(() => expect(api.createUser).toHaveBeenCalled());
    expect(api.createUser.mock.calls[0][0].username).toBe("new.user");
    expect(onCreated).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("shows API error toast on create failure", async () => {
    api.createUser.mockRejectedValueOnce({
      body: { message: "username already exists" },
    });

    render(
      <CreateUserModal
        isOpen
        onClose={() => {}}
        onCreated={() => {}}
        groups={[]}
        users={[]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Username"), {
      target: { value: "taken.user" },
    });
    fireEvent.change(screen.getByPlaceholderText("me@company.com"), {
      target: { value: "taken.user@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("••••••••••••••"), {
      target: { value: "StrongPass123!" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining("Error creating user: username already exists"),
      ),
    );
  });
});
