import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import TwoFactorModal from "../TwoFactorModal";

const refreshUser = vi.fn();
const enrollMFA = vi.fn();
const verifyMFA = vi.fn();
const disableMFA = vi.fn();

const authState = {
  user: { mfa_enabled: false },
};

vi.mock("../ui", () => ({
  Modal: ({ isOpen, title, children }) =>
    isOpen ? (
      <div>
        <h1>{title}</h1>
        {children}
      </div>
    ) : null,
  Button: ({ children, loading, ...props }) => (
    <button {...props}>{loading ? "loading" : children}</button>
  ),
  Input: (props) => <input {...props} />,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: authState.user, refreshUser }),
}));

vi.mock("../../api", () => ({
  enrollMFA: (...args) => enrollMFA(...args),
  verifyMFA: (...args) => verifyMFA(...args),
  disableMFA: (...args) => disableMFA(...args),
}));

describe("TwoFactorModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { mfa_enabled: false };
    enrollMFA.mockResolvedValue({
      otpauth_url: "otpauth://totp/Watchdog:test?secret=ABC123",
      secret: "ABC123",
    });
    verifyMFA.mockResolvedValue({ recovery_codes: ["r1", "r2"] });
    disableMFA.mockResolvedValue({ ok: true });
  });

  it("supports enroll and verify flow in setup mode", async () => {
    const onVerified = vi.fn();

    render(
      <TwoFactorModal
        isOpen
        onClose={vi.fn()}
        setupMode
        onVerified={onVerified}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Enable 2FA/i }));

    await waitFor(() => {
      expect(enrollMFA).toHaveBeenCalled();
      expect(screen.getByAltText(/TOTP QR code/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("123456"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Verify & Enable/i }));

    await waitFor(() => {
      expect(verifyMFA).toHaveBeenCalledWith("123456");
      expect(onVerified).toHaveBeenCalledWith({
        code: "123456",
        recoveryCodes: ["r1", "r2"],
      });
      expect(screen.getByText(/Recovery codes/i)).toBeInTheDocument();
    });
  });

  it("shows enrollment and verification errors", async () => {
    enrollMFA.mockRejectedValueOnce(new Error("enroll failed"));
    verifyMFA.mockRejectedValueOnce(new Error("bad code"));

    render(<TwoFactorModal isOpen onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Enable 2FA/i }));
    await waitFor(() => {
      expect(enrollMFA).toHaveBeenCalled();
      expect(screen.queryByAltText(/TOTP QR code/i)).not.toBeInTheDocument();
    });

    enrollMFA.mockResolvedValueOnce({
      otpauth_url: "otpauth://totp/Watchdog:test?secret=ABC123",
      secret: "ABC123",
    });
    fireEvent.click(screen.getByRole("button", { name: /Enable 2FA/i }));

    await waitFor(() => {
      expect(screen.getByAltText(/TOTP QR code/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("123456"), {
      target: { value: "111111" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Verify & Enable/i }));

    await waitFor(() => {
      expect(verifyMFA).toHaveBeenCalledWith("111111");
      expect(screen.getByRole("button", { name: /Verify & Enable/i })).toBeInTheDocument();
    });
  });

  it("supports disable flow when MFA is enabled", async () => {
    const onClose = vi.fn();
    authState.user = { mfa_enabled: true };

    const promptSpy = vi.spyOn(window, "prompt");
    promptSpy.mockReturnValueOnce("");

    const { rerender } = render(<TwoFactorModal isOpen onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: /Disable 2FA/i }));
    expect(disableMFA).not.toHaveBeenCalled();

    promptSpy.mockReturnValueOnce("current-password");
    fireEvent.click(screen.getByRole("button", { name: /Disable 2FA/i }));

    await waitFor(() => {
      expect(disableMFA).toHaveBeenCalledWith({ current_password: "current-password" });
      expect(refreshUser).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });

    disableMFA.mockRejectedValueOnce(new Error("disable failed"));
    rerender(<TwoFactorModal isOpen onClose={onClose} />);

    promptSpy.mockReturnValueOnce("another-password");
    fireEvent.click(screen.getByRole("button", { name: /Disable 2FA/i }));

    await waitFor(() => {
      expect(disableMFA).toHaveBeenCalledWith({ current_password: "another-password" });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    promptSpy.mockRestore();
  });
});
