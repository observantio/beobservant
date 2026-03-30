import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import DocumentationPage from "../DocumentationPage";

describe("DocumentationPage", () => {
  it("renders documentation index on /docs", () => {
    render(
      <MemoryRouter initialEntries={["/docs"]}>
        <Routes>
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/docs/:topic" element={<DocumentationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Documentation")).toBeInTheDocument();
    expect(screen.getByText("How to Accept Data")).toBeInTheDocument();
    expect(screen.getByText("How to Share Dashboards")).toBeInTheDocument();
  });

  it("renders selected topic content on /docs/:topic", () => {
    render(
      <MemoryRouter initialEntries={["/docs/alert-rules"]}>
        <Routes>
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/docs/:topic" element={<DocumentationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("How to Set Alert Rules")).toBeInTheDocument();
    expect(
      screen.getByText(/Attach one or more notification channels/i),
    ).toBeInTheDocument();
  });

  it("renders new OIDC sync topic route", () => {
    render(
      <MemoryRouter initialEntries={["/docs/oidc-local-sync"]}>
        <Routes>
          <Route path="/docs" element={<DocumentationPage />} />
          <Route path="/docs/:topic" element={<DocumentationPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByText("How OIDC Syncs to Local User State"),
    ).toBeInTheDocument();
    expect(screen.getByText(/PKCE state\/nonce/i)).toBeInTheDocument();
  });
});
