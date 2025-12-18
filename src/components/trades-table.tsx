"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import type { ReporterState, TradeRecord } from "@/lib/types";

type Props = {
  state: ReporterState;
};

const columnHelper = createColumnHelper<TradeRecord>();

const columns = [
  columnHelper.accessor("timestamp", {
    header: "Time",
    cell: (info) => new Date(info.getValue()).toLocaleString(),
  }),
  columnHelper.accessor("symbol", { header: "Symbol" }),
  columnHelper.accessor("side", {
    header: "Side",
    cell: (info) => info.getValue().toUpperCase(),
  }),
  columnHelper.accessor("pnl", {
    header: "P&L",
    cell: (info) => {
      const val = info.getValue();
      const positive = val >= 0;
      return (
        <span className={positive ? "text-emerald-300" : "text-rose-300"}>
          {val >= 0 ? "+" : ""}
          {val.toFixed(2)}
        </span>
      );
    },
  }),
  columnHelper.accessor("pnl_pct", {
    header: "Return",
    cell: (info) => {
      const val = info.getValue();
      const positive = val >= 0;
      return (
        <span className={positive ? "text-emerald-300" : "text-rose-300"}>
          {val >= 0 ? "+" : ""}
          {val.toFixed(2)}%
        </span>
      );
    },
  }),
  columnHelper.accessor("exit_reason", { header: "Reason" }),
];

export function TradesTable({ state }: Props) {
  const table = useReactTable({
    data: state.trades.slice(-20).reverse(), // latest first
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.14em] text-slate-300">
            Recent Trades
          </p>
          <h2 className="text-lg font-semibold text-white">Last 20</h2>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-100">
          <thead className="text-xs uppercase text-slate-300">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-white/5">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 font-medium">
                    {header.isPlaceholder
                      ? null
                      : header.column.columnDef.header?.toString()}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-white/5/10 last:border-none hover:bg-white/5"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2 text-slate-200">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {!table.getRowModel().rows.length && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-4 text-slate-400"
                >
                  No trades yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
