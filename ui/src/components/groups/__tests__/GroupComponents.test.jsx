import { fireEvent, render, screen } from "@testing-library/react";
import GroupCard from "../GroupCard";
import GroupForm from "../GroupForm";
import GroupPermissions from "../GroupPermissions";
import MemberList from "../MemberList";

vi.mock("../../ui", () => ({
  Card: ({ children, ...props }) => <div {...props}>{children}</div>,
  Badge: ({ children }) => <span>{children}</span>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, ...props }) => <input aria-label={label || props.placeholder} {...props} />,
  Textarea: ({ label, ...props }) => <textarea aria-label={label} {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
  Checkbox: ({ checked, onChange }) => (
    <input type="checkbox" checked={checked} onChange={onChange} aria-label="checkbox" />
  ),
}));

vi.mock("../../HelpTooltip", () => ({ default: () => <span>help</span> }));
vi.mock("../../../utils/groupManagementUtils", () => ({
  getCategoryDescription: (resource) => `About ${resource}`,
}));

describe("group components", () => {
  it("renders GroupCard and triggers actions", () => {
    const onOpenPermissions = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const group = { id: "g1", name: "Ops", description: "Ops group" };

    render(
      <GroupCard
        group={group}
        usersCount={2}
        permsCount={1}
        onOpenPermissions={onOpenPermissions}
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Permissions for Ops/i }));
    fireEvent.click(screen.getByRole("button", { name: /Edit Ops/i }));
    fireEvent.click(screen.getByRole("button", { name: /Delete Ops/i }));

    expect(onOpenPermissions).toHaveBeenCalledWith(group);
    expect(onEdit).toHaveBeenCalledWith(group);
    expect(onDelete).toHaveBeenCalledWith(group);
    expect(screen.getByText(/1 permission/i)).toBeInTheDocument();
    expect(screen.getByText(/2 members/i)).toBeInTheDocument();
  });

  it("updates GroupForm fields", () => {
    const setFormData = vi.fn();
    const formData = { name: "", description: "" };

    render(<GroupForm formData={formData} setFormData={setFormData} />);

    fireEvent.change(screen.getByLabelText("Group Name *"), {
      target: { value: "Platform" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Team" },
    });

    expect(setFormData).toHaveBeenNthCalledWith(1, {
      ...formData,
      name: "Platform",
    });
    expect(setFormData).toHaveBeenNthCalledWith(2, {
      ...formData,
      description: "Team",
    });
  });

  it("renders GroupPermissions and handles bulk/single actions", () => {
    const addPerms = vi.fn();
    const removePerms = vi.fn();
    const togglePermission = vi.fn();

    const permissionsByResource = {
      logs: [
        { id: "1", name: "read:logs", display_name: "Read Logs", description: "Read" },
        { id: "2", name: "write:logs", display_name: "Write Logs", description: "Write" },
      ],
    };

    render(
      <GroupPermissions
        permissionsByResource={permissionsByResource}
        groupPermissions={["read:logs"]}
        togglePermission={togglePermission}
        addPerms={addPerms}
        removePerms={removePerms}
      />,
    );

    const selectAllButtons = screen.getAllByRole("button", { name: "Select All" });
    const clearAllButtons = screen.getAllByRole("button", { name: "Clear All" });

    fireEvent.click(selectAllButtons[0]);
    fireEvent.click(clearAllButtons[0]);
    fireEvent.click(selectAllButtons[1]);
    fireEvent.click(clearAllButtons[1]);

    fireEvent.click(screen.getAllByLabelText("checkbox")[0]);

    expect(addPerms).toHaveBeenCalled();
    expect(removePerms).toHaveBeenCalled();
    expect(togglePermission).toHaveBeenCalledWith("read:logs");
  });

  it("handles MemberList empty, filtered, and limited display states", () => {
    const toggleMember = vi.fn();
    const users = [
      { id: "u1", username: "alice", email: "alice@example.com" },
      { id: "u2", username: "bob", email: "bob@example.com" },
      { id: "u3", username: "cara", email: "cara@example.com" },
      { id: "u4", username: "dan", email: "dan@example.com" },
      { id: "u5", username: "eve", email: "eve@example.com" },
      { id: "u6", username: "finn", email: "finn@example.com" },
    ];

    const { rerender } = render(
      <MemberList users={[]} selectedMembers={[]} toggleMember={toggleMember} />,
    );
    expect(screen.getByText("No users available.")).toBeInTheDocument();

    rerender(
      <MemberList users={users} selectedMembers={["u2"]} toggleMember={toggleMember} />,
    );

    expect(screen.getByText(/Showing first 5 of 6 users/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Search users by name or email/i), {
      target: { value: "nomatch" },
    });
    expect(screen.getByText("No users match your search.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Search users by name or email/i), {
      target: { value: "bob" },
    });

    fireEvent.click(screen.getByLabelText("checkbox"));
    expect(toggleMember).toHaveBeenCalledWith("u2");
  });
});
