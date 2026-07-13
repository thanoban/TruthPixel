"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createSupabaseBrowserClient } from "../lib/supabase-browser";

// useSearchParams() opts the whole page out of static prerendering unless wrapped in
// Suspense — Next.js's build fails without this (missing-suspense-with-csr-bailout).
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const searchParams = useSearchParams();
  const router = useRouter();
  const redirectTo = searchParams.get("redirectTo") || "/";

  async function signInWithGoogle() {
    setLoading(true);
    setError(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`,
        },
      });
      if (signInError) {
        throw signInError;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Google sign-in");
      setLoading(false);
    }
  }

  async function signInWithEmail(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) {
        throw signInError;
      }
      router.push(redirectTo);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sign in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <div className="frame login-card">
        <span className="bracket-tl" /><span className="bracket-tr" /><span className="bracket-bl" /><span className="bracket-br" />
        <div className="eyebrow">
          <span className="eyebrow-dot" />
          TruthPixel reviewer dashboard
        </div>
        <h1>Sign in to review claims</h1>
        <p className="hero-copy" style={{ margin: 0 }}>
          Reviewer access is restricted to accounts provisioned for your organization.
        </p>
        {error && <p className="error">{error}</p>}
        <button
          type="button"
          className="btn-primary"
          onClick={() => void signInWithGoogle()}
          disabled={loading}
        >
          {loading ? "Redirecting..." : "Sign in with Google"}
        </button>

        <div className="login-divider">
          <span>or</span>
        </div>

        <form className="login-form" onSubmit={(event) => void signInWithEmail(event)}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <button type="submit" className="btn-secondary" disabled={loading || !email || !password}>
            {loading ? "Signing in..." : "Sign in with email"}
          </button>
        </form>
        <p className="login-note">
          No account yet? Ask an admin to invite you via the Supabase project's Auth &gt; Users
          panel — self-signup is intentionally not exposed on this internal tool.
        </p>
      </div>
    </main>
  );
}
