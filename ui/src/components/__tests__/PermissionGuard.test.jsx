import { render, screen } from "@testing-library/react";
import PermissionGuard from "../PermissionGuard";

let authState = {
  hasPermission: () => false,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("PermissionGuard", () => {
  beforeEach(() => {
    authState = {
      hasPermission: () => false,
    };
  });

  it("renders children when no permission rules are provided", () => {
    render(<PermissionGuard><div>visible</div></PermissionGuard>);
    expect(screen.getByText("visible")).toBeInTheDocument();
  });

  it("renders fallback when all permissions are not satisfied", () => {
    authState = {
      hasPermission: (permission) => permission === "read:logs",
    };

    render(
      <PermissionGuard all={["read:logs", "read:traces"]} fallback={<div>blocked</div>}>
        <div>visible</div>
      </PermissionGuard>,
    );

    expect(screen.getByText("blocked")).toBeInTheDocument();
    expect(screen.queryByText("visible")).not.toBeInTheDocument();
  });

  it("renders children when all permissions are satisfied", () => {
    authState = {
      hasPermission: () => true,
    };

    render(
      <PermissionGuard all={["read:logs", "read:traces"]} fallback={<div>blocked</div>}>
        <div>visible</div>
      </PermissionGuard>,
    );

    expect(screen.getByText("visible")).toBeInTheDocument();
    expect(screen.queryByText("blocked")).not.toBeInTheDocument();
  });

  it("renders children when any permission matches", () => {
    authState = {
      hasPermission: (permission) => permission === "read:alerts",
    };

    render(
      <PermissionGuard any={["read:logs", "read:alerts"]} fallback={<div>blocked</div>}>
        <div>visible</div>
      </PermissionGuard>,
    );

    expect(screen.getByText("visible")).toBeInTheDocument();
  });

  it("renders fallback when no any permission matches", () => {
    render(
      <PermissionGuard any={["read:logs", "read:alerts"]} fallback={<div>blocked</div>}>
        <div>visible</div>
      </PermissionGuard>,
    );

    expect(screen.getByText("blocked")).toBeInTheDocument();
    expect(screen.queryByText("visible")).not.toBeInTheDocument();
  });
});
