import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChangePasswordModal from "../ChangePasswordModal";

const toast = { success: vi.fn(), error: vi.fn() };
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
  updateUserPassword: vi.fn(),
}));

describe("ChangePasswordModal", () => {
  beforeEach(() => {
    authState = {
      authMode: { oidc_enabled: false, password_enabled: true },
    };
    vi.clearAllMocks();
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
});
