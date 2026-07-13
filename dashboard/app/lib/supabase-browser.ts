import { createBrowserClient } from "@supabase/ssr";

// Reviewer dashboard auth (Google via Supabase Auth) — gates who can open this UI. Separate
// from the backend's own tenant/API-key auth (app/auth.py), which is unchanged: this only
// controls dashboard access, not backend API authorization. See dashboard/README.md.
export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set — see dashboard/README.md"
    );
  }
  return createBrowserClient(url, anonKey);
}
