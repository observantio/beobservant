import { fireEvent, render, screen } from "@testing-library/react";
import OIDCLoginButton from "../OIDCLoginButton";

vi.mock("../../ui", () => ({
  Button: ({ children, onClick, loading, ...props }) => (
    <button onClick={onClick} data-loading={String(Boolean(loading))} {...props}>
      {children}
    </button>
  ),
}));

describe("OIDCLoginButton", () => {
  it("renders provider label and handles click", () => {
    const onClick = vi.fn();
    render(<OIDCLoginButton loading={false} onClick={onClick} providerLabel="OIDC" />);

    fireEvent.click(screen.getByRole("button", { name: /Continue with OIDC/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("shows redirecting state while loading", () => {
    render(<OIDCLoginButton loading onClick={() => {}} />);
    expect(screen.getByRole("button", { name: /Redirecting/i })).toBeInTheDocument();
  });
});
