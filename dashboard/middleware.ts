import { NextResponse, type NextRequest } from "next/server";
import { createSupabaseServerClient } from "./app/lib/supabase-server";

// Gates every dashboard route behind a Supabase session (Google sign-in) except /login and
// the OAuth callback itself. This is a UI access gate for reviewers only — it does not
// change the backend's own tenant/API-key auth (app/auth.py), which stays independent.
export async function middleware(request: NextRequest) {
  const response = NextResponse.next({ request });

  if (
    request.nextUrl.pathname.startsWith("/login") ||
    request.nextUrl.pathname.startsWith("/auth/callback")
  ) {
    return response;
  }

  const supabase = createSupabaseServerClient(request, response);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectTo", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
