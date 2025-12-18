import fs from "node:fs/promises";

import { getStateConfig, type StateMode } from "./config";
import {
  type DailyStats,
  type ReporterState,
  type TradeRecord,
  validateState,
} from "./stateSchema";

async function loadJsonFile<T>(filePath: string): Promise<T> {
  const contents = await fs.readFile(filePath, "utf8");
  return JSON.parse(contents) as T;
}

async function loadLocalState(localStatePath: string): Promise<ReporterState> {
  const data = await loadJsonFile<unknown>(localStatePath);
  return validateState(data);
}

async function loadMockState(fixturePath: string): Promise<ReporterState> {
  const data = await loadJsonFile<unknown>(fixturePath);
  return validateState(data);
}

async function loadRemoteState(remoteUrl: string): Promise<ReporterState> {
  if (!remoteUrl) {
    throw new Error("STATE_REMOTE_URL or NEXT_PUBLIC_STATE_URL is not set");
  }

  const res = await fetch(remoteUrl, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(
      `Remote state fetch failed: ${res.status} ${res.statusText}`,
    );
  }

  const data = (await res.json()) as unknown;
  return validateState(data);
}

export async function loadState(options?: {
  mode?: StateMode;
}): Promise<ReporterState> {
  const config = getStateConfig(options?.mode);

  try {
    if (config.mode === "mock") {
      return await loadMockState(config.fixturePath);
    }

    if (config.mode === "remote") {
      return await loadRemoteState(config.remoteUrl);
    }

    // default: local
    return await loadLocalState(config.localStatePath);
  } catch (err) {
    // As a resilience measure, fall back to mock fixture if available.
    if (config.mode !== "mock") {
      try {
        return await loadMockState(config.fixturePath);
      } catch (fallbackErr) {
        console.error("State fallback failed:", fallbackErr);
      }
    }

    throw err;
  }
}

// Convenience helpers for future use
export type { ReporterState, TradeRecord, DailyStats };
