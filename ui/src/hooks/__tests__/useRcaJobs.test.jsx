import { act, renderHook, waitFor } from "@testing-library/react";
import { useRcaJobs } from "../useRcaJobs";
import * as api from "../../api";

const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ success: toastSuccess, error: toastError }),
}));

vi.mock("../../api", () => ({
  createRcaAnalyzeJob: vi.fn(),
  deleteRcaReport: vi.fn(),
  getRcaJob: vi.fn(),
  listRcaJobs: vi.fn(),
}));

describe("useRcaJobs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("loads jobs, creates/deletes reports, and handles scope changes", async () => {
    api.listRcaJobs
      .mockResolvedValueOnce({ items: [{ job_id: "j1", report_id: "r1", status: "running", created_at: "2026-01-01" }] })
      .mockResolvedValue({ items: [{ job_id: "j2", report_id: "r2", status: "completed", created_at: "2026-01-02" }] });
    api.createRcaAnalyzeJob.mockResolvedValue({ job_id: "j3", report_id: "r3", status: "queued" });
    api.deleteRcaReport.mockResolvedValue({ ok: true });

    const { result, rerender } = renderHook(({ scope }) => useRcaJobs(scope), {
      initialProps: { scope: "org-a" },
    });

    await waitFor(() => expect(result.current.loadingJobs).toBe(false));
    expect(result.current.jobs.length).toBeGreaterThan(0);

    await act(async () => {
      await result.current.createJob({ input: 1 });
    });
    expect(api.createRcaAnalyzeJob).toHaveBeenCalled();
    expect(toastSuccess).toHaveBeenCalled();

    await act(async () => {
      await result.current.deleteReportById("r3");
    });
    expect(api.deleteRcaReport).toHaveBeenCalledWith("r3");

    act(() => {
      result.current.removeJobByReportId("r2");
      result.current.setSelectedJobId("j2");
    });

    rerender({ scope: "org-b" });
    await waitFor(() => expect(api.listRcaJobs).toHaveBeenCalled());

    expect(result.current.refreshJobs).toBeTypeOf("function");
  });

  it("handles create and delete failures", async () => {
    api.listRcaJobs.mockResolvedValue({ items: [] });
    api.createRcaAnalyzeJob.mockRejectedValue(new Error("create failed"));
    api.deleteRcaReport.mockRejectedValue(new Error("delete failed"));

    const { result } = renderHook(() => useRcaJobs("org-a"));
    await waitFor(() => expect(result.current.loadingJobs).toBe(false));

    await act(async () => {
      await expect(result.current.createJob({})).rejects.toThrow("create failed");
    });
    await act(async () => {
      await expect(result.current.deleteReportById("r1")).rejects.toThrow("delete failed");
    });
    expect(toastError).toHaveBeenCalled();
  });
});
