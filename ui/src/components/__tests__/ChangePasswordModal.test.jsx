import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChangePasswordModal from "../ChangePasswordModal";

const toast = { success: vi.fn(), error: vi.fn() };
const updateUserPassword = vi.fn();
let authState = {
  authMode: { oidc_enabled: false, password_enabled: true },
};

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("../../api", () => ({
  updateUserPassword: (...args) => updateUserPassword(...args),
}));

describe("ChangePasswordModal", () => {
  beforeEach(() => {
    authState = {
      authMode: { oidc_enabled: false, password_enabled: true },
    };
    vi.clearAllMocks();
    updateUserPassword.mockResolvedValue({ ok: true });
  });

  it("shows OIDC-managed password messaging instead of password fields in OIDC-only mode", () => {
    authState = {
      authMode: { oidc_enabled: true, password_enabled: false },
    };
    const onClose = vi.fn();

    render(
      <ChangePasswordModal
        isOpen
        onClose={onClose}
        userId="u1"
        authProvider="oidc"
        isForced
      />,
    );

    expect(screen.getByText(/OIDC manages passwords/i)).toBeInTheDocument();
    expect(
      screen.getByText(/password fields are unavailable in OIDC-only mode/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Current Password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New Password")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows validation errors for short and mismatched passwords", () => {
    render(
      <ChangePasswordModal
        isOpen
        onClose={vi.fn()}
        userId="u1"
        authProvider="local"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/Enter current password/i), {
      target: { value: "old" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/Enter new password \(min 12 characters\)/i),
      { target: { value: "short" } },
    );
    fireEvent.change(screen.getByPlaceholderText(/Confirm new password/i), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Update Password/i }));
    expect(toast.error).toHaveBeenCalledWith(
      "Password must be at least 12 characters long",
    );

    fireEvent.change(
      screen.getByPlaceholderText(/Enter new password \(min 12 characters\)/i),
      { target: { value: "123456789012" } },
    );
    fireEvent.change(screen.getByPlaceholderText(/Confirm new password/i), {
      target: { value: "123456789013" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Update Password/i }));
    expect(toast.error).toHaveBeenCalledWith("New passwords do not match");
  });

  it("completes forced-password flow and walkthrough", async () => {
    const onClose = vi.fn();
    render(
      <ChangePasswordModal
        isOpen
        onClose={onClose}
        userId="u1"
        authProvider="oidc"
        isForced
      />,
    );

    fireEvent.change(
      screen.getByPlaceholderText(/Enter new password \(min 12 characters\)/i),
      { target: { value: "verysecurepass" } },
    );
    fireEvent.change(screen.getByPlaceholderText(/Confirm new password/i), {
      target: { value: "verysecurepass" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Update Password/i }));

    await waitFor(() => {
      expect(updateUserPassword).toHaveBeenCalledWith("u1", {
        current_password: null,
        new_password: "verysecurepass",
      });
      expect(toast.success).toHaveBeenCalledWith("Password updated successfully");
      expect(screen.getByRole("button", { name: /Next/i })).toBeInTheDocument();
    });

    for (let i = 0; i < 7; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    }
    fireEvent.click(screen.getByRole("button", { name: /Done/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
