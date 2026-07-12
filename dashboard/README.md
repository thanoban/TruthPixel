# TruthPixel reviewer dashboard

Internal, tenant-scoped reviewer UI — claim queue, per-claim signal breakdown, heatmap
overlay (original upload + TruFor anomaly map with an opacity slider), audit trail, and the
decision form (`POST /v1/claims/{id}/decision`). Runs on `:3001` by default.

This is a thin client. All detection/fusion logic lives in `backend/`; this app only calls
the `/v1/claims*` API (`app/api.ts`) and renders the response. Do not add analyzer or fusion
logic here.

## Run locally

```bash
cd dashboard
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL / NEXT_PUBLIC_API_KEY
npm run dev   # http://localhost:3001
```

Set `NEXT_PUBLIC_API_URL` if the backend isn't at the default `http://localhost:8000`
(see `app/api.ts`). CORS for `:3001` is already in `backend/app/config.py`'s
`cors_allow_origins` default, for both `localhost` and `127.0.0.1`.

**Auth note:** with the backend's default `API_AUTH_ENABLED=false`, every request runs as an
implicit local-dev tenant and this just works — `NEXT_PUBLIC_API_KEY` can stay unset. If you
turn `API_AUTH_ENABLED=true`, set `NEXT_PUBLIC_API_KEY` to a tenant key issued via
`POST /v1/admin/tenants/{tenant_id}/api-keys` (see `backend/app/auth.py`) — `app/api.ts`
sends it as `X-API-Key` on every request when present. Still missing: a tenant switcher (one
key is baked in at build/env time, not selectable per-session in the UI).

## Reviewer login (Google + email/password via Supabase Auth)

This is a separate, independent auth layer from the tenant/API-key auth above — it gates
*who can open this UI at all* (`middleware.ts`), not the backend's own API authorization.
Every route except `/login` and `/auth/callback` redirects to `/login` without a valid
Supabase session.

Setup (one-time, in the Supabase project already used for `DATABASE_URL`/`DIRECT_URL`):

1. **Email/password** is enabled by default in Supabase — nothing to configure. This is an
   internal tool, so there's no public sign-up UI; provision reviewer accounts yourself via
   Supabase dashboard → Authentication → Users → Add user.
2. **Google provider:** Supabase dashboard → Authentication → Providers → Google → enable,
   then paste a Google Cloud OAuth Client ID/Secret (Google Cloud Console → APIs & Services
   → Credentials → Create OAuth client ID → Web application). Authorized redirect URI:
   `https://<project-ref>.supabase.co/auth/v1/callback`. Authorized JavaScript origin for
   local dev: `http://localhost:3001`.
3. Copy the project's `NEXT_PUBLIC_SUPABASE_URL` and **anon public** key (Project Settings →
   API — never the `service_role` key) into `.env.local`.

Without both env vars set, `middleware.ts` throws on every request — fails closed
(no dashboard access), not open. See `app/lib/supabase-server.ts`, `app/lib/
supabase-browser.ts`, `middleware.ts`, `app/login/page.tsx`.

The "Reviewer ID" field on a claim's decision form now prefills from the signed-in Google/
email identity instead of a free-text guess, tying the audit trail to a real account — still
editable if someone is recording a decision on a colleague's behalf.

## Status

Verified working end-to-end against a live local backend: queue list, claim detail (with
heatmap overlay), decision submission, and audit-trail fetch all exercised successfully
(`.codex/runlogs/dashboard.out.log` / `backend.out.log` — real 200s on
`GET /v1/claims`, `GET /v1/claims/{id}`, `POST /v1/claims/{id}/decision`,
`GET /v1/claims/{id}/audit`, `GET /v1/claims/{id}/artifacts/{artifact_id}`). `X-API-Key`
support added 2026-07-09 (see [docs/CORRECTIONS.md](../docs/CORRECTIONS.md)) but not yet
re-verified against a live `API_AUTH_ENABLED=true` backend — only against the default
auth-disabled path. Still not production-hardened: no tenant switcher.
