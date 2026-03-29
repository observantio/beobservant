import { render, screen } from "@testing-library/react";
import {
  IncidentSummaryProvider,
  useSharedIncidentSummary,
} from "../IncidentSummaryContext";

let incidentSummary = { open: 2, acknowledged: 1 };

vi.mock("../../hooks/useIncidentSummary", () => ({
  useIncidentSummary: () => incidentSummary,
}));

function Probe() {
  const summary = useSharedIncidentSummary();
  return <div>{summary ? `open:${summary.open}` : "no-summary"}</div>;
}

describe("IncidentSummaryContext", () => {
  it("provides incident summary values", () => {
    render(
      <IncidentSummaryProvider>
        <Probe />
      </IncidentSummaryProvider>,
    );

    expect(screen.getByText("open:2")).toBeInTheDocument();
  });

  it("returns null-like context outside provider", () => {
    render(<Probe />);
    expect(screen.getByText("no-summary")).toBeInTheDocument();
  });
});
