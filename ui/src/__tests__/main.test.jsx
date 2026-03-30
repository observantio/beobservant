import { beforeEach, describe, expect, it, vi } from "vitest";

describe("main entrypoint", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = '<div id="root"></div>';
  });

  it("mounts App into the root element", async () => {
    const render = vi.fn();
    const createRoot = vi.fn(() => ({ render }));

    vi.doMock("react-dom/client", () => ({ createRoot }));
    vi.doMock("../App", () => ({
      default: () => <div>App</div>,
    }));

    await import("../main.jsx");

    expect(createRoot).toHaveBeenCalledWith(document.getElementById("root"));
    expect(render).toHaveBeenCalledTimes(1);
  });
});
