# TruthPixel webapp

Public, self-serve consumer interface — "is this image real?" Anyone can upload one image
and get the same fused multi-signal report the B2B API returns, minus e-commerce-specific
context (no order/listing fields; L5 and the damage-plausibility agent no-op gracefully
when that context is absent — see [docs/USE_CASES.md](../docs/USE_CASES.md)).

This is a thin client. All detection logic lives in `backend/`; this app only uploads an
image to `POST /v1/claims` and renders the response. Do not add fusion/analyzer logic here.

## Run locally

```bash
cd webapp
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_URL at your backend
npm run dev
```

Requires the backend running at the URL in `.env.local` (default `http://localhost:8000`)
with CORS configured to allow the frontend origin (already the default for both
`http://localhost:3000` and `http://127.0.0.1:3000` — see `backend/app/config.py`'s
`cors_allow_origins` and `.env.example`).

**Auth note:** with the backend's default `API_AUTH_ENABLED=false`, every request runs as an
implicit local-dev tenant and this just works. If you turn auth on
(`API_AUTH_ENABLED=true`) for anything beyond local dev, you must also set
`PUBLIC_SUBMISSION_ENABLED=true` in the backend's `.env` — otherwise this webapp's anonymous
`POST /v1/claims` calls (it never sends an `X-API-Key`) will get a 401. See
`.env.example`'s "Auth & rate limits" section and `backend/app/auth.py`.

## Free-tier-then-login (Google + email/password via Supabase Auth)

Anonymous visitors get `PUBLIC_RATE_LIMIT_REQUESTS` free checks per IP (backend default: 5/
hour). A submission past that limit returns 429; this UI catches it and offers a link to
`/login` instead of just an error message. Signing in (Google or email/password) doesn't
remove the limit — it raises it, and re-scopes it to the account instead of the IP
(`PUBLIC_USER_RATE_LIMIT_REQUESTS`, default 25/hour) via a Supabase Auth JWT sent as
`Authorization: Bearer <token>` on submit, verified server-side in
`backend/app/supabase_auth.py`.

This is deliberately **not** a route-level auth gate like the dashboard's `middleware.ts` —
the page must stay fully usable anonymously up to the free limit. `app/auth-header.tsx` and
the submit flow in `app/page.tsx` both degrade gracefully (no crash, just skip the
authenticated path) if `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` aren't set.

Setup (one-time, same Supabase project as the dashboard and `DATABASE_URL`/`DIRECT_URL`):

1. Email/password is enabled by default in Supabase. Unlike the dashboard, this surface
   *does* expose public sign-up (`app/login/page.tsx`'s "Create one" toggle) — these are
   real end users, not pre-provisioned reviewers.
2. Google provider: same steps as `dashboard/README.md`'s Google setup, reusing the same
   Google Cloud OAuth client — add `http://localhost:3000` as an additional authorized
   JavaScript origin alongside the dashboard's `:3001`.
3. Copy `NEXT_PUBLIC_SUPABASE_URL` and the **anon public** key into `.env.local`.
4. Backend also needs `SUPABASE_URL` set (see `.env.example`) to verify the JWTs this page
   sends. Without it, the backend deliberately falls back to the anonymous IP limit instead
   of 401ing a signed-in user (`app/supabase_auth.py::SupabaseAuthNotConfigured`,
   `app/auth.py::allow_public_submission`) — set `SUPABASE_URL` to actually get the higher
   `PUBLIC_USER_RATE_LIMIT_REQUESTS` limit; until then, signing in raises no error but also
   doesn't raise the limit.

## Status

`npm run build` re-verified successfully in the current checkout after a UI polish pass that
keeps the same backend contract (`POST /v1/claims`) but upgrades the public experience into a
more production-feeling single-image upload/report surface. The browser round-trip still depends
on a running backend with anonymous submissions enabled as described above. See
[docs/ROADMAP.md](../docs/ROADMAP.md) for what's deferred (retention policy, optional
API-key signup for higher usage) and [docs/CORRECTIONS.md](../docs/CORRECTIONS.md) for the
latest full-system audit.
