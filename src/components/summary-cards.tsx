"use client";

import type { DailyStats, ReporterState } from "@/lib/types";

type Props = {
  state: ReporterState;
};

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}%`;
}

function getLatestDay(state: ReporterState): DailyStats | null {
  return state.daily_stats.at(-1) ?? null;
}

export function SummaryCards({ state }: Props) {
  const latest = getLatestDay(state);

  const cards = [
    {
      label: "Current Equity",
      value: latest ? formatCurrency(latest.ending_equity) : "—",
      accent: "from-[#5bffec] to-[#4da8ff]",
    },
    {
      label: "Daily P&L",
      value: latest ? formatCurrency(latest.daily_pnl) : "—",
      accent: "from-[#8a5bff] to-[#ff7ee2]",
    },
    {
      label: "Win Rate",
      value: latest ? formatPercent(latest.win_rate) : "—",
      accent: "from-[#4da8ff] to-[#8a5bff]",
    },
    {
      label: "Max Drawdown",
      value: latest ? formatPercent(latest.max_drawdown_pct) : "—",
      accent: "from-[#ff7ee2] to-[#ff9b4a]",
    },
    {
      label: "Trades (total)",
      value: state.trades.length.toString(),
      accent: "from-[#5bffec] to-[#8a5bff]",
    },
    {
      label: "Last Updated",
      value: latest ? latest.date : "—",
      accent: "from-[#4da8ff] to-[#5bffec]",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="glass glow relative overflow-hidden rounded-2xl p-4"
        >
          <div
            className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${card.accent} opacity-70`}
          />
          <p className="text-xs uppercase tracking-[0.16em] text-slate-300">
            {card.label}
          </p>
          <p className="mt-2 text-2xl font-semibold text-white drop-shadow-sm">
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}
