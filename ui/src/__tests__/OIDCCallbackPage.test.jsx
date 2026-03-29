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
    finishOIDCLogin: async ({ code, state }) => {
      return await api.exchangeOIDCCode(code, "", { state });
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
