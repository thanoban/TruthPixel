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
with CORS configured to allow `http://localhost:3000` (already the default — see
`backend/app/config.py`'s `cors_allow_origins`).

## Status

Phase 0 scaffold — not yet built/run in this environment. See
[docs/ROADMAP.md](../docs/ROADMAP.md) for what's deferred (rate limiting, retention policy,
optional API-key signup for higher usage).
