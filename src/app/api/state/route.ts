import { NextResponse } from "next/server";

import { loadState } from "@/lib/stateService";

export async function GET() {
  try {
    const state = await loadState();
    return NextResponse.json(state, {
      status: 200,
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    console.error("State API error", error);
    return NextResponse.json(
      { error: "Failed to load state" },
      { status: 500 },
    );
  }
}
