# Roadmap — Phase 0 → 2

> Concrete, checkable milestones. Local-first development; cloud only when it earns its cost.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md)

## Reality snapshot — 2026-07-08

Before reading the phase checklist, anchor on the repo as it really exists today:

| Area | Already built on `origin/main` | Branch-only today | Still missing before L1 is truly real |
|---|---|---|---|
| Core backend | Sync + async claims, persistence, audit log, artifact storage, webhook callbacks, tenant/admin auth hooks, public-submission rate limiting | No major unmerged backend capability confirmed; most historical feature branches already landed on `main` | Hosted auth rollout, worker/GPU deployment, observability |
| Signal layers | L1 checkpoint loading, L2 TruFor adapter + heatmap artifact persistence, L3 Sightengine, L4 EXIF + `c2patool`, L5 v0 hash/histogram checks | No meaningful branch-only signal-layer implementation confirmed | Train and evaluate a real L1 checkpoint, configure TruFor artifacts, then verify live inference |
| Reviewer surfaces | `dashboard/` exists with queue, claim detail, decision capture, audit trail, and heatmap overlay | — | Auth polish, live API verification, reviewer workflow hardening |
| ML tooling | `ml/layer1_aigen/` training scaffold and `ml/fusion/` learned-fusion tooling both exist | — | Real data, exported artifacts, calibrated model versions in runtime |

The main distinction is not branch-only code anymore, but configured-vs-unconfigured runtime:
the repo already contains the L1/L2 integration paths, yet both still degrade to neutral stubs
until you provide a trained L1 checkpoint and an external TruFor checkout/weights.

## Phase 0 — Working end-to-end demo (target: ~2–4 weeks of evenings)

**Goal:** upload a claim photo → fused risk score + heatmap + readable report, running locally.

Scaffold (done / in progress):
- [x] Repo structure, README, docker-compose (Postgres/Redis/Qdrant/MinIO — optional)
- [x] Docs suite: ARCHITECTURE, COMPETITORS, ML_PLAN, AGENTS, ROADMAP
- [x] FastAPI backend skeleton: `POST /v1/claims`, `GET /health`
- [x] Pydantic signal contracts (`SignalResult`, `AgentFinding`, `FusionResult`, `ClaimReport`)
- [x] LangGraph orchestrator: parallel analyzers → cost-gated agent pass → fusion → report
- [x] Analyzer scaffolding L1–L5, one `Analyzer` ABC, error isolation (one layer failing never kills a claim) — **all five layers now have real wiring behind an unconfigured-fallback stub, see below**
- [x] L4 metadata: real EXIF extraction (Pillow) + real `c2patool` subprocess check, neutral-absence weighting
- [x] Weighted fusion + screenshot-evasion combo rule
- [x] Agent stubs with Vertex/Gemini wiring + no-credentials fallback
- [x] Smoke tests (graph end-to-end, error isolation, combo rule)

Remaining:
- [x] Install deps, run test suite, fix anything red
- [x] Git init, first commit, push to github.com/thanoban/TruthPixel (user-authored commits, no AI co-author)
- [x] L1 HF-ensemble path (zero-training, shipped): `backend/app/hf_inference.py` +
      `l1_aigen.py` call an ensemble of pretrained HF-Inference-API detectors and average
      them. Config `HF_API_TOKEN`/`L1_HF_MODELS`; Apache-2.0 defaults (Ateeqq + Nahrawy).
      This is the day-one real L1 without any local model. Tests: `test_hf_ensemble.py`.
      **Operational note:** needs an HF token set; without it L1 falls back to stub.
- [x] L1 wiring (local checkpoint): `l1_aigen.py` loads a trained CLIP-head via
      `L1_MODEL_PATH`/`L1_MODEL_DEVICE`, taking precedence over the HF ensemble when set
- [ ] L1 own-model upgrade: train the screenshot-augmented CLIP-head on a GenImage subset
      (`ml/layer1_aigen/`) — see [docs/COLAB_TRAINING.md](COLAB_TRAINING.md) (no local GPU:
      Colab + Drive). This is the domain-tuned *upgrade* to the HF ensemble, not a blocker for
      a working L1. No checkpoint trained/deployed yet.
- [x] L2 real: TruFor subprocess inference (`backend/app/trufor.py`) + heatmap PNG artifact,
      gated on `l2_trufor_configured` (repo dir + model file set), stub fallback otherwise
- [x] L3 real: Sightengine recapture API call (keys already templated in `.env.example`)
- [x] L4: add c2patool subprocess check
- [x] L5 real (v0): `context_checks.py` perceptual-hash + color-histogram similarity —
      listing-photo match/mismatch scoring, plus intra-system reused-photo detection by
      scanning recent claim artifacts. **Not yet done:** DINOv2/Qdrant embeddings (better
      matching) or TinEye/SerpAPI (catches photos stolen from *outside* our own claims DB) —
      tracked as L5 v1 in Phase 1 below.
- [x] Async claim queue: `POST /v1/claims/async`, `GET /v1/claims/{id}/status`, webhook
      dispatch on completion (`backend/app/jobs.py`, `celery_app.py`) — **operational caveat:**
      needs a running Celery worker + Redis, or `CELERY_TASK_ALWAYS_EAGER=true` for local dev;
      without either, queued claims stay `pending` forever (not yet documented anywhere but
      here and the README quickstart)
- [x] Claim persistence + review: SQLite-by-default storage, `GET /v1/claims`,
      `POST /v1/claims/{id}/decision`, `GET /v1/claims/{id}/audit`, artifact upload/download
      (original upload + heatmap) — `backend/app/storage/`, `artifacts.py`
- [ ] Vertex agents live: set `GOOGLE_CLOUD_PROJECT`, verify semantic inspector on a garbled-text AI image
- [x] Public webapp scaffold (`webapp/`): upload → fused report, thin client over `/v1/claims`
- [x] Backend CORS wired for webapp/dashboard origins (`app/config.py::cors_allow_origins`, `main.py` `CORSMiddleware`) — implemented
- [ ] `npm install` + run webapp against local backend, confirm end-to-end in a browser (not done in this environment)
- [x] Fix webapp/report data-model drift: `webapp/app/types.ts` now has a `StoredClaim`
      interface (superset of `ClaimReport` — `status`, `decision`, `artifacts`, timestamps)
      matching what `POST /v1/claims` actually returns; `page.tsx` uses it. **Still not
      up to date:** `types.ts` doesn't mirror the tenant/API-key/queue-status schemas
      (`TenantResponse`, `ApiKeyCreateRequest`, `IssuedApiKeyResponse`, `ClaimQueueStatus`,
      `ClaimListItem`, `AuditEvent`) — low priority since the webapp only calls
      `POST /v1/claims` today, but note this before the webapp grows beyond that one endpoint.
- [x] Auth & rate limits: per-tenant API keys (`backend/app/auth.py`), admin token-gated
      tenant/key management, per-tenant and public-IP rate limiting, `PUBLIC_SUBMISSION_ENABLED`
      gate for the anonymous webapp path — all off by default (`API_AUTH_ENABLED=false`)
- [x] `.env.example` / webapp docs now mention the auth toggles above (`.env.example`'s
      "Auth & rate limits" section, `webapp/README.md`'s auth note); re-check for settings drift
      the next time `config.py` changes
- [x] Minimal reviewer dashboard scaffold: queue, score table, claim detail, audit trail,
      decision form, and heatmap overlay — `dashboard/`
- [ ] Reviewer dashboard hardening: verify against a live API, finish auth/tenant flow, and
      close UX gaps for production reviewers
- [ ] Demo script: 5 curated images (real damage, SDXL fake, inpainted, screenshot-of-AI, reused photo)

**Exit criterion:** the screenshot-of-AI-image demo case is flagged with a correct explanation.

## Phase 1 — Real product (target: +2–3 months)

**Goal:** a platform could pilot it. (Async job queue landed ahead of schedule during
Phase 0 — see the Phase 0 checklist above; its operational caveat about needing a running
Celery worker still applies.)

- [x] Persistence foundation: database-backed claims, signals, reviewer decisions, and audit log
- [x] Object storage: local/S3-compatible claim images + heatmaps
- [x] Learned-fusion tooling scaffold: `ml/fusion/features.py` + `ml/fusion/train_meta.py`
- [ ] L5 v1: replace v0 hash/histogram with DINOv2/OpenCLIP embeddings + Qdrant ANN search; add external reverse-image search (TinEye/SerpAPI) for photos stolen from outside our own claims DB
- [x] Public webapp: anonymous submission path (IP rate-limited via `PUBLIC_SUBMISSION_ENABLED`,
      see Phase 0 above). **Still not done:** image-retention policy stated on the page itself,
      optional free API-key signup for higher usage (see USE_CASES.md §3)
- [ ] Learned fusion in production: LightGBM/LogReg + calibration + SHAP trained on real labels,
      exported for backend runtime use (tooling exists, model artifacts do not)
- [ ] Reviewer dashboard productionization: auth, tenant verification, deploy/runtime proof, and
      reviewer ergonomics on top of the existing scaffold
- [ ] Feedback capture → labeled-claims table (fuel for fusion retraining)
- [ ] Serverless GPU inference (Modal or RunPod) for L1/L2; scale-to-zero
- [ ] Held-out-generator benchmark + robustness matrix, published in docs
- [x] AuthN/AuthZ: per-tenant API keys, admin-token-gated key issuance, per-tenant + public-IP rate limits — landed ahead of schedule during Phase 0, see above
- [ ] Observability: structured logs, per-claim trace, cost counters (Vertex/API spend per claim)

**Exit criterion:** honest held-out-generator number published; one pilot-able deployment.

## Phase 2 — Enterprise & moat (target: +6 months)

- [ ] Own recapture CNN (drop Sightengine); own recapture dataset (device-matrix capture scripts)
- [ ] Multi-tenancy hardening: tenant-scoped data, per-tenant thresholds & model versions
- [ ] Model registry + versioned inference (every result records model+prompt versions)
- [ ] Drift monitoring: score-distribution alerts per generator/tenant; retrain pipeline from reviewer labels
- [ ] Cross-claim pattern agent (serial-fraudster detection over L5 reverse-search clusters)
- [ ] Triage-router agent replacing static gate thresholds
- [ ] LangGraph checkpointing (Postgres) + human-in-the-loop re-pass
- [ ] PRNU sensor-fingerprint analysis (advanced L4)
- [ ] SDK + webhook integration package for platforms; SLA docs; audit exports
- [ ] Compliance posture: data retention, PII handling, regional storage

**Exit criterion:** a tenant can onboard without us touching servers; detectors retrain from
their own reviewers' labels.

## Standing decisions (so we don't relitigate)

| Decision | Choice | Why |
|---|---|---|
| Positioning | Return-fraud decision support, not "AI detector" | Durable vs generator churn; clear buyer |
| Verdicts | Never binary; human decides | Accuracy honesty + legal shield |
| Metadata weight | Absence = neutral | WhatsApp re-saves & screenshots wipe it innocently |
| Screenshot evasion | Recapture detection + screenshot-augmented training + semantic agent | Turn evasion into signal |
| Training scope | 3 models only (L1 head, fusion meta, recapture CNN) | Feasible solo; everything else pretrained |
| Headline metric | Held-out-generator AUROC + robustness matrix | The only honest number |
| Hosting | Local dev → serverless scale-to-zero | Async bursty workload; no idle GPU |
| Agents | Gated Gemini pass, cost-gated regardless of credit | Semantics survive screenshots; spend scales with risk; $1,000 GCP credit is GenAI-App-Builder-scoped, not a blanket Vertex allowance — verify before assuming it applies (AGENTS.md) |
| Training compute | Free Colab T4, not Vertex credits | $1,000 credit does not cover Colab Enterprise GPU / training compute (verified via Billing → Credits) — training stays $0 on Colab's free tier instead |
| Git authorship | User-authored commits, no AI co-author trailer | User preference |
| Product surfaces | One detection core, three doors in (API / dashboard / public webapp) | Same signal quality everywhere; webapp is funnel + non-e-commerce use cases, never a fork of the logic |
