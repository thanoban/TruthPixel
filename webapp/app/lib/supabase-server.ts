import { createServerClient } from "@supabase/ssr";
import type { NextRequest, NextResponse } from "next/server";

// Only used by app/auth/callback/route.ts to exchange the OAuth code for a session. The
// webapp has no middleware session check (see supabase-browser.ts) — this is narrower in
// scope than dashboard's identical-looking helper.
export function createSupabaseServerClient(req: NextRequest, res: NextResponse) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set — see webapp/README.md"
    );
  }
  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return req.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => {
          req.cookies.set(name, value);
          res.cookies.set(name, value, options);
        });
      },
    },
  });
}
