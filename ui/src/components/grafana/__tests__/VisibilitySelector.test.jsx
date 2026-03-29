import { fireEvent, render, screen } from "@testing-library/react";
import VisibilitySelector from "../VisibilitySelector";

vi.mock("../../ui", () => ({
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Checkbox: ({ label, checked, onChange }) => (
    <label>
      <input type="checkbox" checked={checked} onChange={onChange} />
      {label}
    </label>
  ),
}));

describe("VisibilitySelector", () => {
  it("changes visibility and manages shared groups", () => {
    const onVisibilityChange = vi.fn();
    const onSharedGroupIdsChange = vi.fn();

    const { rerender } = render(
      <VisibilitySelector
        visibility="private"
        onVisibilityChange={onVisibilityChange}
        sharedGroupIds={[]}
        onSharedGroupIdsChange={onSharedGroupIdsChange}
        groups={[{ id: "g1", name: "Ops" }, { id: "g2", name: "Platform" }]}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "group" },
    });
    expect(onVisibilityChange).toHaveBeenCalledWith("group");

    rerender(
      <VisibilitySelector
        visibility="group"
        onVisibilityChange={onVisibilityChange}
        sharedGroupIds={["g2"]}
        onSharedGroupIdsChange={onSharedGroupIdsChange}
        groups={[{ id: "g1", name: "Ops" }, { id: "g2", name: "Platform" }]}
      />,
    );

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    expect(onSharedGroupIdsChange).toHaveBeenCalledWith(["g2", "g1"]);
    expect(onSharedGroupIdsChange).toHaveBeenCalledWith([]);
  });

  it("shows no-groups message when in group visibility", () => {
    render(
      <VisibilitySelector
        visibility="group"
        onVisibilityChange={vi.fn()}
        sharedGroupIds={[]}
        onSharedGroupIdsChange={vi.fn()}
        groups={[]}
      />,
    );

    expect(screen.getByText(/No groups available/i)).toBeInTheDocument();
  });
});
