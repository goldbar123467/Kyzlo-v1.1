import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const PASSWORD_HASH = process.env.DASH_PASSWORD_HASH;
const AUTH_COOKIE = "dash_auth";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Public paths
  const isPublic =
    pathname.startsWith("/api/health") ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/_next");

  if (isPublic) {
    return NextResponse.next();
  }

  if (!PASSWORD_HASH) {
    return new NextResponse("Auth not configured", { status: 500 });
  }

  const cookie = req.cookies.get(AUTH_COOKIE)?.value;
  if (cookie === PASSWORD_HASH) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("redirect", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
