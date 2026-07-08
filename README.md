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
| [docs/AGENTS.md](docs/AGENTS.md) | LangGraph multi-agent system (Gemini on Vertex AI), cost gating |
| [docs/USE_CASES.md](docs/USE_CASES.md) | Product surfaces (API / reviewer dashboard / public webapp) and use cases beyond return fraud |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase 0–2 checklists and standing decisions |

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
backend/     FastAPI service: API, orchestrator, analyzers (L1–L5), fusion
ml/          Model training & evaluation (Layer 1 CLIP-head pipeline lives here)
webapp/      Public self-serve webapp — anyone checks one image, no tenant/order context
dashboard/   Next.js reviewer UI (heatmap overlay, signal breakdown, human decision) — internal, tenant-scoped
docs/        Architecture & design docs
scripts/     Dev / data helpers
```

Three product surfaces, one detection core — see [docs/USE_CASES.md](docs/USE_CASES.md).

## Quickstart (local-first)

```bash
# 1. Backend API (stub analyzers run out of the box, no models needed)
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 2. Try it via API
curl -X POST http://localhost:8000/v1/claims \
  -F "image=@sample.jpg" -F "order_id=A123" -F "product_sku=SKU-9"

# 3. Or use the public webapp (thin client over the same API)
cd ../webapp
npm install
cp .env.local.example .env.local
npm run dev   # http://localhost:3000
```

Optional local infra (Postgres / Redis / Qdrant / MinIO) via `docker compose up -d`.
Not required for the stub API.

## Status

Phase 0 scaffold. Analyzers return structured **stub** signals so the whole pipeline runs
end-to-end today; real models plug in behind the same interface (see `backend/app/analyzers/`).
Layer 1 training scaffold lives in `ml/layer1_aigen/`.

## License

TBD.
