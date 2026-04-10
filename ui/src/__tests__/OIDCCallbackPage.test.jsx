import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import OIDCCallbackPage from "../pages/OIDCCallbackPage";
import * as api from "../api";
const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    finishOIDCLogin: async ({ code, state, mfaCode = null, mfaChallengeId = null }) => {
      return await api.exchangeOIDCCode(code, "", {
        state,
        mfa_code: mfaCode,
        mfa_challenge_id: mfaChallengeId,
      });
    },
  }),
}));

describe("OIDCCallbackPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("parses querystring before hash correctly", async () => {
    const fakeHref =
      "http://localhost:5173/auth/callback?code=foo&state=bar#/login";
    Object.defineProperty(window, "location", {
      value: { href: fakeHref },
      writable: true,
    });
    vi.spyOn(api, "exchangeOIDCCode").mockResolvedValue({});

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(api.exchangeOIDCCode).toHaveBeenCalled();
      const call = api.exchangeOIDCCode.mock.calls[0];
      expect(call[0]).toBe("foo");
      expect(call[2].state).toBe("bar");
    });
  });

  it("navigates to home after successful callback", async () => {
    Object.defineProperty(window, "location", {
      value: { href: "http://localhost:5173/auth/callback?code=a&state=b" },
      writable: true,
    });
    const replaceStateSpy = vi.spyOn(window.history, "replaceState");
    vi.spyOn(api, "exchangeOIDCCode").mockResolvedValue({});

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(replaceStateSpy).toHaveBeenCalledWith({}, "", "/");
      expect(navigateMock).toHaveBeenCalledWith("/", { replace: true });
    });
  });

  it("shows missing params error and back-to-login action", async () => {
    Object.defineProperty(window, "location", {
      value: { href: "http://localhost:5173/auth/callback" },
      writable: true,
    });

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Missing OIDC callback parameters/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Back to login/i }));
    expect(navigateMock).toHaveBeenCalledWith("/login", { replace: true });
  });

  it("shows oidc provider error description", async () => {
    Object.defineProperty(window, "location", {
      value: {
        href: "http://localhost:5173/auth/callback?error=access_denied&error_description=Denied",
      },
      writable: true,
    });

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Denied")).toBeInTheDocument();
    expect(api.exchangeOIDCCode).not.toHaveBeenCalled();
  });

  it("shows finish login failure message", async () => {
    Object.defineProperty(window, "location", {
      value: {
        href: "http://localhost:5173/auth/callback?code=foo&state=bar",
      },
      writable: true,
    });
    vi.spyOn(api, "exchangeOIDCCode").mockRejectedValueOnce(
      new Error("OIDC login failed hard"),
    );

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/OIDC login failed hard/i)).toBeInTheDocument();
  });

  it("redirects to mfa setup flow when oidc challenge requires setup", async () => {
    Object.defineProperty(window, "location", {
      value: {
        href: "http://localhost:5173/auth/callback?code=foo&state=bar",
      },
      writable: true,
    });
    const setSetupTokenSpy = vi
      .spyOn(api, "setSetupToken")
      .mockImplementation(() => {});
    vi.spyOn(api, "exchangeOIDCCode").mockRejectedValueOnce({
      status: 401,
      body: { detail: { mfa_setup_required: true, setup_token: "setup-42" } },
    });

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(setSetupTokenSpy).toHaveBeenCalledWith("setup-42");
      expect(navigateMock).toHaveBeenCalledWith(
        "/login?mfa_setup=required",
        { replace: true },
      );
    });
  });

  it("prompts for mfa code and completes oidc callback on verification", async () => {
    Object.defineProperty(window, "location", {
      value: {
        href: "http://localhost:5173/auth/callback?code=foo&state=bar",
      },
      writable: true,
    });
    const replaceStateSpy = vi.spyOn(window.history, "replaceState");
    vi.spyOn(api, "exchangeOIDCCode")
      .mockRejectedValueOnce({
        status: 401,
        body: { detail: { mfa_required: true, mfa_challenge_id: "challenge-1" } },
      })
      .mockResolvedValueOnce({});

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: /Verify MFA/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/MFA code/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Verify and continue/i }));

    await waitFor(() => {
      expect(api.exchangeOIDCCode.mock.calls.length).toBeGreaterThanOrEqual(2);
      const hasMfaRetry = api.exchangeOIDCCode.mock.calls.some(
        (call) =>
          call?.[2]?.state === "bar" &&
          call?.[2]?.mfa_code === "123456" &&
          call?.[2]?.mfa_challenge_id === "challenge-1",
      );
      expect(hasMfaRetry).toBe(true);
      expect(replaceStateSpy).toHaveBeenCalledWith({}, "", "/");
      expect(navigateMock).toHaveBeenCalledWith("/", { replace: true });
    });
  });

  it("supports refresh page action while signing in", async () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, "location", {
      value: {
        href: "http://localhost:5173/auth/callback?code=foo&state=bar",
        reload: reloadMock,
      },
      writable: true,
    });
    vi.spyOn(api, "exchangeOIDCCode").mockImplementation(
      () => new Promise(() => {}),
    );

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Refresh page/i }));
    expect(reloadMock).toHaveBeenCalled();
  });
});
