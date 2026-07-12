import { createBrowserClient } from "@supabase/ssr";

// Webapp auth (Google + email/password via Supabase Auth) — used only after the free
// anonymous-IP limit (backend PUBLIC_RATE_LIMIT_REQUESTS) is hit. Signed-in users get a
// higher, account-scoped rate limit (PUBLIC_USER_RATE_LIMIT_REQUESTS) instead of an
// IP-scoped one — see backend/app/auth.py::allow_public_submission. This page stays usable
// anonymously; there is no route-level auth gate here (unlike dashboard/middleware.ts).
export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set — see webapp/README.md"
    );
  }
  return createBrowserClient(url, anonKey);
}
