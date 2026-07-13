# Running TruthPixel Locally — the full guide

> Step-by-step instructions to get every surface (backend API, public webapp, reviewer
> dashboard) running on your machine, from the fastest zero-config path up to every real
> integration this project has (Supabase Postgres + Auth, Vertex AI/Gemini, trained L1
> checkpoint, docker-compose infra). Part of the TruthPixel doc suite:
> [README.md](../README.md) · [ROADMAP.md](ROADMAP.md) · [EXECUTION_PLAN.md](EXECUTION_PLAN.md) ·
> [CORRECTIONS.md](CORRECTIONS.md) (source of every gotcha called out below) ·
> [modules/testing-dev-workflow.md](modules/testing-dev-workflow.md) (how to *work on* the
> code — this doc is how to *run* it)

## Contents

0. [Prerequisites](#0-prerequisites)
1. [Fastest path — backend only, zero config](#1-fastest-path--backend-only-zero-config)
2. [Add the public webapp](#2-add-the-public-webapp)
3. [Add the reviewer dashboard](#3-add-the-reviewer-dashboard)
4. [Local infra via docker-compose (Postgres/Redis/Qdrant/MinIO)](#4-local-infra-via-docker-compose-postgresredisqdrantminio)
5. [Real Supabase (Postgres + Auth) instead of local stubs](#5-real-supabase-postgres--auth-instead-of-local-stubs)
6. [Real Vertex AI (Gemini agents) instead of stub mode](#6-real-vertex-ai-gemini-agents-instead-of-stub-mode)
7. [The trained L1 checkpoint (AI-generation detection)](#7-the-trained-l1-checkpoint-ai-generation-detection)
8. [Other optional real integrations (L3/L4)](#8-other-optional-real-integrations-l3l4)
9. [Running the async queue for real (Celery + Redis)](#9-running-the-async-queue-for-real-celery--redis)
10. [Running tests](#10-running-tests)
11. [Running the demo script](#11-running-the-demo-script)
12. [Recommended setups by goal](#12-recommended-setups-by-goal)
13. [Troubleshooting](#13-troubleshooting)

---

## 0. Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Python 3.12+ | Backend | `python --version` |
| Node.js 20+ | webapp / dashboard | `node --version` |
| Docker (optional) | Local Postgres/Redis/Qdrant/MinIO, or building deploy images | `docker --version` |
| `gcloud` CLI (optional) | Real Vertex AI agents | `gcloud --version` |

Nothing else is required — every third-party integration (Vertex, Sightengine, TruFor,
Supabase, HF) is genuinely optional and degrades to a stub/fallback when unconfigured. Sections
5–8 below are all opt-in, not prerequisites for a working system.

---

## 1. Fastest path — backend only, zero config

Gets you a running API in under two minutes: SQLite (auto-created), local-disk artifact
storage, every signal layer running in its safe stub/fallback mode.

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate          # Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Confirm it's up:

```bash
curl http://localhost:8000/health
# {"status":"ok","vertex_agents":"stub","storage":"configured","queue":"eager"}
```

Submit a real claim:

```bash
curl -X POST http://localhost:8000/v1/claims \
  -F "image=@sample.jpg" -F "order_id=A123" -F "product_sku=SKU-9"
```

At this point every layer runs: L1 returns a neutral stub (no checkpoint/HF token yet), L2/L3
stub (no TruFor/Sightengine), L4 is **real** (EXIF always works, `c2patool` if installed), L5 is
**real** (hash+histogram always works). Fusion combines whatever's available — nothing crashes
because a layer is unconfigured, by design (see `backend/app/analyzers/base.py`'s error
isolation contract).

`backend/.env` doesn't exist yet at this point — that's fine, `Settings` just uses its defaults.
Copy `.env.example` → `backend/.env` once you want to start configuring things in the sections
below:

```bash
cp ../.env.example .env
```

---

## 2. Add the public webapp

Thin client over the same `POST /v1/claims` endpoint — no backend changes needed, just point it
at a running backend.

```bash
cd webapp
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000
```

`.env.local` at minimum needs:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

This alone gets you the **anonymous free-tier flow** — upload one image, get a report, no
login. The `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` lines in the same file are
for the optional login-for-higher-limits upgrade — see §5.3 below. Leave them blank and the page
still works; only the "sign in for a higher limit" path is unavailable (fails closed on just
that feature, not the whole page — confirmed in the file's own comment).

**Backend-side gate:** by default `API_AUTH_ENABLED=false`, so the webapp's anonymous
submissions work with zero backend config. If you turn auth on later, you also need
`PUBLIC_SUBMISSION_ENABLED=true` in `backend/.env` or every webapp submission 401s — see
`webapp/README.md`.

---

## 3. Add the reviewer dashboard

Queue view, claim detail, decision capture, audit trail, heatmap overlay — runs on port 3001 so
it can run alongside the webapp.

```bash
cd dashboard
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3001
```

`.env.local` at minimum:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

With the backend's default `API_AUTH_ENABLED=false`, `TRUTHPIXEL_DASHBOARD_API_KEY` can stay
unset — every proxied call runs as the implicit local-dev tenant. If you turn backend auth on,
you must issue a real tenant API key (§ below) and set `TRUTHPIXEL_DASHBOARD_API_KEY` to it, or
every dashboard call 503s.

The `NEXT_PUBLIC_SUPABASE_*` vars here gate the dashboard's own Google-sign-in wall (different
concern from the webapp's free-tier upgrade) — see §5.3.

---

## 4. Local infra via docker-compose (Postgres/Redis/Qdrant/MinIO)

Not required for anything in §1–3 above (SQLite + local-disk storage + `CELERY_TASK_ALWAYS_EAGER=true`
cover the default path completely). Use this section if you want to exercise the Postgres or
S3-storage code paths locally, or run a real Celery worker.

```bash
docker compose up -d          # all four services
docker compose up -d postgres # just one, if that's all you need
```

| Service | Port | What it's for |
|---|---|---|
| `postgres` | 5432 | Local Postgres alternative to SQLite — same schema via the same Alembic migrations |
| `redis` | 6379 | Required for a real (non-eager) Celery worker, see §9 |
| `minio` | 9000 (API), 9001 (console) | S3-compatible artifact storage alternative to local-disk |
| `qdrant` | 6333 | Provisioned for parity with `.env.example`'s `QDRANT_URL` — **not wired into any code path yet** (tracked as L5 v2 in ROADMAP.md); starting it does nothing today |

To point the backend at local Postgres instead of SQLite:
```
DATABASE_URL=postgresql+psycopg://truthpixel:truthpixel@localhost:5432/truthpixel
```
Restart the backend — `init_db()` runs Alembic migrations automatically against whichever DB
`DATABASE_URL` points at, so the schema is created for you, same as SQLite.

To point storage at local MinIO instead of local-disk:
```
STORAGE_BACKEND=s3
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=truthpixel-images
```
(Create the bucket once via the MinIO console at `http://localhost:9001`, login `minioadmin`/`minioadmin`.)

---

## 5. Real Supabase (Postgres + Auth) instead of local stubs

Supabase is the **production** database choice (see ROADMAP.md's standing decisions) — using it
locally too is optional but lets you test the exact same code path you'll deploy with. Two
independent things Supabase provides here: the Postgres database, and the Auth used by the
webapp/dashboard's optional login gates. You can use either without the other.

### 5.1 Supabase Postgres locally

Create a free Supabase project at supabase.com, then in `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<url-encoded-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
DIRECT_URL=postgresql+psycopg://postgres.<project-ref>:<url-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

**Four things that will genuinely break this if skipped** (all found live, documented in
`.env.example` and `docs/CORRECTIONS.md` 2026-07-12 (3)):
1. Driver prefix must be `postgresql+psycopg://` — a bare `postgresql://` selects psycopg2,
   which isn't installed, and startup fails with `ModuleNotFoundError`.
2. Use the **pooler** hostname (`aws-0-<region>.pooler.supabase.com`), not the direct
   `db.<ref>.supabase.co` host — the direct host is IPv6-only on many networks and fails to
   resolve on an IPv4-only connection.
3. Percent-encode any special character in the password (e.g. `@` → `%40`).
4. `DATABASE_URL` uses the pooler's **transaction-mode port 6543**; `DIRECT_URL` uses the
   **session-mode port 5432** and is used only for Alembic migrations (DDL needs one long-lived
   transaction, which the transaction pooler doesn't reliably support). Omit `DIRECT_URL` and
   Alembic falls back to `DATABASE_URL`.

Restart the backend — `alembic upgrade head` runs automatically against the real Supabase DB.

### 5.2 Verifying it's actually hitting Supabase, not silently falling back to SQLite

```bash
cd backend
.venv/Scripts/python -c "
from app.config import get_settings
s = get_settings()
print('database_url starts with:', s.database_url[:30])
"
```
Should print `postgresql+psycopg://...`, not `sqlite:///`.

### 5.3 Supabase Auth — webapp free-tier-then-login gate + dashboard sign-in wall

Same Supabase project as §5.1 (or a different one — Auth doesn't require also using Supabase
for the DB). From the Supabase dashboard → Project Settings → API, copy the Project URL and
`anon public` key (never the `service_role` key into a frontend `.env`).

**Webapp** (`webapp/.env.local`):
```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```
Enables: users can sign in (Google or email/password) to get a higher per-user rate limit
(`PUBLIC_USER_RATE_LIMIT_REQUESTS`, scoped to their Supabase user ID) instead of the anonymous
IP-based limit. Without these two vars, the login page throws but anonymous submission still
works — this feature fails closed on itself only, not the whole app.

**Dashboard** (`dashboard/.env.local`):
```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```
Enables: Google sign-in wall for reviewers. Unlike the webapp, **both vars are required** here —
`middleware.ts` throws on every request without them (fails closed on the whole dashboard, not
just a feature — different from the webapp's behavior, don't assume they match).

**Backend side** (`backend/.env`) — needed for the backend to *verify* the JWTs these frontends
send:
```
SUPABASE_URL=https://<project-ref>.supabase.co
```
This is the same project's URL, used only to fetch its JWKS endpoint for JWT verification — it
does not give the backend DB access on its own (that's `DATABASE_URL`).

---

## 6. Real Vertex AI (Gemini agents) instead of stub mode

Powers the `semantic_inspector`/`damage_plausibility`/`report_writer` agents
(`backend/app/agents/`) — without this, agent findings are template/stub text, and the fused
score is still computed (agents never gate the deterministic signals, only add commentary).

### 6.1 Auth — Application Default Credentials (no service-account key needed for local dev)

```bash
gcloud auth login                              # once, if not already logged in
gcloud auth application-default login          # sets up ADC the SDK reads automatically
gcloud config set project <your-project-id>
```

### 6.2 Enable the API (one-time per project)

```bash
gcloud services enable aiplatform.googleapis.com --project=<your-project-id>
```

### 6.3 Configure the backend

```
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
VERTEX_MODEL=gemini-2.5-flash
```

**Model-name gotcha, confirmed live:** `gemini-2.0-flash` (the Google AI Studio name) 404s as a
Vertex AI *publisher model* — Vertex's Gemini namespace differs from AI Studio's. Use
`gemini-2.5-flash`, confirmed working. If Google renames/deprecates it later, verify with
`gcloud ai models list` or a direct test call (§6.4) before assuming a new name works.

### 6.4 Verify it's actually calling Gemini, not silently in stub mode

```bash
cd backend
.venv/Scripts/python -c "
from app.agents.llm import get_vision_llm
llm = get_vision_llm()
print('llm:', type(llm).__name__ if llm else 'None (stub mode)')
if llm:
    r = llm.invoke('Reply with exactly one word: OK')
    print('response:', r.content)
"
```
Should print an `llm` type other than `None` and a real `OK` response, not a stub.

### 6.5 Billing note

The Vertex AI API needs an active billing account linked to the project — even light usage
requires this, it's not optional at the platform level. If you're using a student/promo credit
scoped specifically to "GenAI App Builder," confirm it actually covers `aiplatform.googleapis.com`
calls (Billing → Credits in the GCP Console) before assuming agent calls are free — this project
verified that distinction the hard way (see ROADMAP.md's standing decisions table).

---

## 7. The trained L1 checkpoint (AI-generation detection)

Without this, L1 runs on the HF ensemble (if `HF_API_TOKEN` is set) or the neutral stub. A
real trained checkpoint (0.9688 held-out AUROC, screenshot-robust — see
[BENCHMARK.md](BENCHMARK.md)) already exists from a prior training run; wiring it in is pure
config, no training needed to just *use* it:

```
L1_MODEL_PATH=./models/l1_clip_head.pt
L1_MODEL_DEVICE=cpu
```

Place `l1_clip_head.pt` at `backend/models/l1_clip_head.pt` (relative to where the backend
runs). CPU inference is fine for dev/demo volume (~1–3s/image) — `L1_MODEL_DEVICE=auto` also
works and picks GPU only if CUDA is actually available.

**No checkpoint file handy?** Train your own — see
[KAGGLE_TRAINING.md](KAGGLE_TRAINING.md) (recommended, faster free GPU) or
[COLAB_TRAINING.md](COLAB_TRAINING.md). Both produce the same `l1_clip_head.pt` format.

**Zero-training alternative:** set `HF_API_TOKEN` (get one at huggingface.co/settings/tokens,
read scope) instead — L1 falls back to an ensemble of pretrained HF Inference API detectors,
real accuracy, no training or local checkpoint required.

---

## 8. Other optional real integrations (L3/L4)

| Layer | Var(s) | Effect without it |
|---|---|---|
| L3 recapture | `SIGHTENGINE_API_USER`, `SIGHTENGINE_API_SECRET` | Neutral stub |
| L4 provenance | `c2patool` installed on `PATH` (or `C2PATOOL_PATH` pointed at it) | EXIF extraction still works (always-on); only the C2PA/Content-Credentials check is skipped |
| L2 forensics | `L2_TRUFOR_REPO_DIR`/`L2_TRUFOR_MODEL_FILE` (heavy — separate Python 3.7/torch-1.11/mmcv env, see [TRUFOR_SETUP.md](TRUFOR_SETUP.md)) | Falls back to classical forensics (`backend/app/forensics_classic.py` — ELA/noise/JPEG-ghost, always available, no setup) |

L4's `c2patool` and L2's classical-forensics fallback both work with **zero configuration** —
only TruFor (L2's higher-fidelity path) needs the heavy separate environment.

---

## 9. Running the async queue for real (Celery + Redis)

By default `CELERY_TASK_ALWAYS_EAGER=true` processes `POST /v1/claims/async` synchronously
inline — fine for local dev, but doesn't exercise the real queue/worker/webhook path.

```bash
docker compose up -d redis      # if not already running
```
In `backend/.env`:
```
CELERY_TASK_ALWAYS_EAGER=false
REDIS_URL=redis://localhost:6379/0
```
In a second terminal:
```bash
cd backend
celery -A app.celery_app worker --loglevel=info
```
Now `POST /v1/claims/async` actually queues, and `GET /v1/claims/{id}/status` reflects real
async progress instead of completing instantly.

---

## 10. Running tests

```bash
# From the repo root — runs both backend/ and ml/ suites
pytest -c pytest.ini

# Backend only
cd backend && .venv/Scripts/python -m pytest

# ML only
cd ml && python -m pytest
```

**Test isolation matters here** — this repo has real optional integrations (Vertex, L1
checkpoint, TruFor, Sightengine). Tests should never accidentally hit live external services;
`conftest.py`'s `_STUB_SAFE_ENV` forces isolated, unconfigured settings (including its own
throwaway SQLite file, not your real `backend/.env` values) specifically so `pytest` stays fast
and deterministic regardless of what's configured for live use. If you add a new setting,
add its stub-safe default there too — a real regression already happened here (see
`docs/CORRECTIONS.md` 2026-07-12 (3)) when `DIRECT_URL` was added to `Settings` without
updating `conftest.py`, and tests silently ran migrations against production infrastructure
until that isolation was restored.

**Frontend build checks** (type errors and route/config issues surface here, not in `next dev`):
```bash
cd webapp && npm run build
cd dashboard && npm run build
```

---

## 11. Running the demo script

`scripts/demo.py` is the tool behind ROADMAP.md's Phase 0 exit criterion — submits curated claim
images to a live backend and prints the fused report in plain English.

```bash
# Backend must already be running (§1)
backend/.venv/Scripts/python scripts/demo.py

# With real images for the full 5-case demo (2 cases work with zero external images)
backend/.venv/Scripts/python scripts/demo.py \
  --real-damage path/to/real.jpg \
  --ai-fake path/to/ai_generated.jpg \
  --inpainted path/to/manipulated.jpg
```

---

## 12. Recommended setups by goal

| Goal | Do this |
|---|---|
| Just try the API | §1 only |
| Try the public checker UI | §1 + §2 |
| Try the reviewer flow | §1 + §3 |
| Work on backend logic | §1, run tests (§10) before/after changes |
| Test the real production DB path | §1 + §5.1 |
| Test the free-tier-then-login / reviewer sign-in gates | §2/§3 + §5.3 |
| See real agent commentary, not template text | §1 + §6 |
| See a real (non-stub) AI-generation score | §1 + §7 (or just `HF_API_TOKEN` for zero-training) |
| Full production-parity local run | §1 + §2 + §3 + §5 (both) + §6 + §7 |
| Exercise the async queue for real | §1 + §9 |

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on backend startup after setting a Postgres `DATABASE_URL` | Bare `postgresql://` selects psycopg2, not installed | Use `postgresql+psycopg://` (§5.1) |
| `failed to resolve host db.<ref>.supabase.co` | Direct Supabase host is IPv6-only on many networks | Use the pooler host (§5.1) |
| Webapp login page throws | Missing `NEXT_PUBLIC_SUPABASE_URL`/`_ANON_KEY` | Set both, or leave both unset — a half-set pair is the actual broken state, not "unset" (§5.3) |
| Every dashboard request throws in `middleware.ts` | Dashboard's Supabase vars are stricter than the webapp's — both are required, no partial-degrade | Set both `NEXT_PUBLIC_SUPABASE_*` vars (§5.3) |
| Dashboard calls 503 after turning on `API_AUTH_ENABLED=true` | `TRUTHPIXEL_DASHBOARD_API_KEY` unset | Issue a tenant API key via the admin endpoints, set it (§3) |
| Webapp submissions 401 after turning on `API_AUTH_ENABLED=true` | `PUBLIC_SUBMISSION_ENABLED` still false | Set `PUBLIC_SUBMISSION_ENABLED=true` (§2) |
| Vertex call 404s: `Publisher model ... was not found` | Wrong Gemini model name for Vertex's namespace | Use `gemini-2.5-flash`, not `gemini-2.0-flash` (§6.3) |
| Agents silently return template/stub text | `GOOGLE_CLOUD_PROJECT` unset, or ADC not set up | Run `gcloud auth application-default login`, set `GOOGLE_CLOUD_PROJECT` (§6.1–6.4) |
| L1 always returns `score=0.5, confidence=0.1` | Neither `L1_MODEL_PATH` nor `HF_API_TOKEN` configured | Set one of them (§7) |
| A brand-new pytest failure after adding a `Settings` field | `conftest.py`'s stub-safe env wasn't updated for the new field, tests inherit your real `.env` value | Add a safe default for it to `conftest.py`'s `_STUB_SAFE_ENV` (§10) |
| Queued async claims stay `pending` forever | No Celery worker running, and `CELERY_TASK_ALWAYS_EAGER` isn't `true` | Either set `CELERY_TASK_ALWAYS_EAGER=true` for local dev, or run a real worker (§9) |
| `qdrant` container running but nothing changes | Qdrant isn't wired into any code path yet | Expected — it's provisioned for future parity only (§4) |
