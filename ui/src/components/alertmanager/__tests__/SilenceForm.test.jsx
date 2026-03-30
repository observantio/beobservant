import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SilenceForm from "../SilenceForm";

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

vi.mock("../../../api", () => ({
  getGroups: (...args) => getGroups(...args),
}));

describe("SilenceForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getGroups.mockResolvedValue([
      { id: "g1", name: "Ops", description: "Operations" },
      { id: "g2", name: "Platform" },
    ]);
  });

  it("loads groups, manages matchers and submits group visibility payload", async () => {
    const onSave = vi.fn();
    const onCancel = vi.fn();

    render(<SilenceForm onSave={onSave} onCancel={onCancel} />);

    await waitFor(() => {
      expect(getGroups).toHaveBeenCalled();
    });

    const inputs = screen.getAllByRole("textbox");
    fireEvent.change(inputs[0], { target: { value: "alertname" } });
    fireEvent.change(inputs[1], { target: { value: "HighLatency" } });

    fireEvent.click(screen.getByRole("button", { name: /Add Matcher/i }));

    const matcherInputs = screen.getAllByRole("textbox");
    fireEvent.change(matcherInputs[2], { target: { value: "service" } });
    fireEvent.change(matcherInputs[3], { target: { value: "api" } });

    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deleteButtons[0]);

    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "2" } });
    fireEvent.change(screen.getByPlaceholderText(/Reason for silence/i), {
      target: { value: "maintenance" },
    });

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "group" } });

    await waitFor(() => {
      expect(screen.getByText(/Share with Groups/i)).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    expect(screen.getByText(/2 groups selected/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Create Silence/i }));

    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    expect(payload.matchers.length).toBe(1);
    expect(payload.visibility).toBe("group");
    expect(payload.sharedGroupIds.sort()).toEqual(["g1", "g2"]);
    expect(payload.comment).toBe("maintenance");
    expect(new Date(payload.endsAt).getTime()).toBeGreaterThan(
      new Date(payload.startsAt).getTime(),
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("handles group load failure and tenant/private visibility messaging", async () => {
    getGroups.mockRejectedValueOnce(new Error("failed"));
    const onSave = vi.fn();

    render(<SilenceForm onSave={onSave} onCancel={vi.fn()} />);

    await waitFor(() => {
      expect(getGroups).toHaveBeenCalled();
    });

    expect(screen.getByText(/Only you can view and edit this silence/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "tenant" } });
    expect(screen.getByText(/All users in your organization can view this silence/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "private" } });
    expect(screen.getByText(/Only you can view and edit this silence/i)).toBeInTheDocument();
  });
});
