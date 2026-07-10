# TruthPixel

**Multi-signal image-integrity verification for e-commerce return / refund fraud.**

Given a customer-submitted "damaged product" photo, TruthPixel returns a calibrated
fraud-risk score with an explainable, region-level report — combining AI-generation
detection, edit forensics, screenshot/recapture detection, metadata provenance, and a
product cross-check against the seller's own listing photos. A human reviewer makes the
final call.

> Not "an AI detector." The moat is **fusion + e-commerce context**, not any single model.

## Documentation

| Doc | Covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Master design: positioning, signal layers, fusion, system architecture |
| [docs/COMPETITORS.md](docs/COMPETITORS.md) | Full landscape — tools, models, APIs, datasets, our stance on each |
| [docs/ML_PLAN.md](docs/ML_PLAN.md) | What we train, screenshot augmentation, honest evaluation protocol |
| [docs/COLAB_TRAINING.md](docs/COLAB_TRAINING.md) | No local GPU: train the L1 head on Colab, all data/checkpoints in Google Drive |
| [docs/KAGGLE_TRAINING.md](docs/KAGGLE_TRAINING.md) | Same, on Kaggle's free GPU tier instead (use if Colab's quota runs out) |
| [docs/AGENTS.md](docs/AGENTS.md) | LangGraph multi-agent system (Gemini on Vertex AI), cost gating |
| [docs/USE_CASES.md](docs/USE_CASES.md) | Product surfaces (API / reviewer dashboard / public webapp) and use cases beyond return fraud |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase 0–2 checklists and standing decisions |
| [docs/CORRECTIONS.md](docs/CORRECTIONS.md) | Full-system audit log — bugs found/fixed, finished vs. remaining, dated newest-first |

## The five signal layers

| # | Layer | What it catches |
|---|---|---|
| L1 | AI-generation detection | Fully synthetic images (SDXL, Flux, Midjourney, …) |
| L2 | Manipulation / edit forensics | Inpainting, splicing, copy-move (with region heatmap) |
| L3 | Recapture / screenshot | Photo-of-screen / screenshot evasion — a fraud signal in itself |
| L4 | Metadata & provenance | EXIF, C2PA / Content Credentials, SynthID (neutral-weight) |
| L5 | E-commerce context cross-check | Claim photo vs. seller listing; reused/stolen damage photos |

A calibrated **fusion meta-classifier** stacks all five into one risk score with per-signal
explanations (SHAP). Output is a confidence-scored report, never an automatic binary verdict.

## Repo layout

```
backend/     FastAPI service: API, orchestrator, analyzers (L1–L5), fusion, persistence,
             artifact storage, async job queue (see backend/app/{storage,artifacts,jobs}.py)
ml/          Model training & evaluation — `layer1_aigen/` plus `fusion/` tooling
dashboard/   Reviewer dashboard scaffold — queue, claim detail, decision capture, heatmap overlay
webapp/      Public self-serve webapp — anyone checks one image, no tenant/order context
docs/        Architecture & design docs
```

`ml/fusion/` also exists now for learned-fusion feature assembly/training export. The main
remaining repo-layout gaps are `ml/recapture/`, `ml/datagen/`, and any deployment `scripts/`
you decide to add. Product surfaces today: B2B API, reviewer dashboard scaffold, and the
public webapp; see [docs/USE_CASES.md](docs/USE_CASES.md) for the current surface-by-surface
status.

## Quickstart (local-first)

```bash
# 1. Backend API — SQLite DB + local-disk artifact storage are created automatically
#    on first run via Alembic migrations (no external services, no manual `alembic upgrade`
#    needed — init_db() runs it for you). L1 has a local-checkpoint path plus an HF-ensemble
#    path; L2 has a TruFor adapter. Both fall back safely when unconfigured.
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 2. Synchronous claim (analyzes inline, returns the full report)
curl -X POST http://localhost:8000/v1/claims \
  -F "image=@sample.jpg" -F "order_id=A123" -F "product_sku=SKU-9"

# 3. Async claim (queues via Celery, poll for status) — see note below
curl -X POST http://localhost:8000/v1/claims/async -F "image=@sample.jpg"
curl http://localhost:8000/v1/claims/<claim_id>/status

# 4. Or use the public webapp (thin client over the same API; untested end-to-end so far)
cd ../webapp
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000

# 5. Run the repo test suite from the project root
cd ..
backend\.venv\Scripts\python -m pytest
```

`/v1/claims/async` needs a real Celery worker + Redis to actually process anything —
`celery -A app.celery_app worker --loglevel=info` from `backend/`, with `docker compose up -d`
for Redis. Without a worker, queued claims stay `pending` forever. For local dev without
either, set `CELERY_TASK_ALWAYS_EAGER=true` (processes synchronously inline — same as tests).

Optional local infra (Postgres / Redis / Qdrant / MinIO) via `docker compose up -d`. Not
required for the synchronous endpoint — defaults are SQLite + local-disk storage. Postgres and
MinIO/S3 are real, working alternatives (`DATABASE_URL`, `STORAGE_BACKEND=s3`); Qdrant is the
one service in docker-compose not wired into any code path yet (see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §6). L1 still needs either `HF_API_TOKEN` (HF
ensemble) or `L1_MODEL_PATH` (local checkpoint), and L2 still needs the external TruFor repo
and weights to stop falling back to its neutral path.

**Schema changes** go through Alembic (`backend/alembic/`), not `Base.metadata.create_all()`
directly — `init_db()` runs `alembic upgrade head` automatically on every startup (fast no-op
once a DB is current). For a manual check or CLI migration work: `cd backend && alembic current`
/ `alembic upgrade head` (reads `DATABASE_URL` from the same `.env`/environment as the app).
New schema changes should be a real migration (`alembic revision --autogenerate -m "..."`,
reviewed before committing), not another ad-hoc column patch.

## Deploying the backend

`backend/Dockerfile` builds a production image — CPU-only torch (no CUDA wheels, much smaller),
Pillow's `libgl1`/`libglib2.0-0` system deps included, no `.env` baked in (config comes from
environment variables at deploy time, matching `.env.example`'s keys). Build from the repo root
so `backend/models/` (the trained L1 checkpoint, if present) is in the build context:

```bash
docker build -f backend/Dockerfile -t truthpixel-backend .
docker run -p 8000:8000 --env-file backend/.env truthpixel-backend
```

**On Azure** (App Service / Container Apps, targeting Azure-for-Students credits — hosting
only, not training compute; see [docs/ML_PLAN.md](docs/ML_PLAN.md) §6 for why training itself
stays on free Colab/Kaggle): push the image to Azure Container Registry, then point an App
Service (Linux, container) or Container Apps revision at it. Set the same keys from
`.env.example` as Application Settings / environment variables — at minimum `DATABASE_URL`
(Azure Database for PostgreSQL, or leave as SQLite for a single-instance low-volume deploy),
`STORAGE_BACKEND=s3` with an S3-compatible endpoint or Azure Blob via a custom storage backend
(not yet implemented — `local`/`s3` are the two working options today), and `L1_MODEL_PATH`
pointing at the checkpoint baked into the image (`./models/l1_clip_head.pt`). First request
after a cold start pulls the CLIP encoder weights (~1.3GB) if not already cached in the image
layer — consider a startup health-check warm-up hit before routing real traffic.

## Layer 1 training scaffold

The `ml/layer1_aigen/` package now includes:
- GenImage-style dataset discovery and stable train/val/test assignment
- Screenshot/re-save augmentation helpers aligned with `docs/ML_PLAN.md`
- A frozen OpenCLIP encoder + trainable probe-head scaffold
- Train/eval CLI entry points and lightweight ML helper tests

To work on `L1` locally (with a GPU):

```bash
cd ml
pip install -r requirements.txt
python -m layer1_aigen.train --data-root path/to/dataset
```

No local GPU? See [docs/COLAB_TRAINING.md](docs/COLAB_TRAINING.md) — same `ml/layer1_aigen/`
code, run on Colab's free T4, with all datasets and checkpoints living in Google Drive (no
local downloads at all).

## Status

Real (not stub) today: **L3** recapture via Sightengine API, **L4** metadata via EXIF + a real
`c2patool` subprocess check, **L5 v0** context cross-check (perceptual-hash + color-histogram
similarity against seller listing photos and recent claims), persistence/audit/artifact
storage, async queueing, tenant/admin auth hooks, and the reviewer dashboard scaffold.

L1 is a three-mode runtime: local CLIP-head checkpoint first, then an HF Inference API ensemble
(`HF_API_TOKEN` + `L1_HF_MODELS`), then the neutral stub if neither is configured. That means
the missing piece for a non-stub L1 is configuration or a trained checkpoint, not missing repo
code.

Partially real: **L2** has TruFor subprocess integration plus heatmap artifact persistence, but
falls back to the neutral stub until an external TruFor checkout + weights are configured.
Vertex agents run in template/stub mode until `GOOGLE_CLOUD_PROJECT` is set. The public webapp
and dashboard code both exist; this pass verifies their production builds, not a fresh
browser-driven end-to-end session. Full checklist in [docs/ROADMAP.md](docs/ROADMAP.md).

## License

TBD.
