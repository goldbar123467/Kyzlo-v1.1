import { render, screen } from "@testing-library/react";
import { SummaryCards } from "@/components/summary-cards";
import type { ReporterState } from "@/lib/types";
import fixture from "../fixtures/state.sample.json";

describe("SummaryCards", () => {
  it("renders metrics from fixture", () => {
    render(<SummaryCards state={fixture as ReporterState} />);
    expect(screen.getByText(/Current Equity/i)).toBeInTheDocument();
    expect(screen.getByText(/Daily P&L/i)).toBeInTheDocument();
    expect(screen.getByText(/Win Rate/i)).toBeInTheDocument();
    expect(screen.getByText(/Max Drawdown/i)).toBeInTheDocument();
  });
});
