import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const navigateMock = vi.fn();
const toast = { success: vi.fn(), error: vi.fn() };
const loginMock = vi.fn();
const startOIDCLoginMock = vi.fn();
const enrollMFAMock = vi.fn();
const verifyMFAMock = vi.fn();
const clearSetupTokenMock = vi.fn();
const setSetupTokenMock = vi.fn();
const copyToClipboardMock = vi.fn();
const downloadFileMock = vi.fn();

const authState = {
  authMode: { oidc_enabled: false, password_enabled: true },
  authModeLoading: false,
  isAuthenticated: false,
  loading: false,
};

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    login: loginMock,
    startOIDCLogin: startOIDCLoginMock,
    authMode: authState.authMode,
    authModeLoading: authState.authModeLoading,
    isAuthenticated: authState.isAuthenticated,
    loading: authState.loading,
  }),
}));

vi.mock("../../api", () => ({
  enrollMFA: (...args) => enrollMFAMock(...args),
  verifyMFA: (...args) => verifyMFAMock(...args),
  clearSetupToken: (...args) => clearSetupTokenMock(...args),
  setSetupToken: (...args) => setSetupTokenMock(...args),
}));

vi.mock("../../utils/helpers", () => ({
  copyToClipboard: (...args) => copyToClipboardMock(...args),
  downloadFile: (...args) => downloadFileMock(...args),
}));

vi.mock("../../components/auth/PasswordLoginForm", () => ({
  default: ({ username, password, onUsernameChange, onPasswordChange, onSubmit, loading }) => (
    <form onSubmit={onSubmit}>
      <input
        aria-label="username"
        value={username}
        onChange={(e) => onUsernameChange(e.target.value)}
      />
      <input
        aria-label="password"
        type="password"
        value={password}
        onChange={(e) => onPasswordChange(e.target.value)}
      />
      <button type="submit">{loading ? "Signing in..." : "Sign in"}</button>
    </form>
  ),
}));

vi.mock("../../components/auth/OIDCLoginButton", () => ({
  default: ({ loading, onClick, providerLabel }) => (
    <button onClick={onClick}>{loading ? "Signing in with SSO..." : `Continue with ${providerLabel}`}</button>
  ),
}));

import LoginPage from "../LoginPage";

describe("LoginPage extra coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.authMode = { oidc_enabled: false, password_enabled: true };
    authState.authModeLoading = false;
    authState.isAuthenticated = false;
    authState.loading = false;

    loginMock.mockResolvedValue({});
    startOIDCLoginMock.mockResolvedValue({});
    enrollMFAMock.mockResolvedValue({ secret: "sec", otpauth_url: "otpauth://x" });
    verifyMFAMock.mockResolvedValue({ recovery_codes: ["r1", "r2"] });
    copyToClipboardMock.mockResolvedValue(true);
  });

  it("handles auth mode edge states and password form validation", async () => {
    authState.authMode = { oidc_enabled: false, password_enabled: false };
    const { rerender } = render(<LoginPage />);
    expect(screen.getByText(/Authentication is not configured/i)).toBeInTheDocument();

    authState.authMode = { oidc_enabled: false, password_enabled: true };
    rerender(<LoginPage />);

    fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));
    expect(screen.getByText(/Username is required/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("username"), { target: { value: "alice" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));
    expect(screen.getByText(/Password is required/i)).toBeInTheDocument();
  });

  it("handles OIDC button and oidc start failure", async () => {
    authState.authMode = { oidc_enabled: true, password_enabled: false };
    startOIDCLoginMock.mockRejectedValueOnce(new Error("oidc unavailable"));

    render(<LoginPage />);

    fireEvent.click(screen.getByRole("button", { name: /Continue with/i }));
    await waitFor(() => {
      expect(screen.getByText(/oidc unavailable/i)).toBeInTheDocument();
    });
  });

  it("handles mfa challenge verify and back actions", async () => {
    loginMock
      .mockRejectedValueOnce({ status: 401, body: { detail: "MFA required" } })
      .mockResolvedValueOnce({});

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Authentication code/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Verify/i }));
    expect(screen.getByText(/Enter the authentication code/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Use recovery code instead/i }));
    expect(screen.getByLabelText(/Recovery code/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Recovery code/i), { target: { value: "rc1" } });
    fireEvent.click(screen.getByRole("button", { name: /Verify/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenLastCalledWith("alice", "pw", "rc1");
      expect(navigateMock).toHaveBeenCalledWith("/");
    });
  });

  it("covers mfa setup flow with download/copy and cancel", async () => {
    loginMock.mockRejectedValueOnce({
      status: 401,
      body: { detail: { mfa_setup_required: true, setup_token: "setup-1" } },
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/Set up two-factor authentication/i)).toBeInTheDocument();
      expect(setSetupTokenMock).toHaveBeenCalledWith("setup-1");
    });

    fireEvent.click(screen.getByRole("button", { name: /Start MFA setup/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Verify/i })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Authentication code/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /Verify/i }));

    await waitFor(() => {
      expect(screen.getByText(/Recovery codes — save these now/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Copy codes/i }));
    fireEvent.click(screen.getByRole("button", { name: /Download/i }));

    await waitFor(() => {
      expect(copyToClipboardMock).toHaveBeenCalled();
      expect(downloadFileMock).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(clearSetupTokenMock).toHaveBeenCalled();
  });
});
