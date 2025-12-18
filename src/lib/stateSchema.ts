import { z } from "zod";

export const tradeSchema = z.object({
  timestamp: z.string().datetime(),
  symbol: z.string(),
  side: z.enum(["long", "short"]),
  entry_price: z.number(),
  exit_price: z.number(),
  shares: z.number(),
  pnl: z.number(),
  pnl_pct: z.number(),
  hold_time_minutes: z.number(),
  exit_reason: z.string(),
});

export const dailyStatsSchema = z.object({
  date: z.string().date(),
  starting_equity: z.number(),
  ending_equity: z.number(),
  daily_pnl: z.number(),
  daily_return_pct: z.number(),
  trades: z.number(),
  winners: z.number(),
  losers: z.number(),
  win_rate: z.number(),
  sharpe_intraday: z.number(),
  max_drawdown_pct: z.number(),
  // Optional future fields
  avg_win: z.number().optional(),
  avg_loss: z.number().optional(),
  max_win: z.number().optional(),
  max_loss: z.number().optional(),
});

export const stateSchema = z.object({
  trades: z.array(tradeSchema),
  daily_stats: z.array(dailyStatsSchema),
});

export type TradeRecord = z.infer<typeof tradeSchema>;
export type DailyStats = z.infer<typeof dailyStatsSchema>;
export type ReporterState = z.infer<typeof stateSchema>;

export function validateState(data: unknown): ReporterState {
  return stateSchema.parse(data);
}
