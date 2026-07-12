"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createSupabaseBrowserClient } from "../lib/supabase-browser";

type Mode = "sign-in" | "sign-up";

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
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const searchParams = useSearchParams();
  const router = useRouter();
  const redirectTo = searchParams.get("redirectTo") || "/";
  const limitReached = searchParams.get("reason") === "limit";

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

  async function onSubmitEmail(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const supabase = createSupabaseBrowserClient();
      if (mode === "sign-up") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}` },
        });
        if (signUpError) {
          throw signUpError;
        }
        if (!data.session) {
          setNotice("Check your email to confirm your account, then sign in.");
          setMode("sign-in");
          return;
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) {
          throw signInError;
        }
      }
      router.push(redirectTo);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="hero-grid" style={{ gridTemplateColumns: "1fr" }}>
        <div className="hero-card" style={{ maxWidth: 440, margin: "40px auto" }}>
          <p className="eyebrow">TruthPixel account</p>
          <h1>{mode === "sign-in" ? "Sign in to keep checking images" : "Create a free account"}</h1>
          {limitReached && (
            <p className="tagline">
              You've used your free anonymous checks for now. Sign in (or create a free account)
              to keep going with a higher limit.
            </p>
          )}
          {error && <p className="error-banner">{error}</p>}
          {notice && <p className="notice-banner">{notice}</p>}

          <button type="button" onClick={() => void signInWithGoogle()} disabled={loading}>
            {loading ? "Redirecting..." : "Continue with Google"}
          </button>

          <div className="login-divider">
            <span>or</span>
          </div>

          <form className="login-form" onSubmit={(event) => void onSubmitEmail(event)}>
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
                minLength={6}
                autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
              />
            </label>
            <button type="submit" disabled={loading || !email || !password}>
              {loading
                ? "Please wait..."
                : mode === "sign-in"
                  ? "Sign in with email"
                  : "Create account"}
            </button>
          </form>

          <p className="login-note">
            {mode === "sign-in" ? (
              <>
                Don't have an account?{" "}
                <button type="button" className="link-button" onClick={() => setMode("sign-up")}>
                  Create one
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button type="button" className="link-button" onClick={() => setMode("sign-in")}>
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>
      </section>
    </main>
  );
}
