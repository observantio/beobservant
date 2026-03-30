import { act, renderHook } from "@testing-library/react";
import {
  useApi,
  useAutoRefresh,
  useBodyScrollLock,
  useClickOutside,
  useDebounce,
  useLocalStorage,
  usePagination,
  usePrevious,
  useToggle,
} from "../index";

describe("core hooks", () => {
  it("useApi executes and resets state", async () => {
    const apiFunc = vi.fn().mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useApi(apiFunc, null));

    await act(async () => {
      const value = await result.current.execute("x");
      expect(value).toEqual({ ok: true });
    });

    expect(result.current.data).toEqual({ ok: true });
    expect(result.current.loading).toBe(false);

    act(() => {
      result.current.reset();
    });
    expect(result.current.data).toBeNull();
  });

  it("useDebounce updates value after delay", async () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ value }) => useDebounce(value, 50), {
      initialProps: { value: "a" },
    });

    rerender({ value: "b" });
    expect(result.current).toBe("a");

    await act(async () => {
      vi.advanceTimersByTime(60);
    });
    expect(result.current).toBe("b");
    vi.useRealTimers();
  });

  it("useLocalStorage reads and writes values", () => {
    localStorage.setItem("k", JSON.stringify("v1"));
    const { result } = renderHook(() => useLocalStorage("k", "init"));

    expect(result.current[0]).toBe("v1");
    act(() => result.current[1]("v2"));
    expect(localStorage.getItem("k")).toBe(JSON.stringify("v2"));
  });

  it("usePagination provides navigation helpers", () => {
    const { result } = renderHook(() => usePagination(95, 10));

    expect(result.current.totalPages).toBe(10);
    act(() => result.current.goToPage(5));
    expect(result.current.currentPage).toBe(5);
    act(() => result.current.nextPage());
    expect(result.current.currentPage).toBe(6);
    act(() => result.current.previousPage());
    expect(result.current.currentPage).toBe(5);
    act(() => result.current.reset());
    expect(result.current.currentPage).toBe(1);
  });

  it("useAutoRefresh triggers callback when enabled", async () => {
    vi.useFakeTimers();
    const callback = vi.fn();

    renderHook(() => useAutoRefresh(callback, 30, true));

    await act(async () => {
      vi.advanceTimersByTime(65);
    });

    expect(callback).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("useClickOutside and usePrevious work together", () => {
    const handler = vi.fn();
    const { result, rerender } = renderHook(({ value }) => {
      const ref = useClickOutside(handler);
      const prev = usePrevious(value);
      return { ref, prev };
    }, {
      initialProps: { value: 1 },
    });

    const host = document.createElement("div");
    const inside = document.createElement("button");
    host.appendChild(inside);
    document.body.appendChild(host);
    result.current.ref.current = host;

    inside.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(handler).not.toHaveBeenCalled();

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(handler).toHaveBeenCalledTimes(1);

    rerender({ value: 2 });
    expect(result.current.prev).toBe(1);
  });

  it("useToggle and useBodyScrollLock update states", () => {
    const { result, rerender } = renderHook(({ locked }) => {
      const toggle = useToggle(false);
      useBodyScrollLock(locked);
      return toggle;
    }, {
      initialProps: { locked: false },
    });

    act(() => result.current[1]());
    expect(result.current[0]).toBe(true);
    act(() => result.current[2]());
    expect(result.current[0]).toBe(true);
    act(() => result.current[3]());
    expect(result.current[0]).toBe(false);

    rerender({ locked: true });
    expect(document.body.style.overflow).toBe("hidden");
  });
});
