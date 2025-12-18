import crypto from "node:crypto";

import { NextResponse } from "next/server";

const PASSWORD_HASH = process.env.DASH_PASSWORD_HASH;
const AUTH_COOKIE = "dash_auth";

function hash(input: string) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

export async function POST(request: Request) {
  try {
    if (!PASSWORD_HASH) {
      return NextResponse.json(
        { error: "Auth not configured" },
        { status: 500 },
      );
    }

    const body = (await request.json()) as { password?: string };
    const candidate = body.password ?? "";
    const candidateHash = hash(candidate);

    if (candidateHash !== PASSWORD_HASH) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const res = NextResponse.json({ ok: true });
    res.cookies.set(AUTH_COOKIE, PASSWORD_HASH, {
      httpOnly: true,
      sameSite: "lax",
      secure: true,
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: "/",
    });
    return res;
  } catch (_error) {
    return NextResponse.json({ error: "Bad request" }, { status: 400 });
  }
}
