import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api", () => ({
  getRcaJob: vi.fn(),
  getRcaReportById: vi.fn(),
  getRcaJobResult: vi.fn(),
  fetchRcaBayesian: vi.fn(),
  fetchRcaCorrelate: vi.fn(),
  fetchRcaForecast: vi.fn(),
  fetchRcaGranger: vi.fn(),
  fetchRcaSloBurn: vi.fn(),
  fetchRcaTopology: vi.fn(),
  getRcaDeployments: vi.fn(),
  getRcaMlWeights: vi.fn(),
}));

import * as api from "../../api";
import { useRcaReport } from "../useRcaReport";

describe("useRcaReport", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
  });

  it("polls queued jobs and switches to completed when result is ready", async () => {
    api.getRcaJob.mockResolvedValue({
      job_id: "job-1",
      report_id: "rep-1",
      status: "queued",
      tenant_id: "tenant-a",
      requested_by: "u1",
    });
    const notFoundErr = new Error("RCA report not found");
    notFoundErr.status = 404;
    api.getRcaReportById.mockRejectedValue(notFoundErr);
    api.getRcaJobResult
      .mockResolvedValueOnce({
        job_id: "job-1",
        report_id: "rep-1",
        status: "pending",
        tenant_id: "tenant-a",
        requested_by: "u1",
        result: null,
      })
      .mockResolvedValueOnce({
        job_id: "job-1",
        report_id: "rep-1",
        status: "completed",
        tenant_id: "tenant-a",
        requested_by: "u1",
        result: {
          start: "2026-03-08T00:00:00Z",
          end: "2026-03-08T00:05:00Z",
          overall_severity: "medium",
          service_latency: [],
          error_propagation: [],
        },
      });

    const selectedJob = { job_id: "job-1", status: "queued" };

    const { result } = renderHook(() =>
      useRcaReport(
        "job-1",
        selectedJob,
        null,
        { enableInsights: false, activeInsightTab: "summary" },
      ),
    );

    await waitFor(() => expect(result.current.loadingPrimaryReport).toBe(false));
    expect(result.current.hasReport).toBe(false);
    expect(api.getRcaJobResult).toHaveBeenCalled();

    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await waitFor(() => expect(result.current.hasReport).toBe(true));
    expect(result.current.reportMeta?.status).toBe("completed");
    expect(api.getRcaJobResult).toHaveBeenCalledTimes(2);
  });

  it("falls back to job-result fetch when report-id lookup returns 404", async () => {
    api.getRcaJob.mockResolvedValue({
      job_id: "job-2",
      report_id: "rep-2",
      status: "completed",
      tenant_id: "tenant-a",
      requested_by: "u1",
    });
    const notFoundErr = new Error("RCA report not found");
    notFoundErr.status = 404;
    api.getRcaReportById.mockRejectedValue(notFoundErr);
    api.getRcaJobResult.mockResolvedValue({
      job_id: "job-2",
      report_id: "rep-2",
      status: "completed",
      tenant_id: "tenant-a",
      requested_by: "u1",
      result: {
        start: "2026-03-08T00:00:00Z",
        end: "2026-03-08T00:05:00Z",
        overall_severity: "high",
        service_latency: [],
        error_propagation: [],
      },
    });

    const selectedJob = { job_id: "job-2", status: "completed", report_id: "rep-2" };
    const { result } = renderHook(() =>
      useRcaReport(
        "job-2",
        selectedJob,
        null,
        { enableInsights: false, activeInsightTab: "summary" },
      ),
    );

    await waitFor(() => expect(result.current.hasReport).toBe(true));
    expect(api.getRcaReportById).toHaveBeenCalledWith("rep-2");
    expect(api.getRcaJobResult).toHaveBeenCalledWith("job-2");
  });

  it("treats job-result conflict as transient and skips repeated report lookups", async () => {
    api.getRcaJob
      .mockResolvedValueOnce({
        job_id: "job-3",
        report_id: "rep-3",
        status: "completed",
        tenant_id: "tenant-a",
        requested_by: "u1",
      })
      .mockResolvedValueOnce({
        job_id: "job-3",
        report_id: "rep-3",
        status: "completed",
        tenant_id: "tenant-a",
        requested_by: "u1",
      });
    const notFoundErr = new Error("RCA report not found");
    notFoundErr.status = 404;
    api.getRcaReportById.mockRejectedValue(notFoundErr);
    const conflictErr = new Error("result not ready");
    conflictErr.status = 409;
    api.getRcaJobResult
      .mockRejectedValueOnce(conflictErr)
      .mockResolvedValueOnce({
        job_id: "job-3",
        report_id: "rep-3",
        status: "completed",
        tenant_id: "tenant-a",
        requested_by: "u1",
        result: {
          start: "2026-03-08T00:00:00Z",
          end: "2026-03-08T00:05:00Z",
          overall_severity: "high",
          service_latency: [],
          error_propagation: [],
        },
      });

    const selectedJob = {
      job_id: "job-3",
      status: "completed",
      report_id: "rep-3",
    };
    const { result } = renderHook(() =>
      useRcaReport(
        "job-3",
        selectedJob,
        null,
        { enableInsights: false, activeInsightTab: "summary" },
      ),
    );

    await waitFor(() => expect(result.current.loadingPrimaryReport).toBe(false));
    expect(result.current.reportError).toBe(null);
    expect(result.current.hasReport).toBe(false);
    expect(api.getRcaReportById).toHaveBeenCalledTimes(1);
    expect(api.getRcaJobResult).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.reloadReport();
    });

    await waitFor(() => expect(result.current.hasReport).toBe(true));
    expect(api.getRcaReportById).toHaveBeenCalledTimes(1);
    expect(api.getRcaJobResult).toHaveBeenCalledTimes(2);
  });

  it("resets and sets error for terminal failed jobs", async () => {
    const selectedJob = {
      job_id: "job-failed",
      status: "failed",
      error: "boom",
    };

    const { result } = renderHook(() =>
      useRcaReport("job-failed", selectedJob, null, {
        enableInsights: false,
        activeInsightTab: "summary",
      }),
    );

    await waitFor(() => {
      expect(result.current.loadingPrimaryReport).toBe(false);
      expect(result.current.hasReport).toBe(false);
      expect(result.current.reportError).toBe("boom");
    });

    expect(api.getRcaJobResult).not.toHaveBeenCalled();
  });

  it("loads by reportId override and keeps polling disabled", async () => {
    api.getRcaReportById.mockResolvedValue({
      job_id: "job-o",
      report_id: "rep-o",
      status: "completed",
      tenant_id: "tenant-o",
      requested_by: "u1",
      result: {
        start: "2026-03-08T00:00:00Z",
        end: "2026-03-08T00:05:00Z",
        service_latency: [{ service: "api" }],
        error_propagation: [],
      },
    });

    const { result } = renderHook(() =>
      useRcaReport(null, null, "rep-o", {
        enableInsights: false,
        activeInsightTab: "summary",
      }),
    );

    await waitFor(() => {
      expect(result.current.hasReport).toBe(true);
      expect(result.current.reportMeta?.report_id).toBe("rep-o");
    });

    expect(api.getRcaReportById).toHaveBeenCalledWith("rep-o");
    expect(api.getRcaJob).not.toHaveBeenCalled();
    expect(api.getRcaJobResult).not.toHaveBeenCalled();
  });

  it("loads insight tabs and records insight fetch errors", async () => {
    api.getRcaJob.mockResolvedValue({
      job_id: "job-insights",
      report_id: "rep-insights",
      status: "completed",
      tenant_id: "tenant-a",
      requested_by: "u1",
    });
    api.getRcaReportById.mockResolvedValue({
      job_id: "job-insights",
      report_id: "rep-insights",
      status: "completed",
      tenant_id: "tenant-a",
      requested_by: "u1",
      result: {
        start: "2026-03-08T00:00:00Z",
        end: "2026-03-08T00:05:00Z",
        service_latency: [{ service: "api" }],
        error_propagation: [{ source_service: "api" }],
      },
    });
    api.fetchRcaCorrelate.mockRejectedValue(new Error("corr failed"));
    api.fetchRcaGranger.mockResolvedValue({ edges: [] });
    api.fetchRcaBayesian.mockResolvedValue({ posteriors: [] });
    api.getRcaMlWeights.mockResolvedValue({ weights: {} });
    api.getRcaDeployments.mockResolvedValue([]);
    api.fetchRcaTopology.mockResolvedValue({ root_service: "api" });

    const { result, rerender } = renderHook(
      ({ tab }) =>
        useRcaReport(
          "job-insights",
          { job_id: "job-insights", status: "completed", report_id: "rep-insights" },
          null,
          { enableInsights: true, activeInsightTab: tab },
        ),
      { initialProps: { tab: "causal" } },
    );

    await waitFor(() => {
      expect(result.current.hasReport).toBe(true);
    });

    await waitFor(() => {
      expect(api.fetchRcaCorrelate).toHaveBeenCalled();
      expect(api.fetchRcaGranger).toHaveBeenCalled();
      expect(api.fetchRcaBayesian).toHaveBeenCalled();
      expect(api.getRcaMlWeights).toHaveBeenCalled();
      expect(api.getRcaDeployments).toHaveBeenCalled();
    });

    rerender({ tab: "topology" });
    await waitFor(() => {
      expect(api.fetchRcaTopology).toHaveBeenCalled();
    });
  });
});
