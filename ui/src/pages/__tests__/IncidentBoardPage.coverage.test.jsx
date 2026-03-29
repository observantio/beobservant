import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const toastMock = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
};

const permissionState = {
  readUsers: true,
  manageUsers: false,
  updateIncidents: true,
};

const incidentsDataState = {
  incidents: [],
  incidentUsers: [],
  loading: false,
  error: null,
};

const refresh = vi.fn();
const setIncidents = vi.fn();
const setError = vi.fn();

const updateIncident = vi.fn();
const getGroups = vi.fn();
const createIncidentJira = vi.fn();
const listJiraProjectsByIntegration = vi.fn();
const listJiraIssueTypes = vi.fn();
const listIncidentJiraComments = vi.fn();
const listJiraIntegrations = vi.fn();
const getAlertsByFilter = vi.fn();

vi.mock("../../api", () => ({
  updateIncident: (...args) => updateIncident(...args),
  getGroups: (...args) => getGroups(...args),
  createIncidentJira: (...args) => createIncidentJira(...args),
  listJiraProjectsByIntegration: (...args) => listJiraProjectsByIntegration(...args),
  listJiraIssueTypes: (...args) => listJiraIssueTypes(...args),
  listIncidentJiraComments: (...args) => listIncidentJiraComments(...args),
  listJiraIntegrations: (...args) => listJiraIntegrations(...args),
  getAlertsByFilter: (...args) => getAlertsByFilter(...args),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toastMock,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1", username: "alice" },
    hasPermission: (perm) => {
      if (perm === "read:users") return permissionState.readUsers;
      if (perm === "manage:users") return permissionState.manageUsers;
      if (perm === "update:incidents") return permissionState.updateIncidents;
      return false;
    },
  }),
}));

vi.mock("../../contexts/IncidentSummaryContext", () => ({
  useSharedIncidentSummary: () => ({
    by_visibility: { public: 1, private: 0, group: 0 },
    assigned_to_me_open: 1,
  }),
}));

vi.mock("../../components/HelpTooltip", () => ({
  default: () => <span>help</span>,
}));

vi.mock("../../hooks", async () => {
  const React = await vi.importActual("react");
  const actual = await vi.importActual("../../hooks");
  return {
    ...actual,
    useLocalStorage: (_key, initial) => React.useState(initial),
    useIncidentsData: () => ({
      ...incidentsDataState,
      refresh,
      setIncidents,
      setError,
    }),
  };
});

import IncidentBoardPage from "../IncidentBoardPage";

describe("IncidentBoardPage additional coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    incidentsDataState.incidents = [];
    incidentsDataState.incidentUsers = [];
    incidentsDataState.loading = false;
    incidentsDataState.error = null;

    permissionState.readUsers = true;
    permissionState.manageUsers = false;
    permissionState.updateIncidents = true;

    getGroups.mockResolvedValue([]);
    listJiraIntegrations.mockResolvedValue({ items: [] });
    listJiraProjectsByIntegration.mockResolvedValue({ projects: [] });
    listJiraIssueTypes.mockResolvedValue({ issueTypes: ["Task", "Bug"] });
    listIncidentJiraComments.mockResolvedValue({ comments: [] });
    updateIncident.mockResolvedValue({});
    getAlertsByFilter.mockResolvedValue([]);

    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it("handles quick hide and quick unhide actions", async () => {
    incidentsDataState.incidents = [
      {
        id: "r1",
        alertName: "Visible resolved",
        status: "resolved",
        assignee: "u1",
        fingerprint: "fp-r1",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
        hideWhenResolved: false,
      },
      {
        id: "r2",
        alertName: "Hidden resolved",
        status: "resolved",
        assignee: "u1",
        fingerprint: "fp-r2",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
        hideWhenResolved: true,
      },
    ];

    render(<IncidentBoardPage />);

    fireEvent.click(await screen.findByTitle("Hide incident"));
    await waitFor(() => {
      expect(updateIncident).toHaveBeenCalledWith("r1", { hideWhenResolved: true });
      expect(refresh).toHaveBeenCalled();
      expect(toastMock.success).toHaveBeenCalledWith("Incident hidden");
    });

    fireEvent.click(screen.getByTitle("Unhide incident"));
    await waitFor(() => {
      expect(updateIncident).toHaveBeenCalledWith("r2", { hideWhenResolved: false });
      expect(toastMock.success).toHaveBeenCalledWith("Incident unhidden");
    });
  });

  it("covers notes tab add/quote/copy flows", async () => {
    const now = new Date().toISOString();
    incidentsDataState.incidents = [
      {
        id: "i1",
        alertName: "Disk pressure",
        status: "open",
        assignee: "u1",
        fingerprint: "fp-i1",
        lastSeenAt: now,
        severity: "critical",
        labels: { env: "prod" },
        notes: [
          {
            author: "u1",
            text: "Initial triage complete",
            createdAt: now,
          },
        ],
      },
    ];

    updateIncident.mockResolvedValueOnce({
      ...incidentsDataState.incidents[0],
      notes: [
        {
          author: "u1",
          text: "Initial triage complete",
          createdAt: now,
        },
        {
          author: "u1",
          text: "Mitigated by rollback",
          createdAt: new Date(Date.now() + 1000).toISOString(),
        },
      ],
    });

    render(<IncidentBoardPage />);

    fireEvent.click((await screen.findByText("edit")).closest("button"));
    fireEvent.click(screen.getAllByRole("button", { name: /Notes/i })[1]);

    fireEvent.change(screen.getByPlaceholderText(/Investigation updates/i), {
      target: { value: "Mitigated by rollback" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Add note/i }));

    await waitFor(() => {
      expect(updateIncident).toHaveBeenCalledWith("i1", { note: "Mitigated by rollback" });
      expect(toastMock.success).toHaveBeenCalledWith("Note added");
    });

    fireEvent.click(screen.getByRole("button", { name: /Copy all/i }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalled();
      expect(toastMock.success).toHaveBeenCalledWith("Copied notes to clipboard");
    });

    fireEvent.click(screen.getAllByRole("button", { name: /Quote/i })[0]);
    expect(
      screen.getByPlaceholderText(/Investigation updates/i).value,
    ).toContain("Mitigated by rollback");
  });

  it("guards jira create when update permission is missing", async () => {
    permissionState.updateIncidents = false;
    incidentsDataState.incidents = [
      {
        id: "j1",
        alertName: "CPU spike",
        status: "open",
        assignee: "",
        fingerprint: "fp-j1",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
      },
    ];

    listJiraIntegrations.mockResolvedValue({
      items: [{ id: "int-1", name: "Jira Cloud" }],
    });
    listJiraProjectsByIntegration.mockResolvedValue({
      projects: [{ key: "OPS", name: "Operations" }],
    });

    render(<IncidentBoardPage />);

    fireEvent.click((await screen.findByText("edit")).closest("button"));
    fireEvent.click(screen.getByRole("button", { name: /Jira/i }));

    fireEvent.click(screen.getByRole("button", { name: /Create Jira/i }));
    expect(toastMock.error).toHaveBeenCalledWith("Missing update:incidents permission");
    expect(createIncidentJira).not.toHaveBeenCalled();
  });

  it("renders empty-state message when there are no incidents", async () => {
    incidentsDataState.incidents = [];

    render(<IncidentBoardPage />);

    expect(await screen.findByText(/No incidents found/i)).toBeInTheDocument();
    expect(screen.getByText(/filters are set correctly/i)).toBeInTheDocument();
  });

  it("shows assignment permission fallback when user listing is not allowed", async () => {
    permissionState.readUsers = false;
    permissionState.manageUsers = false;
    incidentsDataState.incidents = [
      {
        id: "p1",
        alertName: "Perm test",
        status: "open",
        assignee: "",
        fingerprint: "fp-p1",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
      },
    ];

    render(<IncidentBoardPage />);

    fireEvent.click((await screen.findByText("edit")).closest("button"));
    fireEvent.click(screen.getByRole("button", { name: /Assignment/i }));

    expect(
      await screen.findByText(/do not have permission to list users/i),
    ).toBeInTheDocument();
  });

  it("surfaces hide incident failures", async () => {
    incidentsDataState.incidents = [
      {
        id: "hf1",
        alertName: "Hide failure",
        status: "resolved",
        assignee: "u1",
        fingerprint: "fp-hf1",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
        hideWhenResolved: false,
      },
    ];
    updateIncident.mockRejectedValueOnce(new Error("hide failed"));

    render(<IncidentBoardPage />);

    fireEvent.click(await screen.findByTitle("Hide incident"));

    await waitFor(() => {
      expect(setError).toHaveBeenCalled();
      expect(toastMock.error).toHaveBeenCalled();
    });
  });

  it("quick-resolves assigned incidents when alert is no longer active", async () => {
    incidentsDataState.incidents = [
      {
        id: "qr1",
        alertName: "Resolve me",
        status: "open",
        assignee: "u1",
        fingerprint: "fp-qr1",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
      },
    ];
    getAlertsByFilter.mockResolvedValueOnce([]);

    render(<IncidentBoardPage />);

    fireEvent.click(await screen.findByTitle("Quick resolve"));

    await waitFor(() => {
      expect(updateIncident).toHaveBeenCalledWith("qr1", { status: "resolved" });
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("blocks quick-resolve when underlying alert is still active", async () => {
    incidentsDataState.incidents = [
      {
        id: "qr2",
        alertName: "Still firing",
        status: "open",
        assignee: "u1",
        fingerprint: "fp-qr2",
        lastSeenAt: new Date().toISOString(),
        severity: "warning",
        notes: [],
      },
    ];
    getAlertsByFilter.mockResolvedValueOnce([{ id: "a-1" }]);

    render(<IncidentBoardPage />);

    fireEvent.click(await screen.findByTitle("Quick resolve"));

    await waitFor(() => {
      expect(updateIncident).not.toHaveBeenCalledWith("qr2", { status: "resolved" });
      expect(toastMock.error).toHaveBeenCalledWith("Alert still active. Resolve it first.");
    });
  });

  it("creates a replacement Jira ticket for linked incidents", async () => {
    incidentsDataState.incidents = [
      {
        id: "j2",
        alertName: "Jira linked",
        status: "open",
        assignee: "u1",
        fingerprint: "fp-j2",
        lastSeenAt: new Date().toISOString(),
        severity: "critical",
        notes: [],
        jiraTicketKey: "OPS-10",
        jiraTicketUrl: "https://jira.local/browse/OPS-10",
      },
    ];
    listJiraIntegrations.mockResolvedValueOnce({
      items: [{ id: "int-1", name: "Jira Cloud" }],
    });
    listJiraProjectsByIntegration.mockResolvedValue({
      projects: [{ key: "OPS", name: "Operations" }],
    });
    listJiraIssueTypes.mockResolvedValue({ issueTypes: ["Task", "Bug"] });
    createIncidentJira.mockResolvedValueOnce({
      jiraTicketKey: "OPS-11",
      jiraTicketUrl: "https://jira.local/browse/OPS-11",
    });

    render(<IncidentBoardPage />);

    fireEvent.click((await screen.findByText("edit")).closest("button"));
    fireEvent.click(screen.getByRole("button", { name: /Jira/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Create New Jira/i }));

    await waitFor(() => {
      expect(createIncidentJira).toHaveBeenCalledWith(
        "j2",
        expect.objectContaining({
          integrationId: "int-1",
          projectKey: "OPS",
          issueType: "Task",
          replaceExisting: true,
        }),
      );
      expect(toastMock.success).toHaveBeenCalledWith("Jira created: OPS-11");
      expect(refresh).toHaveBeenCalled();
    });
  });

  it("shows copy-all notes failure toast when clipboard write fails", async () => {
    const now = new Date().toISOString();
    incidentsDataState.incidents = [
      {
        id: "n1",
        alertName: "Copy failure",
        status: "open",
        assignee: "u1",
        fingerprint: "fp-n1",
        lastSeenAt: now,
        severity: "warning",
        notes: [{ author: "u1", text: "one", createdAt: now }],
      },
    ];
    navigator.clipboard.writeText.mockRejectedValueOnce(new Error("denied"));

    render(<IncidentBoardPage />);

    fireEvent.click((await screen.findByText("edit")).closest("button"));
    fireEvent.click(screen.getAllByRole("button", { name: /Notes/i })[1]);
    fireEvent.click(screen.getByRole("button", { name: /Copy all/i }));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Copy failed");
    });
  });
});
