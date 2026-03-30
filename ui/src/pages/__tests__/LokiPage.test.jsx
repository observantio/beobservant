import { render, waitFor } from "@testing-library/react";
import { vi, describe, it, beforeEach, expect } from "vitest";

vi.mock("../../api", () => ({
  getLabels: vi.fn(),
  getLabelValues: vi.fn(),
  queryLogs: vi.fn(),
  getLogVolume: vi.fn(),
}));

vi.mock("../../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
  Sparkline: () => <svg />,
  Spinner: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
}));
vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));
let authState = {
  user: { id: "u1", org_id: "org-a", api_keys: [] },
};
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));
vi.mock("../../hooks", () => ({ useAutoRefresh: () => {} }));

import LokiPage from "../LokiPage";
import * as api from "../../api";

describe("LokiPage localStorage behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    authState = {
      user: { id: "u1", org_id: "org-a", api_keys: [] },
    };
  });

  it("does not mutate legacy saved state during initial load", async () => {
    localStorage.setItem(
      "lokiPageState",
      JSON.stringify({
        selectedLabel: "foo",
        selectedValue: "bar",
      }),
    );

    api.getLabels.mockResolvedValue({ data: ["baz"] });
    api.getLabelValues.mockResolvedValue({ data: [] });
    render(<LokiPage />);

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("lokiPageState") || "{}");
      expect(stored.selectedLabel).toBe("foo");
      expect(stored.selectedValue).toBe("bar");
    });
  });

  it("reloads log filter labels when the active API key changes", async () => {
    api.getLabels
      .mockResolvedValueOnce({ data: ["service_name"] })
      .mockResolvedValueOnce({ data: ["app"] });
    api.getLabelValues.mockResolvedValue({ data: [] });

    const { rerender } = render(<LokiPage />);

    await waitFor(() => {
      expect(api.getLabels).toHaveBeenCalledTimes(1);
    });

    authState = {
      user: {
        id: "u1",
        org_id: "org-b",
        api_keys: [
          { id: "key-a", key: "org-a", is_enabled: false },
          { id: "key-b", key: "org-b", is_enabled: true },
        ],
      },
    };
    rerender(<LokiPage />);

    await waitFor(() => {
      expect(api.getLabels).toHaveBeenCalledTimes(2);
    });
  });
});
