import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = {
  createSilence: vi.fn(),
  deleteSilence: vi.fn(),
  createAlertRule: vi.fn(),
  updateAlertRule: vi.fn(),
  deleteAlertRule: vi.fn(),
  testAlertRule: vi.fn(),
  importAlertRules: vi.fn(),
  setAlertRuleHidden: vi.fn(),
  setSilenceHidden: vi.fn(),
};

const reloadData = vi.fn();
const setHookError = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

const dataState = {
  alerts: [],
  silences: [],
  rules: [],
  channels: [],
  loading: false,
};

vi.mock("../../api", () => ({
  createSilence: (...args) => api.createSilence(...args),
  deleteSilence: (...args) => api.deleteSilence(...args),
  createAlertRule: (...args) => api.createAlertRule(...args),
  updateAlertRule: (...args) => api.updateAlertRule(...args),
  deleteAlertRule: (...args) => api.deleteAlertRule(...args),
  testAlertRule: (...args) => api.testAlertRule(...args),
  importAlertRules: (...args) => api.importAlertRules(...args),
  setAlertRuleHidden: (...args) => api.setAlertRuleHidden(...args),
  setSilenceHidden: (...args) => api.setSilenceHidden(...args),
}));

vi.mock("../../hooks", async () => {
  const React = await vi.importActual("react");
  return {
    useAlertManagerData: () => ({
      alerts: dataState.alerts,
      silences: dataState.silences,
      rules: dataState.rules,
      channels: dataState.channels,
      loading: dataState.loading,
      reloadData,
      setError: setHookError,
    }),
    useLocalStorage: (_key, initial) => React.useState(initial),
  };
});

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      api_keys: [
        { key: "org-1", name: "Main Product", is_default: true },
        { key: "org-2", name: "Secondary Product", is_default: false },
      ],
    },
  }),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ error: toastError, success: toastSuccess }),
}));

vi.mock("../../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
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

vi.mock("../../components/HelpTooltip", () => ({
  default: () => <span>?</span>,
}));

vi.mock("../../components/ConfirmModal", () => ({
  default: ({ isOpen, title, message, onConfirm, onCancel, confirmText }) =>
    isOpen ? (
      <div>
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>{confirmText || "Confirm"}</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock("../../components/alertmanager/RuleEditor", () => ({
  default: ({ onSave, onCancel }) => (
    <div>
      <button
        onClick={() =>
          onSave({
            name: "rule-new",
            orgId: "org-1",
            orgIds: ["org-1", "org-2"],
            expr: "up == 0",
            duration: "1m",
            severity: "critical",
            labels: {},
            annotations: {},
            enabled: true,
            group: "corr-1",
            visibility: "private",
            notificationChannels: [],
            sharedGroupIds: [],
          })
        }
      >
        save-rule
      </button>
      <button onClick={onCancel}>cancel-rule</button>
    </div>
  ),
}));

vi.mock("../../components/alertmanager/SilenceForm", () => ({
  default: ({ onSave, onCancel }) => (
    <div>
      <button
        onClick={() =>
          onSave({
            matchers: [{ name: "alertname", value: "DiskFull", isEqual: true }],
            startsAt: new Date().toISOString(),
            endsAt: new Date(Date.now() + 3600_000).toISOString(),
            comment: "maintenance",
            visibility: "private",
            sharedGroupIds: [],
          })
        }
      >
        save-silence
      </button>
      <button onClick={onCancel}>cancel-silence</button>
    </div>
  ),
}));

vi.mock("../../utils/alertmanagerRuleUtils", () => ({
  buildRulePayload: (input) => input,
}));

import AlertManagerPage from "../AlertManagerPage";

describe("AlertManagerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dataState.loading = false;
    dataState.alerts = [
      {
        id: "a1",
        fingerprint: "fp1",
        starts_at: "2026-03-01T00:00:00Z",
        labels: { alertname: "DiskFull", severity: "critical", instance: "node-1" },
        annotations: { summary: "Disk almost full" },
        status: { state: "active" },
      },
    ];
    dataState.rules = [
      {
        id: "r1",
        name: "DiskFullRule",
        severity: "critical",
        enabled: true,
        group: "corr-1",
        orgId: "org-1",
        expr: "up == 0",
        duration: "1m",
        annotations: { summary: "summary" },
        createdBy: "user-2",
      },
    ];
    dataState.silences = [
      {
        id: "s1",
        comment: "maintenance",
        starts_at: "2026-03-01T00:00:00Z",
        ends_at: "2026-03-01T01:00:00Z",
        matchers: [{ name: "alertname", value: "DiskFull", isEqual: true }],
        visibility: "group",
        createdBy: "user-2",
      },
    ];
    dataState.channels = [{ id: "c1", enabled: true }];

    api.importAlertRules.mockResolvedValue({
      status: "preview",
      count: 1,
      created: 0,
      updated: 0,
    });
    api.testAlertRule.mockResolvedValue({ message: "test fired" });
    api.setAlertRuleHidden.mockResolvedValue({ ok: true });
    api.setSilenceHidden.mockResolvedValue({ ok: true });
    api.deleteAlertRule.mockResolvedValue({ ok: true });
    api.deleteSilence.mockResolvedValue({ ok: true });
    api.createAlertRule.mockResolvedValue({ ok: true });
    api.updateAlertRule.mockResolvedValue({ ok: true });
    api.createSilence.mockResolvedValue({ ok: true });
  });

  it("covers alerts tab filtering branches", () => {
    render(<AlertManagerPage />);

    fireEvent.click(screen.getByRole("button", { name: /Filters/i }));
    fireEvent.change(screen.getByPlaceholderText(/instance=node-1/i), {
      target: { value: "instance=node-1" },
    });
    const alertFilterSelects = screen.getAllByRole("combobox");
    fireEvent.change(alertFilterSelects[0], { target: { value: "critical" } });

    fireEvent.click(screen.getByRole("button", { name: /^Apply$/i }));
    expect(screen.getByText(/DiskFull/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Filters/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Clear$/i }));
  });

  it("covers rules tab actions, import flow, and rule editor save", async () => {
    render(<AlertManagerPage />);

    fireEvent.click(screen.getByRole("button", { name: /Rules/i }));

    fireEvent.click(screen.getByRole("button", { name: /Filters/i }));
    const ruleFilterSelects = screen.getAllByRole("combobox");
    fireEvent.change(ruleFilterSelects[0], { target: { value: "all" } });
    fireEvent.change(ruleFilterSelects[1], { target: { value: "enabled" } });
    fireEvent.change(ruleFilterSelects[2], { target: { value: "critical" } });
    fireEvent.change(ruleFilterSelects[3], { target: { value: "org-1" } });
    fireEvent.change(screen.getByPlaceholderText(/Search correlation ID/i), {
      target: { value: "corr" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Apply$/i }));

    fireEvent.click(screen.getByTitle("Test Rule"));
    await waitFor(() => {
      expect(api.testAlertRule).toHaveBeenCalledWith("r1");
      expect(screen.getByText(/Success/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle("Hide Rule"));
    fireEvent.click(screen.getByRole("button", { name: /Hide Rule/i }));
    await waitFor(() => {
      expect(api.setAlertRuleHidden).toHaveBeenCalledWith("r1", true);
      expect(reloadData).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTitle("Delete Rule"));
    const deleteButtons = screen.getAllByRole("button", { name: /^Delete$/i });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);
    await waitFor(() => {
      expect(api.deleteAlertRule).toHaveBeenCalledWith("r1");
    });

    fireEvent.click(screen.getByRole("button", { name: /Import YAML/i }));
    fireEvent.click(screen.getByRole("button", { name: /Memory Usage/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Preview$/i }));
    await waitFor(() => {
      expect(api.importAlertRules).toHaveBeenCalledWith(
        expect.objectContaining({ dryRun: true }),
      );
      expect(screen.getByText(/Preview parsed/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Create Rule/i }));
    fireEvent.click(screen.getByRole("button", { name: /save-rule/i }));
    await waitFor(() => {
      expect(api.createAlertRule).toHaveBeenCalled();
    });
  });

  it("covers silences tab create, hide, and delete flows", async () => {
    render(<AlertManagerPage />);

    fireEvent.click(screen.getByRole("button", { name: /Silences/i }));

    fireEvent.click(screen.getByRole("button", { name: /Create Silence/i }));
    fireEvent.click(screen.getByRole("button", { name: /save-silence/i }));
    await waitFor(() => {
      expect(api.createSilence).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTitle("Hide Silence"));
    fireEvent.click(screen.getByRole("button", { name: /Hide Silence/i }));
    await waitFor(() => {
      expect(api.setSilenceHidden).toHaveBeenCalledWith("s1", true);
    });

    fireEvent.click(screen.getByTitle("Delete Silence"));
    const deleteButtons = screen.getAllByRole("button", { name: /^Delete$/i });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);
    await waitFor(() => {
      expect(api.deleteSilence).toHaveBeenCalledWith("s1");
    });
  });

  it("handles api errors through toast and hook error sink", async () => {
    api.deleteAlertRule.mockRejectedValueOnce(new Error("delete failed"));

    render(<AlertManagerPage />);
    fireEvent.click(screen.getByRole("button", { name: /Rules/i }));
    fireEvent.click(screen.getByTitle("Delete Rule"));
    const deleteButtons = screen.getAllByRole("button", { name: /^Delete$/i });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => {
      expect(toastError).toHaveBeenCalled();
      expect(setHookError).toHaveBeenCalled();
    });
  });
});
