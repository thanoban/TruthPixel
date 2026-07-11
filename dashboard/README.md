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
cp .env.local.example .env.local   # set TRUTHPIXEL_API_URL / TRUTHPIXEL_API_KEY as needed
npm run dev   # http://localhost:3001
```

**Recommended env for a pilot:**
- `TRUTHPIXEL_API_URL`: backend origin the dashboard should proxy to. Server-side, preferred.
- `TRUTHPIXEL_API_KEY`: tenant API key for reviewer access when `API_AUTH_ENABLED=true`. Server-side, preferred.
- `NEXT_PUBLIC_DASHBOARD_TENANT_LABEL`: optional UI label for the current reviewer workspace.
- `NEXT_PUBLIC_DEFAULT_REVIEWER_ID`: optional default reviewer ID prefill for the decision form.

Legacy compatibility remains:
- `NEXT_PUBLIC_API_URL`: fallback only if `TRUTHPIXEL_API_URL` is unset.
- `NEXT_PUBLIC_API_KEY`: fallback only if `TRUTHPIXEL_API_KEY` is unset. Avoid for pilots because it is exposed to browser code.

The dashboard now calls same-origin Next.js proxy routes under `/api/*`; those routes inject the
server-side tenant key when configured, then forward to the existing backend `/v1/claims*`
contract. CORS for `:3001` is still useful for local development and is already in
`backend/app/config.py`'s `cors_allow_origins` default, for both `localhost` and `127.0.0.1`.

**Auth note:** with the backend's default `API_AUTH_ENABLED=false`, every request runs as an
implicit local-dev tenant and this just works — both API-key vars can stay unset. If you turn
`API_AUTH_ENABLED=true`, issue a tenant key via `POST /v1/admin/tenants/{tenant_id}/api-keys`
(see `backend/app/auth.py`) and place it in `TRUTHPIXEL_API_KEY`. Still intentionally missing
for this pilot stage: a per-session tenant switcher or reviewer login/SSO; this remains a
single-tenant reviewer surface keyed at env/runtime level.

## Status

Verified working end-to-end against a live local backend: queue list, claim detail (with
heatmap overlay), decision submission, and audit-trail fetch all exercised successfully
(`.codex/runlogs/dashboard.out.log` / `backend.out.log` — real 200s on
`GET /v1/claims`, `GET /v1/claims/{id}`, `POST /v1/claims/{id}/decision`,
`GET /v1/claims/{id}/audit`, `GET /v1/claims/{id}/artifacts/{artifact_id}`). This pilot pass
hardens the reviewer path by moving auth to the server-side dashboard proxy, persisting the
reviewer ID locally, and removing the dangerous default "reject" choice in the decision form.
Still not production-hardened: no per-session tenant switcher, no reviewer login/SSO, and the
dashboard remains a thin single-tenant surface over the current backend API contract.
