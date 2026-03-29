import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { ToastProvider, useToast } from "../ToastContext";

const setSetupToken = vi.fn();

vi.mock("../../api", () => ({
  setSetupToken: (...args) => setSetupToken(...args),
}));

function ToastHarness() {
  const toast = useToast();
  const [lastId, setLastId] = useState(null);

  return (
    <div>
      <button
        onClick={() => setLastId(toast.success("ok", 0))}
      >
        show-success
      </button>
      <button
        onClick={() => setLastId(toast.error({ detail: [{ msg: "bad", loc: ["field"] }] }, 0))}
      >
        show-error-object
      </button>
      <button onClick={() => setLastId(toast.info(true, 0))}>show-info-bool</button>
      <button onClick={() => setLastId(toast.warning(42, 0))}>show-warning-num</button>
      <button onClick={() => setLastId(toast.showToast("dup", "info", 1000))}>
        show-dup
      </button>
      <button onClick={() => setLastId(toast.showToast("remove-me", "info", 1000))}>
        show-removable
      </button>
      <button onClick={() => lastId && toast.removeToast(lastId)}>remove-last</button>
    </div>
  );
}

describe("ToastContext", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders toast variants, dedupes messages, and removes toasts", async () => {
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /show-success/i }));
    fireEvent.click(screen.getByRole("button", { name: /show-error-object/i }));
    fireEvent.click(screen.getByRole("button", { name: /show-info-bool/i }));
    fireEvent.click(screen.getByRole("button", { name: /show-warning-num/i }));

    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText(/bad at field/i)).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show-dup/i }));
    fireEvent.click(screen.getByRole("button", { name: /show-dup/i }));
    expect(screen.getAllByText("dup").length).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: /show-removable/i }));
    expect(screen.getByText("remove-me")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove-last/i }));
    await waitFor(() => {
      expect(screen.queryByText("remove-me")).not.toBeInTheDocument();
    });

  });

  it("handles global api-error events, including MFA setup challenge", async () => {
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );

    fireEvent(
      globalThis,
      new CustomEvent("api-error", {
        detail: {
          status: 401,
          body: {
            detail: {
              mfa_setup_required: true,
              setup_token: "setup-token-1",
            },
          },
        },
      }),
    );

    await waitFor(() => {
      expect(setSetupToken).toHaveBeenCalledWith("setup-token-1");
      expect(screen.getByText(/setup is required/i)).toBeInTheDocument();
    });

    const countBefore = screen.getAllByText(/setup is required/i).length;

    fireEvent(
      globalThis,
      new CustomEvent("api-error", {
        detail: {
          status: 500,
          body: { detail: "server error" },
        },
      }),
    );

    fireEvent(
      globalThis,
      new CustomEvent("api-error", {
        detail: {
          status: 500,
          body: { detail: "server error" },
        },
      }),
    );

    expect(screen.getAllByText(/setup is required/i).length).toBe(countBefore);
  });
});
