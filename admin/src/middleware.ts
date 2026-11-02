import { NextResponse, type NextRequest } from "next/server";

import { ADMIN_COOKIE } from "@/lib/constants";

/**
 * Send visitors without a session to /login. This only checks that the cookie exists;
 * the API validates the token itself on every call (see lib/api.ts).
 */
export function middleware(request: NextRequest) {
  if (request.cookies.has(ADMIN_COOKIE)) return NextResponse.next();

  const login = new URL("/login", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
