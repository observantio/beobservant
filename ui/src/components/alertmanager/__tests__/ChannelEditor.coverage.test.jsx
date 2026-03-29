import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ChannelEditor from "../ChannelEditor";

const getGroups = vi.fn();

vi.mock("../../ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => (
    <div>
      {label && <span>{label}</span>}
      <input {...props} />
    </div>
  ),
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
}));

vi.mock("../../HelpTooltip", () => ({
  default: () => <span>?</span>,
}));

vi.mock("../channelForms/EmailChannelFields", () => ({
  default: () => <div>Email Channel Fields</div>,
}));

vi.mock("../../../api", () => ({
  getGroups: (...args) => getGroups(...args),
}));

describe("ChannelEditor coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getGroups.mockResolvedValue([
      { id: "g1", name: "Ops", description: "Ops team" },
      { id: "g2", name: "Platform" },
    ]);
  });

  it("covers config type branches, group sharing, and submit payload", async () => {
    const onSave = vi.fn();
    const onCancel = vi.fn();

    render(
      <ChannelEditor
        channel={null}
        onSave={onSave}
        onCancel={onCancel}
        allowedTypes={["email", "slack", "teams", "webhook", "pagerduty"]}
        visibility="group"
      />,
    );

    await waitFor(() => {
      expect(getGroups).toHaveBeenCalled();
      expect(screen.getByText(/Group Sharing/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/Team Slack Channel/i), {
      target: { value: "Primary Channel" },
    });

    const typeSelect = screen.getAllByRole("combobox")[0];

    fireEvent.change(typeSelect, { target: { value: "webhook" } });
    fireEvent.change(screen.getByPlaceholderText(/https:\/\/example.com\/webhook/i), {
      target: { value: "https://endpoint" },
    });
    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: "PUT" },
    });

    fireEvent.change(typeSelect, { target: { value: "slack" } });
    fireEvent.change(
      screen.getByPlaceholderText(/https:\/\/hooks.slack.com\/services/i),
      { target: { value: "https://hooks.slack.com/services/a" } },
    );
    fireEvent.change(screen.getByPlaceholderText(/#alerts/i), {
      target: { value: "#sre-alerts" },
    });

    fireEvent.change(typeSelect, { target: { value: "teams" } });
    fireEvent.change(
      screen.getByPlaceholderText(/https:\/\/outlook.office.com\/webhook/i),
      { target: { value: "https://outlook.office.com/webhook/x" } },
    );

    fireEvent.change(typeSelect, { target: { value: "pagerduty" } });
    fireEvent.change(
      screen.getByPlaceholderText(/Your PagerDuty integration key/i),
      { target: { value: "pd-key" } },
    );

    fireEvent.change(typeSelect, { target: { value: "email" } });
    expect(screen.getByText(/Email Channel Fields/i)).toBeInTheDocument();

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    fireEvent.click(checkboxes[2]);
    expect(screen.getByText(/2 groups selected/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Save Channel/i }));

    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    expect(payload.name).toBe("Primary Channel");
    expect(payload.type).toBe("email");
    expect(payload.enabled).toBe(false);
    expect(payload.sharedGroupIds.sort()).toEqual(["g1", "g2"]);

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("covers channel hydration, empty allowed types, and load-groups error", async () => {
    getGroups.mockRejectedValueOnce(new Error("group load failed"));

    render(
      <ChannelEditor
        channel={{
          name: "Existing",
          type: "webhook",
          enabled: true,
          config: { url: "https://x", method: "POST" },
          shared_group_ids: ["g2"],
          visibility: "group",
        }}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        allowedTypes={["not-enabled"]}
        visibility="tenant"
      />,
    );

    await waitFor(() => {
      expect(getGroups).toHaveBeenCalled();
    });

    expect(screen.getByDisplayValue("Existing")).toBeInTheDocument();
    expect(
      screen.getByText(/No channel types are enabled by organization policy/i),
    ).toBeInTheDocument();
  });
});
