import { fireEvent, render, screen } from "@testing-library/react";
import TraceTimeline from "../TraceTimeline";

vi.mock("../../ui", () => ({
  Badge: ({ children }) => <span>{children}</span>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
}));

vi.mock("../../../utils/formatters", () => ({
  formatDuration: (d) => `${d}us`,
}));

vi.mock("../../../utils/helpers", () => ({
  getServiceName: (span) => span.serviceName || "svc",
  hasSpanError: (span) => Boolean(span.error),
  getSpanColorClass: () => "bg-blue-500",
}));

describe("TraceTimeline coverage", () => {
  it("returns null when trace is missing", () => {
    const { container } = render(<TraceTimeline trace={null} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders span timeline and handles copy/toggle/close actions", () => {
    const onClose = vi.fn();
    const onCopyTraceId = vi.fn();

    render(
      <TraceTimeline
        trace={{
          traceId: "trace-1",
          spans: [
            {
              spanId: "s1",
              operationName: "GET /health",
              serviceName: "api",
              startTime: 100,
              duration: 50,
              tags: { env: "prod", host: "a", region: "us", tier: "web" },
            },
            {
              spanId: "s2",
              parentSpanId: "s1",
              operationName: "db",
              serviceName: "db",
              startTime: 120,
              duration: 20,
              error: true,
              tags: [{ key: "sql", value: "select 1" }],
            },
          ],
        }}
        onClose={onClose}
        onCopyTraceId={onCopyTraceId}
      />,
    );

    expect(screen.getByText(/Trace Timeline/i)).toBeInTheDocument();
    expect(screen.getAllByText(/ERROR/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Services/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle(/Copy Trace ID/i));
    expect(onCopyTraceId).toHaveBeenCalledWith("trace-1");

    fireEvent.click(screen.getByText(/\+1 more/i));
    expect(screen.getByText(/Show less/i)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Close dialog/i));
    expect(onClose).toHaveBeenCalled();
  });
});
