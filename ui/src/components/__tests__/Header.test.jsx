import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

let authState = {
  user: {
    id: "u1",
    username: "tester",
    role: "admin",
    api_keys: [],
  },
  logout: vi.fn(),
  hasPermission: (permission) => {
    if (permission === "read:agents") return true;
    if (permission === "read:audit_logs") return true;
    return false;
  },
  refreshUser: vi.fn(),
};

vi.mock("../../api", () => ({
  updateApiKey: vi.fn().mockResolvedValue({}),
  evaluatePromql: vi.fn().mockResolvedValue({ status: "success", data: { result: [] } }),
  getIncidentsSummary: vi.fn().mockResolvedValue(null),
  listApiKeys: vi.fn().mockResolvedValue([]),
  getOjoReleases: vi.fn().mockResolvedValue({ latest: { assets: [] }, releases: [] }),
  getAgents: vi.fn().mockResolvedValue([]),
  getActiveAgents: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

vi.mock("../ChangePasswordModal", () => ({
  default: () => null,
}));

import Header from "../Header";
import * as api from "../../api";

describe("Header user menu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState = {
      user: {
        id: "u1",
        username: "tester",
        role: "admin",
        api_keys: [],
      },
      logout: vi.fn(),
      hasPermission: (permission) => {
        if (permission === "read:agents") return true;
        if (permission === "read:audit_logs") return true;
        return false;
      },
      refreshUser: vi.fn(),
    };
  });

  it("shows Quotas link in user dropdown", async () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /User menu for tester/i }),
    );

    expect(await screen.findByRole("menuitem", { name: /Quotas/i })).toBeInTheDocument();
  });

  it("runs a quick metrics query from the sidebar header", async () => {
    authState.user.api_keys = [
      {
        id: "key-1",
        name: "Tenant A",
        key: "tenant-a",
        is_enabled: true,
        is_shared: false,
        can_use: true,
        is_hidden: false,
      },
    ];

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Quick query metrics/i }));
    fireEvent.change(screen.getAllByRole("textbox")[0], {
      target: { value: "up" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run/i }));

    await waitFor(() => {
      expect(api.evaluatePromql).toHaveBeenCalledWith(
        "up",
        "tenant-a",
        expect.objectContaining({ sampleLimit: 20 }),
      );
    });
    expect(await screen.findByText(/"status": "success"/i)).toBeInTheDocument();
  });

  it("shows extra services in the Ojo wizard with search and selection", async () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Download Ojo Agent/i }));
    fireEvent.click(screen.getByRole("button", { name: /Extra services/i }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "gpu" },
    });

    expect(await screen.findByText(/ojo-gpu · gpu.yaml/i)).toBeInTheDocument();
    expect(screen.queryByText(/ojo-postgres · postgres.yaml/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /GPU/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    expect(await screen.findByText(/Suggested install command/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    expect(
      await screen.findByText(/3\. Generate GPU config file/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/gpu.yaml/i).length).toBeGreaterThan(0);
  });

  it("treats scoped metrics activity as connected in the Ojo wizard", async () => {
    authState.user.api_keys = [
      {
        id: "key-1",
        name: "Tenant A",
        key: "tenant-a",
        is_enabled: true,
        is_shared: false,
        can_use: true,
        is_hidden: false,
      },
    ];
    api.getAgents.mockResolvedValue([]);
    api.getActiveAgents.mockResolvedValue([
      {
        name: "Tenant A",
        tenant_id: "tenant-a",
        active: true,
        metrics_active: true,
        metrics_count: 12,
      },
    ]);

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Download Ojo Agent/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    expect(
      await screen.findByText(/5\. Check if the agent is connected/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Check now/i }));

    expect(
      await screen.findByText(/Connected: metrics detected for Tenant A in the selected API key scope\./i),
    ).toBeInTheDocument();
  });

  it("does not reset to slide 1 when api keys refresh while the wizard is open", async () => {
    authState.user.api_keys = [
      {
        id: "key-1",
        name: "Tenant A",
        key: "tenant-a",
        is_enabled: true,
        is_shared: false,
        can_use: true,
        is_hidden: false,
      },
    ];

    const { rerender } = render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Download Ojo Agent/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    expect(
      await screen.findByText(/3\. Generate Ojo config file/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Slide 3 of 5/i)).toBeInTheDocument();

    authState = {
      ...authState,
      user: {
        ...authState.user,
        api_keys: [
          ...authState.user.api_keys,
          {
            id: "key-2",
            name: "Tenant B",
            key: "tenant-b",
            is_enabled: false,
            is_shared: false,
            can_use: true,
            is_hidden: false,
          },
        ],
      },
    };

    rerender(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Slide 3 of 5/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. Generate Ojo config file/i)).toBeInTheDocument();
  });
});
