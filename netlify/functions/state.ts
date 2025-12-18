import fs from "node:fs/promises";
import path from "node:path";

import type { Handler } from "@netlify/functions";

import { validateState } from "../../src/lib/stateSchema";

const LOCAL_STATE_PATH =
  process.env.LOCAL_STATE_PATH ??
  path.resolve(process.cwd(), "../reports/state.json");

const FIXTURE_PATH =
  process.env.STATE_FIXTURE_PATH ??
  path.resolve(process.cwd(), "fixtures/state.sample.json");

const REMOTE_URL =
  process.env.REPO_RAW_URL ?? process.env.STATE_REMOTE_URL ?? "";

const GITHUB_TOKEN = process.env.GITHUB_TOKEN ?? "";

async function readJson(filePath: string) {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw) as unknown;
}

async function loadLocal() {
  const data = await readJson(LOCAL_STATE_PATH);
  return validateState(data);
}

async function loadFixture() {
  const data = await readJson(FIXTURE_PATH);
  return validateState(data);
}

async function loadRemote() {
  if (!REMOTE_URL) {
    throw new Error("REPO_RAW_URL/STATE_REMOTE_URL is not set for remote mode");
  }

  const res = await fetch(REMOTE_URL, {
    headers: GITHUB_TOKEN ? { Authorization: `Bearer ${GITHUB_TOKEN}` } : {},
  });

  if (!res.ok) {
    throw new Error(`Remote fetch failed: ${res.status} ${res.statusText}`);
  }

  const data = (await res.json()) as unknown;
  return validateState(data);
}

export const handler: Handler = async () => {
  const mode =
    (process.env.NEXT_PUBLIC_STATE_MODE as "local" | "mock" | "remote" | undefined) ??
    (process.env.NETLIFY_DEV === "true" ? "local" : "remote");

  try {
    if (mode === "mock") {
      return {
        statusCode: 200,
        body: JSON.stringify(await loadFixture()),
      };
    }

    if (mode === "remote" && process.env.NETLIFY_DEV !== "true") {
      return {
        statusCode: 200,
        body: JSON.stringify(await loadRemote()),
      };
    }

    // default to local in dev
    return {
      statusCode: 200,
      body: JSON.stringify(await loadLocal()),
    };
  } catch (error) {
    console.error("[netlify][state] error", error);

    // Last-chance fallback to fixture
    try {
      const fallback = await loadFixture();
      return {
        statusCode: 200,
        body: JSON.stringify(fallback),
      };
    } catch {
      return {
        statusCode: 500,
        body: JSON.stringify({ error: "Failed to load state" }),
      };
    }
  }
};
