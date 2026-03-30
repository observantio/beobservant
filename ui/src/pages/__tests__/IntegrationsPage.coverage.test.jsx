import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = {
  getNotificationChannels: vi.fn(),
  setNotificationChannelHidden: vi.fn(),
  createNotificationChannel: vi.fn(),
  updateNotificationChannel: vi.fn(),
  deleteNotificationChannel: vi.fn(),
  testNotificationChannel: vi.fn(),
  getAllowedChannelTypes: vi.fn(),
  listJiraIntegrations: vi.fn(),
  setJiraIntegrationHidden: vi.fn(),
  createJiraIntegration: vi.fn(),
  updateJiraIntegration: vi.fn(),
  deleteJiraIntegration: vi.fn(),
  getAuthMode: vi.fn(),
};

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toast = { success: toastSuccess, error: toastError };

vi.mock("../../api", () => ({
  getNotificationChannels: (...args) => api.getNotificationChannels(...args),
  setNotificationChannelHidden: (...args) => api.setNotificationChannelHidden(...args),
  createNotificationChannel: (...args) => api.createNotificationChannel(...args),
  updateNotificationChannel: (...args) => api.updateNotificationChannel(...args),
  deleteNotificationChannel: (...args) => api.deleteNotificationChannel(...args),
  testNotificationChannel: (...args) => api.testNotificationChannel(...args),
  getAllowedChannelTypes: (...args) => api.getAllowedChannelTypes(...args),
  listJiraIntegrations: (...args) => api.listJiraIntegrations(...args),
  setJiraIntegrationHidden: (...args) => api.setJiraIntegrationHidden(...args),
  createJiraIntegration: (...args) => api.createJiraIntegration(...args),
  updateJiraIntegration: (...args) => api.updateJiraIntegration(...args),
  deleteJiraIntegration: (...args) => api.deleteJiraIntegration(...args),
  getAuthMode: (...args) => api.getAuthMode(...args),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1" } }),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ title }) => <h1>{title}</h1>,
}));

vi.mock("../../components/ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Card: ({ children }) => <div>{children}</div>,
  Input: ({ ...props }) => <input {...props} />,
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Spinner: () => <div>Loading</div>,
  Modal: ({ isOpen, title, children }) =>
    isOpen ? (
      <div>
        <h2>{title}</h2>
        {children}
      </div>
    ) : null,
}));

vi.mock("../../components/ConfirmModal", () => ({
  default: ({ isOpen, title, message, onConfirm, onCancel, confirmText, cancelText }) =>
    isOpen ? (
      <div role="dialog">
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>{confirmText || "Confirm"}</button>
        <button onClick={onCancel}>{cancelText || "Cancel"}</button>
      </div>
    ) : null,
}));

vi.mock("../../components/alertmanager/ChannelEditor", () => ({
  default: ({ channel, onSave, onCancel, visibility }) => (
    <div>
      <div>{channel ? "edit-channel" : "create-channel"}</div>
      <button
        onClick={() =>
          onSave({
            name: "chan-new",
            type: "email",
            visibility,
            sharedGroupIds: ["g1"],
            enabled: true,
            config: { to: "ops@example.com" },
          })
        }
      >
        submit-channel
      </button>
      <button onClick={onCancel}>cancel-channel</button>
    </div>
  ),
}));

import IntegrationsPage from "../IntegrationsPage";

describe("IntegrationsPage coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    api.getNotificationChannels.mockResolvedValue([
      {
        id: "c1",
        name: "Owner Channel",
        type: "email",
        visibility: "private",
        createdBy: "u1",
        enabled: true,
        isHidden: false,
        config: { to: "owner@example.com" },
      },
      {
        id: "c2",
        name: "Tenant Channel",
        type: "webhook",
        visibility: "tenant",
        createdBy: "u2",
        enabled: true,
        isHidden: false,
        config: { url: "https://hook" },
      },
    ]);
    api.getAllowedChannelTypes.mockResolvedValue({ allowedTypes: ["email", "webhook"] });
    api.listJiraIntegrations.mockResolvedValue({
      items: [
        {
          id: "j1",
          name: "Owner Jira",
          visibility: "private",
          createdBy: "u1",
          baseUrl: "https://jira.example.com",
          enabled: true,
          isHidden: false,
          authMode: "api_token",
        },
        {
          id: "j2",
          name: "Tenant Jira",
          visibility: "tenant",
          createdBy: "u2",
          baseUrl: "https://jira-tenant.example.com",
          enabled: true,
          isHidden: false,
          authMode: "bearer",
        },
      ],
    });
    api.getAuthMode.mockResolvedValue({ oidc_enabled: true });

    api.setNotificationChannelHidden.mockResolvedValue({ ok: true });
    api.createNotificationChannel.mockResolvedValue({ ok: true });
    api.updateNotificationChannel.mockResolvedValue({ ok: true });
    api.deleteNotificationChannel.mockResolvedValue({ ok: true });
    api.testNotificationChannel.mockResolvedValue({ message: "channel test ok" });
    api.setJiraIntegrationHidden.mockResolvedValue({ ok: true });
    api.createJiraIntegration.mockResolvedValue({ ok: true });
    api.updateJiraIntegration.mockResolvedValue({ ok: true });
    api.deleteJiraIntegration.mockResolvedValue({ ok: true });
  });

  it("handles channel create/edit/test/delete and hidden toggle", async () => {
    render(<IntegrationsPage />);

    expect(await screen.findByText("Owner Channel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Add channel/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit-channel/i }));

    await waitFor(() => {
      expect(api.createNotificationChannel).toHaveBeenCalled();
      expect(toastSuccess).toHaveBeenCalledWith("Channel saved");
    });

    fireEvent.click(screen.getByRole("button", { name: /Edit channel/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit-channel/i }));

    await waitFor(() => {
      expect(api.updateNotificationChannel).toHaveBeenCalledWith(
        "c1",
        expect.objectContaining({ name: "chan-new" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /Test channel/i }));
    await waitFor(() => {
      expect(api.testNotificationChannel).toHaveBeenCalledWith("c1");
      expect(screen.getByText(/channel test ok/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Close/i }));

    fireEvent.click(screen.getByRole("button", { name: /Delete channel/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(api.deleteNotificationChannel).toHaveBeenCalledWith("c1");
      expect(toastSuccess).toHaveBeenCalledWith("Channel deleted");
    });

    fireEvent.click(screen.getByRole("button", { name: /Shared By Organization/i }));
    fireEvent.click(screen.getByRole("button", { name: /Hide channel/i }));

    await waitFor(() => {
      expect(api.setNotificationChannelHidden).toHaveBeenCalledWith("c2", true);
    });
  });

  it("handles jira validation, create/edit/delete and hidden toggle", async () => {
    render(<IntegrationsPage />);

    expect(await screen.findByText("Owner Jira")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Add Jira integration/i }));
    fireEvent.click(screen.getByRole("button", { name: /Save Integration/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Jira Base URL is required");
    });

    const nameInput = screen.getByPlaceholderText(/My Jira Integration/i);
    const urlInput = screen.getByPlaceholderText(/https:\/\/company.atlassian.net/i);

    fireEvent.change(nameInput, { target: { value: "   " } });
    fireEvent.change(urlInput, { target: { value: "not-a-url" } });
    fireEvent.click(screen.getByRole("button", { name: /Save Integration/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        "Jira Base URL must be a valid URL (https://company.atlassian.net)",
      );
    });

    fireEvent.change(nameInput, { target: { value: "Jira New" } });
    fireEvent.change(urlInput, { target: { value: "https://jira.new" } });
    fireEvent.click(screen.getByRole("button", { name: /Save Integration/i }));

    await waitFor(() => {
      expect(api.createJiraIntegration).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Jira New", baseUrl: "https://jira.new" }),
      );
      expect(toastSuccess).toHaveBeenCalledWith("Jira integration saved");
    });

    fireEvent.click(screen.getByRole("button", { name: /Edit integration/i }));
    fireEvent.change(screen.getByPlaceholderText(/My Jira Integration/i), {
      target: { value: "Owner Jira Updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save Integration/i }));

    await waitFor(() => {
      expect(api.updateJiraIntegration).toHaveBeenCalledWith(
        "j1",
        expect.objectContaining({ name: "Owner Jira Updated", visibility: "private" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /Delete integration/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(api.deleteJiraIntegration).toHaveBeenCalledWith("j1");
    });

    fireEvent.click(screen.getByRole("button", { name: /Shared By Organization/i }));
    fireEvent.click(screen.getByRole("button", { name: /Hide integration/i }));

    await waitFor(() => {
      expect(api.setJiraIntegrationHidden).toHaveBeenCalledWith("j2", true);
    });
  });

  it("handles load and mutation failures", async () => {
    api.getNotificationChannels.mockRejectedValueOnce(new Error("load failed"));
    api.createNotificationChannel.mockRejectedValueOnce(new Error("save failed"));
    api.deleteJiraIntegration.mockRejectedValueOnce(new Error("delete failed"));

    render(<IntegrationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/No channels in this scope/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Add channel/i }));
    fireEvent.click(screen.getByRole("button", { name: /submit-channel/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("save failed");
    });

    fireEvent.click(screen.getByRole("button", { name: /Delete integration/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("delete failed");
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });
});
