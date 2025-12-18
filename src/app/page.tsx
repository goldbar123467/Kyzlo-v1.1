export const revalidate = 300;

import { BackdropToggle } from "@/components/backdrop-toggle";
import { EquityChart } from "@/components/equity-chart";
import { SummaryCards } from "@/components/summary-cards";
import { TradesTable } from "@/components/trades-table";
import { loadState } from "@/lib/stateService";

export default async function Home() {
  const state = await loadState();

  return (
    <main className="relative min-h-screen overflow-hidden bg-transparent text-slate-100">
      <div className="starfield" style={{ opacity: "var(--cosmos-enabled)" }} />
      <div
        className="parallax-gradient"
        style={{ opacity: "calc(0.9 * var(--cosmos-enabled))" }}
      />
      <div
        className="planet p1"
        style={{ opacity: "calc(0.5 * var(--cosmos-enabled))" }}
      />
      <div
        className="planet p2"
        style={{ opacity: "calc(0.5 * var(--cosmos-enabled))" }}
      />
      <div
        className="rocket"
        style={{ opacity: "calc(0.8 * var(--cosmos-enabled))" }}
      />

      <div className="relative z-10 mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-300">
            OTQ Live Cosmos
          </p>
          <h1 className="text-4xl font-semibold text-white drop-shadow-lg">
            Mission Control Dashboard
          </h1>
          <p className="text-slate-300">
            Space-themed glassmorphism view of your bots: equity, drawdowns, and
            latest trades.
          </p>
          <BackdropToggle />
        </header>

        <SummaryCards state={state} />
        <EquityChart state={state} />
        <TradesTable state={state} />
      </div>
    </main>
  );
}
