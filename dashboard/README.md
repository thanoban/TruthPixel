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
key is baked in at build/env time, not selectable per-session in the UI). Artifact previews use
short-lived backend-signed URLs so `<img>` previews and download links still work when the raw
artifact endpoint is protected by `X-API-Key`.

For Cloud Run deployments, set:

```bash
NEXT_PUBLIC_API_URL=https://<cloud-run-service-url>
NEXT_PUBLIC_API_KEY=<issued-tenant-api-key>
```

The exact backend setup and smoke checklist live in
[`docs/CLOUD_RUN_SUPABASE.md`](../docs/CLOUD_RUN_SUPABASE.md).

## Status

Verified against backend auth-on tests for the dashboard API surface: tenant issuance, keyed
queue/detail/status/audit/decision requests, missing-key 401s, and cross-tenant 404s. Still
not production-hardened: no tenant switcher.
