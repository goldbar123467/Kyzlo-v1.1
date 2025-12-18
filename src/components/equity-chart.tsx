"use client";

import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type { ReporterState } from "@/lib/types";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

type Props = { state: ReporterState };

export function EquityChart({ state }: Props) {
  if (!state.daily_stats.length) {
    return (
      <div className="glass rounded-2xl p-4 text-slate-300">
        No equity data yet.
      </div>
    );
  }

  const labels = state.daily_stats.map((d) => d.date);
  const equity = state.daily_stats.map((d) => d.ending_equity);
  const peak = equity.reduce<number[]>((acc, val, idx) => {
    if (idx === 0) return [val];
    acc.push(Math.max(acc[idx - 1], val));
    return acc;
  }, []);
  const drawdown = equity.map(
    (val, idx) => ((val - peak[idx]) / peak[idx]) * 100,
  );

  const data = {
    labels,
    datasets: [
      {
        label: "Equity",
        data: equity,
        borderColor: "#5bffec",
        backgroundColor: "rgba(91, 255, 236, 0.12)",
        fill: true,
        tension: 0.25,
        pointRadius: 0,
      },
      {
        label: "Drawdown (%)",
        data: drawdown,
        yAxisID: "y1",
        borderColor: "#ff7ee2",
        backgroundColor: "rgba(255, 126, 226, 0.12)",
        tension: 0.25,
        pointRadius: 0,
      },
    ],
  };

  const options = {
    responsive: true,
    interaction: { mode: "index" as const, intersect: false },
    plugins: {
      legend: {
        labels: {
          color: "#e6ecff",
          boxWidth: 10,
        },
      },
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.9)",
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        titleColor: "#e6ecff",
        bodyColor: "#e6ecff",
      },
    },
    scales: {
      x: {
        ticks: { color: "#9fb3ff" },
        grid: { color: "rgba(255,255,255,0.06)" },
      },
      y: {
        ticks: { color: "#9fb3ff" },
        grid: { color: "rgba(255,255,255,0.06)" },
      },
      y1: {
        position: "right" as const,
        ticks: {
          color: "#ffb3f0",
          callback: (value: number | string) => `${value}%`,
        },
        grid: { display: false },
      },
    },
  };

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-slate-300">
            Performance
          </p>
          <h2 className="text-lg font-semibold text-white">
            Equity & Drawdown
          </h2>
        </div>
      </div>
      <div className="h-80">
        <Line options={options} data={data} />
      </div>
    </div>
  );
}
