# Roadmap — Phase 0 → 2

> Concrete, checkable milestones. Local-first development; cloud only when it earns its cost.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md) ·
> [CORRECTIONS.md](CORRECTIONS.md) · [EXECUTION_PLAN.md](EXECUTION_PLAN.md)

## Reality snapshot — 2026-07-11

Before reading the phase checklist, anchor on the repo as it really exists today:

| Area | Landed on this reconciliation branch | Still not landed on main |
|---|---|---|
| Core backend | Sync + async claims, persistence, audit log, artifact storage, tenant/admin auth hooks, public-submission rate limiting, reviewer-decision capture | Observability/tracing, batch intake, hosted deployment/runtime proof |
| Reviewer surfaces | `dashboard/` queue, claim detail, status polling, decision capture, audit trail, artifact preview, reviewer-context/auth-proxy hardening | Tenant-switcher and full live verification against `API_AUTH_ENABLED=true` |
| Public webapp | Self-serve upload flow, backend-shaped report rendering, artifact preview, retention/privacy/risk copy, anonymous-vs-API-key placeholder messaging | Real signup/upgrade flow, production deployment verification |
| Label feedback loop | Reviewer decisions can now be exported via tenant/admin label export + CSV/summary endpoints for retraining workflows | Training job that consumes those labels into a deployed fusion artifact |
| Test reliability | Root `conftest.py` now isolates tests from accidental `backend/.env` leakage and clears runtime caches | Additional broader runtime-hardening work still branch-only |
| Signal layers | L1 local-checkpoint path + HF ensemble path, L2 TruFor adapter + heatmap artifact persistence, L3 Sightengine, L4 EXIF + `c2patool`, L5 v0 hash/histogram checks | Branch-only experiments such as classical L2 fallback, broader L5 upgrades, and observability remain unmerged here |

This branch intentionally lands only the verified, narrow slices that are ready to promote now.
Several larger `codex/*` branches exist, but they bundle broader runtime or roadmap changes and
are not treated as finished here unless they are actually merged.

## Phase 0 — Working end-to-end demo

**Goal:** upload a claim photo → fused risk score + heatmap + readable report, running locally.

Shipped:
- [x] Repo structure, docs suite, backend skeleton, signal contracts, orchestration scaffold
- [x] Analyzer scaffolding L1–L5 with per-layer error isolation
- [x] L1 local-checkpoint path plus HF Inference API ensemble fallback
- [x] L2 TruFor subprocess adapter with persisted heatmap artifact when configured
- [x] L3 Sightengine recapture path
- [x] L4 EXIF + `c2patool` provenance checks
- [x] L5 v0 listing/context checks using perceptual-hash + histogram matching
- [x] Weighted fusion plus screenshot-evasion combo rule
- [x] Sync + async claim submission endpoints
- [x] Claim persistence, artifact storage, audit trail, reviewer decisions
- [x] Public webapp over `POST /v1/claims`
- [x] Reviewer dashboard over claim list/detail/decision/audit/artifact endpoints
- [x] Tenant/admin auth hooks and public submission gate
- [x] Test-session env isolation from local `backend/.env`

Still missing:
- [ ] Train and deploy the own-model L1 checkpoint
- [ ] Verify Vertex agents live with real credentials
- [ ] Verify the full browser-driven public webapp flow in this branch again after reconciliation
- [ ] Verify the dashboard against a live `API_AUTH_ENABLED=true` backend with a real tenant key
- [ ] Create the curated demo harness and reproducible demo dataset

**Exit criterion:** the screenshot-of-AI-image demo case is flagged with a correct explanation.

## Phase 1 — Real product

**Goal:** a platform could pilot it honestly.

- [x] Persistence foundation: database-backed claims, signals, reviewer decisions, audit log
- [x] Object storage: local/S3-compatible original-upload + heatmap storage
- [x] Public webapp self-serve surface with clear disclaimers and backend-compatible rendering
- [x] Reviewer dashboard hardening for queue/detail/review workflows on tenant-protected routes
- [x] Feedback capture export: labeled claims JSON/CSV/summary endpoints for tenant/admin use
- [ ] Learned fusion in production: train/export/deploy a real artifact from reviewer labels
- [ ] L5 v1: embedding-based retrieval and external reverse-image search
- [ ] Reviewer dashboard productionization: tenant switching, stronger auth UX, deployment proof
- [ ] Hosted worker/GPU deployment and async queue runtime proof
- [ ] Observability: structured logs, per-claim trace, cost counters

**Exit criterion:** honest held-out-generator number published; one pilot-able deployment.

## Phase 2 — Enterprise & moat

- [ ] Own recapture CNN and recapture dataset
- [ ] Multi-tenancy hardening: thresholds, model versions, stronger tenant controls
- [ ] Model registry + versioned inference records
- [ ] Drift monitoring and retrain loop from reviewer labels
- [ ] Cross-claim fraud-pattern analysis
- [ ] SDK/webhook package and audit exports
- [ ] Compliance posture: retention, PII handling, regional storage

**Exit criterion:** a tenant can onboard without us touching servers; detectors retrain from
their own reviewers' labels.

## Standing decisions

| Decision | Choice | Why |
|---|---|---|
| Positioning | Return-fraud decision support, not "AI detector" | Durable vs generator churn; clear buyer |
| Verdicts | Never binary; human decides | Accuracy honesty + legal shield |
| Metadata weight | Absence = neutral | Innocent resaves/screenshots often wipe metadata |
| Screenshot evasion | Recapture detection + screenshot-robust signals + semantic review | Turn evasion into signal |
| Training scope | Small set of owned models only | Feasible solo; leverage pretrained systems elsewhere |
| Product surfaces | One core engine, three doors in (API / dashboard / webapp) | Keep signal quality consistent across use cases |
