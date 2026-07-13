"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "./lib/supabase-browser";

// This deployment may not have Supabase Auth configured yet (NEXT_PUBLIC_SUPABASE_URL /
// NEXT_PUBLIC_SUPABASE_ANON_KEY unset) — the free anonymous tier still has to work in that
// case, so this component must degrade to rendering nothing rather than throwing and taking
// the whole page down with it (unlike the dashboard, which is allowed to fail closed).
const SUPABASE_CONFIGURED = Boolean(
  process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

export function AuthHeader() {
  const [email, setEmail] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!SUPABASE_CONFIGURED) {
      return;
    }
    const supabase = createSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => subscription.subscription.unsubscribe();
  }, []);

  async function signOut() {
    const supabase = createSupabaseBrowserClient();
    await supabase.auth.signOut();
    router.refresh();
  }

  if (!SUPABASE_CONFIGURED) {
    return null;
  }

  return (
    <div className="auth-header">
      {email ? (
        <>
          <span>{email}</span>
          <button type="button" className="btn-secondary" onClick={() => void signOut()}>
            Sign out
          </button>
        </>
      ) : (
        <a href="/login" className="btn-secondary">
          Sign in
        </a>
      )}
    </div>
  );
}
