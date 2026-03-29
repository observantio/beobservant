import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AuditCompliancePage from "../AuditCompliancePage";
import * as api from "../../api";

let hasPermission = () => true;
const toast = { success: vi.fn(), error: vi.fn() };
const copyToClipboard = vi.fn();
const downloadFile = vi.fn();

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ hasPermission }),
}));

vi.mock("../../contexts/LayoutModeContext", () => ({
  useLayoutMode: () => ({ sidebarMode: true }),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toast,
}));

vi.mock("../../utils/helpers", () => ({
  copyToClipboard: (...args) => copyToClipboard(...args),
  downloadFile: (...args) => downloadFile(...args),
}));

vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ title, subtitle }) => (
    <div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  ),
}));

vi.mock("../../components/ui", () => ({
  Card: ({ children, title }) => (
    <div>
      {title ? <h2>{title}</h2> : null}
      {children}
    </div>
  ),
  Input: ({ helperText, error, label, ...props }) => <input {...props} />,
  Button: ({ children, loading, ...props }) => (
    <button {...props} disabled={loading || props.disabled}>
      {children}
    </button>
  ),
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Spinner: () => <div>Loading</div>,
  Badge: ({ children }) => <span>{children}</span>,
}));

vi.mock("../../api");

describe("AuditCompliancePage coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hasPermission = () => true;
    api.getUsers.mockResolvedValue([{ id: "u1", username: "alice", email: "a@x.com" }]);
    api.getAuditLogs.mockResolvedValue([
      {
        id: "a1",
        created_at: "2026-03-29T00:00:00Z",
        user_id: "u1",
        action: "login",
        resource_type: "user",
        resource_id: "u1",
        details: { method: "GET", status_code: 200 },
        ip_address: "127.0.0.1",
      },
    ]);
    api.exportAuditLogs.mockResolvedValue("csv");
    copyToClipboard.mockResolvedValue(true);
  });

  it("shows permission message when audit read permission is missing", async () => {
    hasPermission = () => false;
    render(<AuditCompliancePage />);
    expect(
      await screen.findByText(/do not have permission to view audit logs/i),
    ).toBeInTheDocument();
  });

  it("renders audit page and supports selecting a row", async () => {
    render(<AuditCompliancePage />);

    await waitFor(() => {
      expect(screen.getByText(/Audit & Compliance/i)).toBeInTheDocument();
    });

    const rowButton = screen.getByRole("button", { name: /Open audit details a1/i });
    fireEvent.click(rowButton);

    expect(screen.getAllByText(/login/i).length).toBeGreaterThan(0);
  });

  it("handles pagination no-more-results and export flow", async () => {
    const now = "2026-03-29T00:00:00Z";
    const many = Array.from({ length: 101 }, (_, i) => ({
      id: `row-${i + 1}`,
      created_at: now,
      user_id: "u1",
      action: "view",
      resource_type: "audit",
      resource_id: `${i + 1}`,
      details: {},
      ip_address: "127.0.0.1",
    }));
    api.getAuditLogs.mockResolvedValueOnce(many).mockResolvedValueOnce([]);

    render(<AuditCompliancePage />);

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 - 100/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("No more audit records");
    });

    fireEvent.click(screen.getByRole("button", { name: /Export/i }));
    await waitFor(() => {
      expect(api.exportAuditLogs).toHaveBeenCalled();
      expect(downloadFile).toHaveBeenCalledWith("csv", "audit-logs.csv", "text/csv");
      expect(toast.success).toHaveBeenCalledWith("Audit CSV exported");
    });
  });

  it("covers row detail copy success and failure", async () => {
    render(<AuditCompliancePage />);

    const rowButton = await screen.findByRole("button", {
      name: /Open audit details a1/i,
    });
    fireEvent.click(rowButton);

    fireEvent.click(screen.getByRole("button", { name: /Copy JSON/i }));
    await waitFor(() => {
      expect(copyToClipboard).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith("Copied to clipboard");
    });

    copyToClipboard.mockResolvedValueOnce(false);
    fireEvent.click(screen.getByRole("button", { name: /Copy resource/i }));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Copy failed");
    });
  });

  it("shows load failure toast when audit fetch fails", async () => {
    api.getAuditLogs.mockRejectedValueOnce(new Error("audit load failed"));

    render(<AuditCompliancePage />);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("audit load failed");
      expect(screen.getByText(/No audit records found/i)).toBeInTheDocument();
    });
  });

  it("handles export failure and clears action filter chip", async () => {
    api.exportAuditLogs.mockRejectedValueOnce(new Error("export failed"));

    render(<AuditCompliancePage />);

    await screen.findByText(/Audit & Compliance/i);
    fireEvent.change(screen.getByPlaceholderText(/api_key.create/i), {
      target: { value: "token.rotate" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Apply$/i }));

    await waitFor(() => {
      expect(screen.getByText(/Action: token.rotate/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Export/i }));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("export failed");
    });

    const actionChip = screen.getByText(/Action: token.rotate/i).parentElement;
    fireEvent.click(actionChip.querySelector("button"));
    await waitFor(() => {
      expect(screen.queryByText(/Action: token.rotate/i)).not.toBeInTheDocument();
    });
  });
});
