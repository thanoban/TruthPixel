# Execution Plan — Forensic-Grade Accuracy, Full Automation, Pilot-Ready Startup

> The sequenced plan for the next development block, written 2026-07-10 against a verified
> system state (see [CORRECTIONS.md](CORRECTIONS.md) for the audit trail behind every claim
> below). Three tracks: **A — accuracy**, **B — automation**, **C — startup readiness**.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [ROADMAP.md](ROADMAP.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md)

## 0. Where we stand (verified, not aspirational)

> **Updated 2026-07-10 (4):** re-verified by running the repo, not reading docs. Two
> corrections vs. the version of this table written earlier the same day — see
> [CORRECTIONS.md](CORRECTIONS.md) 2026-07-10 (4) for the full findings.

🔴 **Blocker, fix before anything below:** the backend test suite is currently broken —
8/57 failing, 136s instead of ~20s — because tests aren't isolated from `backend/.env`'s
real Vertex/L1 credentials (added when those went live). `backend-ci.yml` will fail on
push as-is. This isn't part of Track A/B/C below; it's a prerequisite for trusting any of
their test results.

| Layer / capability | State |
|---|---|
| L1 AI-gen detection | **Real trained checkpoint live** (0.9688 held-out AUROC, screenshot-robust) + HF-ensemble path + stub fallback |
| L2 edit forensics | **Effectively stub.** `backend/app/forensics_classic.py` (ELA/noise/JPEG-ghost) is drafted but **confirmed not wired into `l2_forensics.py`** (correction: earlier today's version of this doc said A1 was "in progress" — the module exists but nothing calls it yet). TruFor path needs compute we don't have |
| L3 recapture | Real via Sightengine API (needs keys; stub without) |
| L4 metadata/provenance | Real (EXIF + c2patool) |
| L5 context cross-check | Real (hash+histogram + optional CLIP-embedding blend + reuse detection) |
| Fusion | Weighted + calibrated-learned-model runtime (no trained fusion model yet — no labels, `ml/datagen/` doesn't exist) |
| Agents (Vertex/Gemini) | **Live and verified** (semantic inspector + damage plausibility + report writer), cost-gated |
| Platform | Auth/tenancy/rate limits, async queue, persistence/audit/artifacts, Alembic migrations, structured tracing, Dockerfile + CI workflow (not deployed, CI untested against a real push), demo harness |

**The single biggest accuracy gap is L2, and it hasn't been started yet** (only drafted,
unwired). Everything else has a real signal today.

## 1. Honest framing: what "government-grade forensics" actually means

Government/lab forensic image analysis is not secret models. It is: (1) the *published*
classical techniques — error-level analysis, noise-inconsistency mapping, double-JPEG/ghost
detection, PRNU — (2) provenance verification, (3) multiple independent signals fused, and
(4) a human expert making the final call with an audit trail. **That is architecturally
exactly this system.** Parity is therefore a matter of: filling L2 with real forensic
signals, keeping every layer independent, calibrating fusion on labeled data, and never
overstating a single-model number. We will say "multi-signal forensic methodology with a
published held-out benchmark," never "government-grade" as a marketing claim we can't cite.

## 2. Track A — Forensic-grade accuracy (no compute engine required)

Ordered by impact-per-effort; every step is CPU-only or uses already-hosted inference.
**Revised 2026-07-10** (see §2a for why) — sequencing and A2/A3's position changed from the
original version of this doc; the items themselves didn't.

- **A1. L2 classical forensics** *(module drafted, NOT wired in yet — `backend/app/forensics_classic.py`
  exists but `l2_forensics.py` doesn't reference it; confirmed via grep 2026-07-10 (4). This
  is the next concrete step, not "in progress.")*
  ELA + block noise-inconsistency + JPEG-ghost, pure numpy/PIL, sub-second on CPU. Wired
  into `l2_forensics.py` below TruFor in precedence: TruFor (when configured) → classical
  (always available) → never a stub again. Produces a real localization heatmap through the
  existing TruFor renderer + artifact persistence. Calibrate score constants against
  synthetic splices; conservative confidence (classical methods are honest-but-noisy).
  **Target:** a held-out discrimination number on CASIA v2 (see A1b), not just "scores
  meaningfully higher on our own splices."
- **A1b. External eval — CASIA v2** *(new)* — evaluate A1's classical forensics against a
  held-out split of CASIA v2 (already a reuse candidate per COMPETITORS.md §3; standard
  academic splicing benchmark with ground-truth masks). Self-generated splices (A4) are
  useful for *calibrating* thresholds; they're the wrong data to *claim* accuracy on, since
  tuning and claiming on the same self-authored data risks measuring our own compositing
  artifacts rather than real-world splice detection. A number that holds up on data we
  didn't construct is the credible one.
- **A2. L1 max-accuracy blend mode** — run the trained checkpoint *and* the HF ensemble
  together and combine (independent architectures → uncorrelated errors). Opt-in flag;
  checkpoint-only remains the default until the blend is benchmarked better. **Moved to run
  after A6** — any accuracy change should be justified by a measured delta against a real
  benchmark, not shipped ahead of one.
- **A3. Curated HF-ensemble expansion** — add members only if live-verified + license-safe
  (Apache-2.0/CC-BY; never CC-BY-NC in the commercial set — see COMPETITORS.md §2). Same
  "after A6, measured not assumed" rule as A2.
- **A4. Synthetic labeled eval/training set** (`ml/datagen/fraud_pairs.py`) — locally-built
  spliced/inpainted pairs from real photos (PIL compositing at mismatched compression
  levels), honestly labeled as synthetic. Role clarified: this is **calibration/training
  data**, not the accuracy claim itself (that's A1b/A6's job) — unblocks per-layer
  ablation and A5.
- **A5. Learned fusion (T2)** — LogReg + Platt calibration on A4's labels + reviewer
  decisions as they accrue. Minutes on CPU; tooling already exists (`ml/fusion/`). Exported
  via `FUSION_MODEL_PATH`. This is where "the ensemble is the accuracy story" becomes a
  measured number instead of hand weights. **Target: precision@review-budget** (top-k
  flagged claims) as the headline metric, not AUROC alone — reviewers only have capacity
  to check a fixed number of claims, so that's the number a buyer actually cares about;
  already named in ML_PLAN.md's fusion-eval section but not previously elevated as the
  target here.
- **A5b. Fusion-level robustness matrix** *(new)* — the existing robustness matrix
  (pristine / jpeg_q75 / screenshot_sim / social_roundtrip, `ml/layer1_aigen/eval.py`) is
  currently applied only to L1's own eval. Re-run it through L2 and the *fused* score on
  the A1b/A4 eval sets. This is the concrete test of ARCHITECTURE.md §2's "screenshot
  evasion is itself a signal" claim, which otherwise stays an architectural argument no
  number backs up.
- **A6. Published benchmark report** (`docs/BENCHMARK.md`) — held-out-generator AUROC
  (L1: 0.9688, already have this), A1b's CASIA v2 number, A5's precision@review-budget,
  A5b's fusion-level robustness matrix, and **Expected Calibration Error (ECE) +
  reliability diagram** *(new)* — AUROC/precision measure ranking quality, not whether a
  stated "80%" is trustworthy on its own terms; ARCHITECTURE.md §4 already promises
  calibrated confidence, nothing has verified it yet, and ECE is cheap once A5's held-out
  predictions exist. This report is the credibility artifact for pilots, and — once it
  exists — the actual enforcement mechanism for ML_PLAN.md §4's regression gate ("any new
  model version must beat current on held-out AUROC"), which has no automated harness yet.
- **A7. Deferred until compute exists:** TruFor on serverless GPU (env is validated, see
  TRUFOR_SETUP.md), T3 recapture CNN, PRNU.

### 2a. Why this revision (training scope unchanged)

This revision adds rigor, not scope: no new deep-learning training. The standing decision
in ML_PLAN.md/ROADMAP.md ("train exactly 3 things: L1 head, fusion meta-classifier,
recapture CNN — everything else pretrained") still holds. A1/A1b are algorithmic
(fixed formulas) and calibration, not training. A5 is the one training step here — CPU,
minutes, logistic regression over 5 numbers per claim. T3 (real deep-learning, GPU) stays
in A7, deferred. If L1's own number needs to go higher later, the lever is better/larger
training data (CIFAKE is 32×32 — a known limitation already flagged in ROADMAP.md), not a
new training step, and that's not part of this revision either.

## 3. Track B — Multi-agent automation on Vertex (for high-volume enterprise users)

Credits are live and verified; the cost-gating discipline stays regardless of credit.

- **B1. Triage-router agent** — replaces the static `AGENT_TRIGGER_LOW/HIGH` band with a
  Gemini routing decision over the full signal vector (still hard-capped by config so a
  routing bug can't cause unbounded spend).
- **B2. Batch submission** (`POST /v1/claims/batch`) — bulk claim intake for sellers/
  platforms, fanning into the existing queue; per-tenant rate limits already apply.
- **B3. Automated dispositions** — agent-written, seller-facing outcome summaries delivered
  through the existing webhook on completion; reviewer decision still gates anything
  adverse (human-in-the-loop is a standing decision, not a phase).
- **B4. Cross-claim pattern agent** — scheduled pass over L5 reuse clusters → serial-
  fraudster reports per tenant.
- **B5. LangGraph checkpointing (Postgres) + reviewer-triggered agent re-pass** — a reviewer
  can add context and re-run the agent stage on a stored claim.

## 4. Track C — Operate like a startup (pilot-ready)

- **C1. Deploy for real** — build + smoke-test the existing Dockerfile (needs a Docker
  daemon: user machine or CI), then Azure Container Apps/App Service + Redis + worker.
- **C2. Auth on in the deployed environment** — tenant onboarding runbook using the
  existing admin API; dashboard verified against a live keyed backend.
- **C3. Per-claim cost counters** — aggregate the existing `record_external_usage` events
  into per-claim/per-tenant spend (Vertex + Sightengine + HF), exposed via tenant-safe and
  admin reporting endpoints. Unit economics visibility = pricing input.
- **C4. Policy surface** — data-retention statement, PII handling, SLA draft.
- **C5. Pilot kit** — benchmark doc (A6) + demo script + dashboard walkthrough + pricing
  sketch grounded in C3's real cost data.

## 5. Execution order

```
A1 (L2 classical — in progress) → A1b (CASIA v2 eval)
→ A4 (datagen) → A5 (learned fusion) → A5b (fusion-level robustness matrix)
→ A6 (benchmark report — AUROC, precision@review-budget, ECE, robustness — the harness)
→ A2 (L1 blend) / A3 (ensemble expansion) — measured against A6, not shipped on faith
→ B2 (batch API) → B1 (triage router) → B3 (auto-dispositions)
→ C3 (cost counters) → C1/C2 (deploy + auth on)
→ C5 (pilot kit, built on A6) → B4/B5, C4 as they slot in
```

Rationale: accuracy first (it's the product), then the automation that makes high-volume
users self-serve, then the operational wrapper that makes it sellable. Each step is
independently verifiable and lands with tests + docs, per the standing discipline. A2/A3
moved to *after* A6 (2026-07-10 revision, see §2a): a real benchmark harness should exist
before further accuracy changes are judged, not after.

## 5a. C3 runtime contract (implemented 2026-07-11)

Environment/config behavior:
- `VERTEX_INPUT_COST_PER_1M_TOKENS` and `VERTEX_OUTPUT_COST_PER_1M_TOKENS` price Vertex
  agent usage when `record_vertex_usage()` sees token counts. If either value is `0` or
  unset, that side of the token cost contributes `0`.
- `HF_REQUEST_COST_USD` applies a flat per-request cost to successful HF inference API
  member calls. Default `0.0`.
- `SIGHTENGINE_REQUEST_COST_USD` applies a flat per-request cost to successful Sightengine
  recapture checks. Default `0.0`.
- Failed external calls still increment request/failure counters, but negative or missing
  prices are clamped to `0`.
- Provider / operation / model labels are sanitized and length-bounded before persistence,
  so reporting stays privacy-safe and cardinality-safe even if a caller passes noisy values.

Persistence and endpoints:
- Claim-level summaries persist automatically when the backend logs `claim_usage_summary`
  for a bound `claim_id` (`log_usage_summary()` now writes storage before emitting the log).
- `GET /v1/claims/{claim_id}/usage` returns one tenant-scoped `ClaimUsageSummary`. Claims
  with no usage row yet return a zeroed summary instead of an error.
- `GET /v1/usage/summary` returns the authenticated tenant's aggregate `TenantUsageSummary`.
- `GET /v1/admin/claims/{claim_id}/usage` returns any claim's usage summary for admins.
- `GET /v1/admin/tenants/{tenant_id}/usage/summary` returns a single tenant aggregate.
- `GET /v1/admin/usage/summary` lists tenant aggregates for tenants that currently have
  claims.

Example claim response:

```json
{
  "claim_id": "0f2e6b2d-7c74-4e09-8f97-97b9f7f57b23",
  "tenant_id": "acme-marketplace",
  "outcome": "completed",
  "total_external_requests": 3,
  "failed_external_requests": 1,
  "total_input_tokens": 120,
  "total_output_tokens": 45,
  "estimated_cost_usd": 0.0037,
  "providers": {
    "vertex_ai": {
      "requests": 2,
      "failed_requests": 0,
      "input_tokens": 120,
      "output_tokens": 45,
      "estimated_cost_usd": 0.0012,
      "operations": {
        "report_writer": 1,
        "semantic_inspector": 1
      },
      "models": [
        "gemini-2.5-flash"
      ]
    },
    "sightengine": {
      "requests": 1,
      "failed_requests": 1,
      "input_tokens": 0,
      "output_tokens": 0,
      "estimated_cost_usd": 0.0025,
      "operations": {
        "l3_recapture_check": 1
      },
      "models": [
        "screen"
      ]
    }
  }
}
```

Example tenant summary response:

```json
{
  "tenant_id": "acme-marketplace",
  "total_claims": 12,
  "claims_with_usage": 9,
  "claims_with_failed_external_requests": 2,
  "total_external_requests": 27,
  "failed_external_requests": 3,
  "total_input_tokens": 15420,
  "total_output_tokens": 2940,
  "estimated_cost_usd": 0.1843,
  "providers": {
    "vertex_ai": {
      "requests": 18,
      "failed_requests": 0,
      "input_tokens": 15420,
      "output_tokens": 2940,
      "estimated_cost_usd": 0.1218,
      "operations": {
        "damage_plausibility": 6,
        "report_writer": 6,
        "semantic_inspector": 6
      },
      "models": [
        "gemini-2.5-flash"
      ],
      "claim_count": 6
    }
  }
}
```

## 6. What we will NOT do (so the plan stays honest)

- No GPU/compute-engine dependencies in any near-term step (A7 explicitly waits).
- No fabricated test/eval images presented as real generator output.
- No accuracy claims beyond the published held-out benchmark.
- No agent autonomy over adverse decisions — reviewer decides, always.
- No unverifiable third-party integrations (e.g., guessed API contracts) — anything we
  can't test live doesn't ship.
