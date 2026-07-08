# Roadmap — Phase 0 → 2

> Concrete, checkable milestones. Local-first development; cloud only when it earns its cost.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md)

## Phase 0 — Working end-to-end demo (target: ~2–4 weeks of evenings)

**Goal:** upload a claim photo → fused risk score + heatmap + readable report, running locally.

Scaffold (done / in progress):
- [x] Repo structure, README, docker-compose (Postgres/Redis/Qdrant/MinIO — optional)
- [x] Docs suite: ARCHITECTURE, COMPETITORS, ML_PLAN, AGENTS, ROADMAP
- [x] FastAPI backend skeleton: `POST /v1/claims`, `GET /health`
- [x] Pydantic signal contracts (`SignalResult`, `AgentFinding`, `FusionResult`, `ClaimReport`)
- [x] LangGraph orchestrator: parallel analyzers → cost-gated agent pass → fusion → report
- [x] Analyzer stubs L1–L5 with error isolation (one layer failing never kills a claim)
- [x] L4 metadata: real EXIF extraction (Pillow), neutral-absence weighting
- [x] Weighted fusion + screenshot-evasion combo rule
- [x] Agent stubs with Vertex/Gemini wiring + no-credentials fallback
- [x] Smoke tests (graph end-to-end, error isolation, combo rule)

Remaining:
- [x] Install deps, run test suite, fix anything red
- [x] Git init, first commit, push to github.com/thanoban/TruthPixel (user-authored commits, no AI co-author)
- [ ] L1 real: train CLIP-head on GenImage subset with screenshot augmentation (`ml/layer1_aigen/`)
- [ ] L2 real: TruFor pretrained inference + heatmap PNG output
- [x] L3 real: Sightengine recapture API call (keys already templated in `.env.example`)
- [x] L4: add c2patool subprocess check
- [ ] Vertex agents live: set `GOOGLE_CLOUD_PROJECT`, verify semantic inspector on a garbled-text AI image
- [x] Public webapp scaffold (`webapp/`): upload → fused report, thin client over `/v1/claims`
- [ ] Backend CORS wired for webapp/dashboard origins (`app/config.py::cors_allow_origins`) — done in code, unverified
- [ ] `npm install` + run webapp against local backend, confirm end-to-end in a browser
- [ ] Minimal reviewer report page (dashboard) showing score, signal table, heatmap overlay
- [ ] Demo script: 5 curated images (real damage, SDXL fake, inpainted, screenshot-of-AI, reused photo)

**Exit criterion:** the screenshot-of-AI-image demo case is flagged with a correct explanation.

## Phase 1 — Real product (target: +2–3 months)

**Goal:** a platform could pilot it.

- [ ] Async job queue (Celery + Redis), claim status polling / webhook callback
- [x] Persistence foundation: database-backed claims, signals, reviewer decisions, and audit log
- [ ] Object storage: MinIO/S3 (images + heatmaps)
- [ ] L5 v1: DINOv2 embeddings + Qdrant; listing↔claim similarity; reverse-image search (TinEye/SerpAPI)
- [ ] Public webapp: anonymous rate limiting (IP/fingerprint), image-retention policy stated on page, optional free API key for higher usage (see USE_CASES.md §3)
- [ ] Learned fusion: LightGBM/LogReg + calibration + SHAP (labels from synthetic fraud pairs — `ml/datagen/`)
- [ ] Reviewer dashboard (Next.js): claim queue, heatmap overlay, per-signal breakdown, approve/reject + reason
- [ ] Feedback capture → labeled-claims table (fuel for fusion retraining)
- [ ] Serverless GPU inference (Modal or RunPod) for L1/L2; scale-to-zero
- [ ] Held-out-generator benchmark + robustness matrix, published in docs
- [ ] AuthN/AuthZ: per-tenant API keys, rate limits
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
| Agents | Gated Gemini pass on Vertex credits | Semantics survive screenshots; spend scales with risk |
| Git authorship | User-authored commits, no AI co-author trailer | User preference |
| Product surfaces | One detection core, three doors in (API / dashboard / public webapp) | Same signal quality everywhere; webapp is funnel + non-e-commerce use cases, never a fork of the logic |
