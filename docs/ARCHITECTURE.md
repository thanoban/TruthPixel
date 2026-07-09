# TruthPixel — Image Integrity Verification for E-commerce Returns

> Master design doc. Draft v0.3 — 2026-07-08.
>
> Companion docs: [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) ·
> [AGENTS.md](AGENTS.md) · [USE_CASES.md](USE_CASES.md) · [ROADMAP.md](ROADMAP.md)

## Repo status note

This document mixes target architecture with implementation reality. As of 2026-07-08:
- `origin/main` already includes the async queue, persistence/audit/artifacts, reviewer dashboard scaffold, tenant/admin auth primitives, public-submission rate limiting, and the `ml/fusion/` training helpers.
- L3/L4/L5 are genuinely implemented analyzers today.
- L2 has real TruFor adapter + heatmap artifact plumbing, but still falls back to a neutral stub until an external TruFor checkout and weights are configured.
- L1 has both local-checkpoint loading and an HF Inference API ensemble path on `main`; what is missing for the own-model path is a trained checkpoint, while the HF path just needs `HF_API_TOKEN`.

## 0. One-line positioning

Not "an AI-image detector." We are a **multi-signal image-integrity engine**, beachheaded on
e-commerce return/refund fraud: given a customer-submitted "damaged product" photo, we return
a calibrated fraud-risk score with an explainable, region-level report and a human-review
dashboard. The same engine serves other verification use cases through a public self-serve
webapp — see §11 and [USE_CASES.md](USE_CASES.md).

Why this framing wins:
- Generic AI-detectors decay fast on unseen generators. A single-model accuracy claim is a
  liability. **Fusion + domain context is a defensible moat; a lone classifier is not.**
- Nobody in the market fuses AI-gen detection + edit forensics + recapture detection +
  metadata + **product cross-check against the seller's own listing photos**. That last
  layer is the novelty and the thing incumbents structurally can't copy quickly.

---

## 1. Competitor analysis — reuse vs. compete

> Full landscape (15 commercial tools, 17 open-source models, 9 APIs, 20+ datasets) with
> per-item stance lives in [COMPETITORS.md](COMPETITORS.md). Summary of the strategic calls:

| Player | What they do | Our stance |
|---|---|---|
| Sightengine (AI-gen + **Recapture** API) | API detects AI images AND photos-of-screens / printed recaptures | **REUSE** as a signal (esp. recapture) early; replace with our own model later to cut per-call cost & vendor lock-in |
| Reality Defender / Sensity / Hive | Enterprise deepfake & synthetic-media detection | **DON'T COMPETE head-on.** They're general media/deepfake; we're vertical e-commerce returns. Different buyer, different workflow |
| Truepic | Trusted **capture-time** authenticity SDK | **COMPLEMENTARY.** They verify at capture; we verify arbitrary post-hoc uploads. Different problem |
| C2PA / Content Credentials / OpenAI Verify / Google SynthID | Provenance standards & watermark verification | **CONSUME, don't build.** We verify these as one metadata signal — never our whole story |
| AI-or-Not / TrueMedia | Consumer "is this AI?" tools | Not enterprise, no workflow, no localization. Not real competitors for our buyer |

**Where we win:** fusion score (not binary), region heatmaps, e-commerce product cross-check,
reviewer dashboard with audit trail, per-tenant model versioning. The dashboard + fusion +
Layer 4 is the product; any single detector is a commodity.

---

## 2. The screenshot / recapture problem — our actual answer

The user's core worry: *"a fraudster screenshots the AI image, so metadata/PRNU/pixel
forensics die — then we can't do anything."*

Reframe: **a screenshot is not an escape, it is itself a signal.**

- Screenshot / photo-of-screen **destroys**: EXIF, C2PA, PRNU, and badly degrades pixel-noise
  forensics (ELA/Noiseprint). True.
- But **recapture detection** (moiré, screen grid, glare, aliasing, resampling) reliably flags
  "this is a picture of a screen, not a direct camera capture."
- In the return-fraud context that is a **red flag by itself**: a legitimate damage photo is a
  direct phone capture. A screenshot/recapture of a "damaged" item is inherently suspicious.
- What still survives a screenshot: **semantic AI artifacts** (garbled text, impossible
  shadows/reflections, over-smooth textures) — these live in image content, not pixel noise —
  and **CLIP-feature detectors**, which are far more recompression-robust than raw-pixel
  detectors.

So we flip evasion into detection:

```
recapture_detected = TRUE
        AND (metadata_absent OR semantic_ai_artifacts_present)
   ==> HIGH fraud risk
```

Concrete mitigations baked into the system:
1. **Recapture/screenshot detector as a first-class Layer** (not an afterthought).
2. **Screenshot-augmented training** for Layer 1: resize + JPEG q70–90 + crop + slight blur on
   all training data, so the classifier learns *post-screenshot* artifacts, not pristine ones.
3. **Metadata is neutral evidence, never proof.** Clean-or-absent metadata contributes ~0 to
   the fusion score on its own (a genuine WhatsApp-resaved phone photo loses metadata too).
   Absent metadata only matters *in combination* with other signals.

---

## 3. Signal layers — build vs. buy

| # | Layer | Primary approach | Build/Buy | Notes |
|---|---|---|---|---|
| L1 | AI-generation detection | **Ensemble, 3 modes in precedence order:** (1) local trained CLIP-head checkpoint (UniversalFakeDetect approach, screenshot-augmented); (2) **HF Inference API ensemble** of pretrained detectors — zero training, zero GPU hosting; (3) neutral stub | **Buy-then-build** | HF-ensemble path shipped (`app/hf_inference.py` → `l1_aigen.py`); default members Apache-2.0. Local-checkpoint loading also wired; no checkpoint committed yet. See §3a |
| L2 | Manipulation / edit forensics | TruFor (pretrained) for forgery localization + heatmap; CAT-Net/MVSS-Net as alternates | **Buy (pretrained inference)** | TruFor adapter + heatmap artifact persistence are wired; still stubbed until external repo/weights are configured |
| L3 | Recapture / screenshot | Sightengine Recapture API (day 1) → custom moiré/screen-artifact CNN (later) | **Buy → Build** | The screenshot-fraud answer |
| L4 | Metadata & provenance | exiftool + piexif (EXIF), c2patool/c2pa-python (C2PA), SynthID check | **Buy (libs/CLIs)** | Neutral-weight signal only |
| L5 | E-commerce context cross-check | **v0 (shipped):** perceptual-hash + color-histogram similarity vs listing photos, plus a direct DB scan against recent claims for reused-photo detection. **v1 (target):** DINOv2/OpenCLIP embeddings + Qdrant ANN search; external reverse-image search (TinEye/SerpAPI) for photos stolen from *outside* our own system; lighting/shadow consistency | **Build (our moat)** | v0 lives in `backend/app/context_checks.py` — no public dataset, we build the seller-listing↔claim pair data for v1 |

**Scope discipline:** we train *one* head (L1) and *one* small recapture model (L3, later
phase). Everything else is pretrained inference or third-party libs. That keeps compute and
timeline sane while still being a "legend" fused system.

---

## 3a. L1 as an ensemble — reuse the pretrained field, don't out-train it

The single fastest path to real L1 accuracy is **not** training our own detector first — it's
calling an **ensemble of pretrained AI-image detectors already served on the HF Inference
API**. Rationale:

- **Zero training, zero GPU hosting.** These run on HF's serverless inference; we send image
  bytes and get a label back. Directly answers the "no local GPU / avoid idle GPU cost"
  constraint (see [ML_PLAN.md](ML_PLAN.md) §6).
- **Ensembling is the accuracy move, not a shortcut.** Independent architectures (SigLIP, Swin,
  ViT) make *uncorrelated* errors, so averaging them generalizes better to unseen generators
  than any single model — the same fusion logic that governs the whole product, applied one
  level down. L1's own output is already a mini-fusion.
- **License-aware defaults.** Members ship commercial-safe: `Ateeqq/ai-vs-human-image-detector`
  (SigLIP, Apache-2.0) + `Nahrawy/AIorNot` (Swin, Apache-2.0). `umm-maybe/AI-image-detector`
  (CC-BY-4.0, needs attribution) is an optional add. `Organika/sdxl-detector` (682K downloads
  but **CC-BY-NC**) is eval/demo only — never in the commercial default set.

Implementation (`backend/app/hf_inference.py`): each member's heterogeneous labels
("artificial"/"human", "ai"/"real", …) are normalized to a single P(AI-generated) by keyword,
so adding a model needs no per-model config; one member failing (cold model / rate limit)
doesn't kill L1 — we average whoever answered and only error when *all* fail. Config:
`HF_API_TOKEN`, `L1_HF_MODELS`, `HF_INFERENCE_TIMEOUT_SECONDS`.

Trajectory: HF ensemble is the day-one detector; our own screenshot-augmented CLIP head
(when trained) takes precedence and can be *added* to the ensemble as one more member. The
same pattern is the right long-term answer for L2 as well (prefer a pretrained forensics model
over a bespoke one where one exists).

---

## 4. Fusion engine — the accuracy story

Each layer emits a normalized `{score ∈ [0,1], confidence, evidence}`. A **meta-classifier**
(gradient-boosted trees or logistic regression — a stacking model) trained on labeled
fraud/legit claims combines them into one calibrated risk score.

**Implementation status:** the runtime scorer, training pipeline, and export format for
exactly this already exist and are tested — `backend/app/fusion/learned.py` (standardized
logistic regression + Platt-style calibration, loads an exported JSON), `ml/fusion/train_meta.py`
and `features.py` (trains and exports from labeled claim JSONL). `fuse()` in
`backend/app/fusion/engine.py` uses the learned model automatically when `FUSION_MODEL_PATH`
is set (falls back to the weighted average below on any load/score failure, logged not
swallowed). **What's missing is not code — it's real labeled claims data** to train on; until
then `FUSION_MODEL_PATH` stays unset and the weighted-average fallback is what actually runs.

- **Calibration** (Platt / isotonic) so "87%" actually means 87% — critical for a threshold
  the business trusts.
- **Explainability**: report shows per-signal contribution ("inpainting in region X: +0.3;
  recapture detected: +0.25; EXIF absent: +0.02"). SHAP over the meta-classifier.
- **Never a binary verdict.** Output = confidence-scored report + heatmap; a **human reviewer
  makes the final call**. This is the accuracy story *and* the legal shield (same
  human-in-the-loop framing as the invigilator project).
- **Missing-signal robustness**: the meta-model must handle any layer being absent (e.g. an API
  timed out) — train with feature dropout so it degrades gracefully.

The benchmark we publish is the honest one: **train on SD, test on Flux/unseen generators**,
report *that* held-out number, not a same-distribution 99%.

---

## 5. Enterprise architecture

Return-fraud checks are **async, low-QPS, bursty** events — not real-time chat. That shapes
everything: queue-driven, serverless GPU that scales to zero, no always-on GPU box.

The orchestrator is a **LangGraph state graph**: deterministic analyzers are tool nodes,
Gemini (Vertex AI) agents add semantic/contextual signals, and conditional edges route only
risky/uncertain cases through the expensive agent pass.

```
Client (shopping platform)
   │  POST /v1/claims  (image + order context, API key)
   ▼
API Gateway ── auth, rate-limit, per-tenant keys ──► Postgres (claims, results, audit log)
   │                                                  MinIO/S3 (images)
   ▼ enqueue
Job Queue (Redis + Celery / or SQS)
   ▼
LangGraph orchestrator (state graph)
   │
   ├─ Stage A: deterministic analyzers (parallel fan-out — ground-truth signals)
   │    ├─ L1 AI-gen      (serverless GPU: Modal/RunPod)
   │    ├─ L2 forensics   (serverless GPU: TruFor)
   │    ├─ L3 recapture   (Sightengine API — shipped)
   │    ├─ L4 metadata    (CPU: EXIF + c2patool — shipped)
   │    └─ L5 context     (v0 shipped: hash+histogram vs listing/recent-claims;
   │                       v1 target: DINOv2 embed → Qdrant search + reverse-image API)
   │
   ├─ conditional routing:
   │    high-confidence clean ──────────────► skip agents (save credits)
   │    recapture / uncertain / flagged ────► Stage B
   │
   ├─ Stage B: VLM agent pass (Gemini on Vertex AI)
   │    ├─ Semantic artifact inspector  (garbled text, impossible shadows/reflections,
   │    │                                unnatural textures — SURVIVES SCREENSHOTS)
   │    └─ Damage plausibility agent    (claim vs listing photo: same product? damage
   │                                     plausible? lighting consistent?)
   │
   ├─ Fusion node (meta-classifier + calibration + SHAP; agent signals = extra features)
   │
   └─ Report agent (Gemini): raw signals → human-readable reviewer report
   ▼ persist result + heatmap + report
Reviewer Dashboard (Next.js) ── heatmap overlay, signal breakdown, human decision
   ▼
Webhook / API response to platform + feedback captured for retraining
```

**Agent design rules:**
- Deterministic CV models are the ground truth; agents *reason over* them and add semantic
  signals — they never replace classifiers. (A VLM judging "is this AI?" from pixels is
  weaker than the CLIP head; a VLM judging "is this damage plausible for this product?" is
  something no classifier can do.)
- **Cost gating**: agents run only on the uncertain/flagged branch — Vertex spend scales with
  risk, not volume. High-confidence-clean claims never touch an LLM.
- The semantic inspector is a direct counter to screenshot evasion: semantic artifacts live in
  image *content*, so recompression/recapture can't wash them out.
- Agent outputs are structured (Pydantic schemas), versioned, and logged like any other
  signal — they feed fusion as features, and the audit trail records prompts + model versions.

Enterprise/scale concerns designed in from the start:
- **Multi-tenancy**: per-platform API keys, isolated data, per-tenant model versions & thresholds.
- **Model registry & versioning**: every result records which model versions produced it (audit).
- **Drift monitoring**: track score distributions per generator; alert when a new generator tanks L1.
- **Human-review feedback loop**: reviewer decisions become labeled data → periodic retrain.
- **Observability & audit log**: immutable record of inputs, signals, versions, and the human
  decision — legal defensibility.
- **Cost control**: scale-to-zero GPU, cache embeddings, short-circuit fusion when a cheap
  strong signal already decides (e.g. valid SynthID watermark → likely AI, stop early).

---

## 6. Tech stack

- **Backend/API**: FastAPI (Python), Pydantic contracts.
- **Orchestration / agents**: LangGraph state graph; Gemini via Vertex AI
  (`langchain-google-vertexai`) — funded by existing Vertex credits. Stub LLM fallback so
  the graph runs locally with no credentials.
- **Queue/workers**: Celery + Redis — **shipped** (`backend/app/jobs.py`, `celery_app.py`);
  requires a running worker + Redis to actually process async claims, see README quickstart.
- **Models**: PyTorch; served on Modal or RunPod serverless GPU (scale-to-zero) — target for
  hosted inference. Today, L1 has training scaffolding, runtime checkpoint loading, and an HF
  serverless ensemble path on `main`, while L2 has a real TruFor integration path; both layers
  still fall back safely when their external model artifacts or credentials are absent.
- **Vector DB**: Qdrant — **not wired into any code path yet** (docker-compose has a Qdrant
  service, but L5 v0 uses direct SQL + in-process hashing, no vector index). Target for L5 v1.
- **Data stores**: SQLite by default (`sqlite:///./truthpixel.db`, override via `DATABASE_URL`
  for Postgres), local-disk artifact storage by default (override to S3/MinIO via
  `STORAGE_BACKEND=s3`) — **shipped** (`backend/app/storage/`, `artifacts.py`).
- **Dashboard**: Next.js + React reviewer scaffold — **built on `origin/main`** with queue,
  claim detail, decision capture, audit trail, and heatmap overlay; not yet hardened for a
  deployed reviewer auth flow.
- **Forensics/metadata**: EXIF (Pillow) + `c2patool` subprocess — **shipped**. `piexif`,
  `c2pa-python` not currently used.
- **3rd-party APIs**: Sightengine (recapture) — **shipped and wired** (`l3_recapture.py`,
  falls back to a neutral stub without API keys). TinEye/SerpAPI (reverse image) — **not
  implemented**; only placeholder env vars exist in `.env.example`.

---

## 7. Data & training plan

Full detail in [ML_PLAN.md](ML_PLAN.md). The short version — we train exactly three things:

| # | Model | Phase |
|---|---|---|
| T1 | L1 CLIP-head (frozen ViT-L/14 → MLP head) w/ screenshot augmentation | 0 |
| T2 | Fusion meta-classifier (LightGBM/LogReg + calibration + SHAP) | 1 |
| T3 | L3 recapture CNN (own dataset, device-matrix capture) | 2 |

Datasets: GenImage (primary L1), CASIA/DEFACTO/IMD2020 (L2 eval), **own-built** recapture
and listing↔claim datasets (L3/L5 — the moat data). Headline metric: **held-out-generator
AUROC + robustness matrix** (pristine / JPEG / screenshot-sim / social-roundtrip).

---

## 8. Phased roadmap

Full checklists in [ROADMAP.md](ROADMAP.md).
- **Phase 0 — demo:** local end-to-end pipeline; the repo already has queue/persistence/dashboard
  scaffolding, but a true demo still needs a configured non-stub L1 path (HF ensemble or a
  trained checkpoint), configured TruFor, and live Vertex verification; exit = the
  screenshot-of-AI case is flagged with correct explanation.
- **Phase 1 — product:** learned fusion in production, L5 v1 (DINOv2+Qdrant), dashboard/auth
  hardening, serverless GPU, published honest benchmark; exit = pilot-able.
- **Phase 2 — enterprise:** own recapture model, multi-tenancy, model registry, drift
  monitoring, retrain-from-reviewer-labels loop, SDK/webhooks.

---

## 9. Implemented repo layout (current — not aspirational)

```
backend/
  app/
    main.py            # FastAPI: sync + async claims, status, decision, audit, artifacts, /health
    config.py          # pydantic-settings; DB/storage/queue/Vertex/gating/threshold env
    schemas.py         # SignalResult, AgentFinding, FusionResult, ClaimReport, StoredClaim, ...
    analyzers/         # L1–L5 behind one Analyzer ABC (error-isolated)
                        #   L1 aigen: local checkpoint -> HF ensemble -> neutral stub
                        #   L2 forensics: TruFor adapter + heatmap artifacts, stub until configured
                        #   L3 recapture, L4 metadata, L5 context: REAL
    agents/            # Gemini agents (semantic, plausibility, report) + stub fallback
    graph/build.py     # LangGraph: analyzers → gated agents → fusion → report
    fusion/engine.py   # weighted fusion + screenshot-evasion combo rule
    context_checks.py  # L5 v0: perceptual-hash + histogram image fingerprinting
    storage/           # SQLAlchemy models + repository (claims, audit events, artifacts)
    artifacts.py       # local-disk / S3 artifact store
    jobs.py, celery_app.py  # async claim queue (Celery), webhook dispatch
  tests/               # smoke, persistence, async-queue, recapture, context-analyzer tests
ml/
  layer1_aigen/         # L1 dataset/augment/model/train/eval scaffold
  fusion/               # learned-fusion feature assembly + training/export helpers
dashboard/             # reviewer dashboard scaffold (queue/detail/review)
webapp/                # public self-serve webapp (thin client, same API) — built, not yet run
docs/                  # this doc suite
```

Not yet created: `scripts/`, `ml/recapture/`, and `ml/datagen/`. `dashboard/` and `ml/fusion/`
now exist; the remaining gap is turning those scaffolds into deployed, model-backed flows.

---

## 10. Product surfaces — one core, three doors in

Full detail in [USE_CASES.md](USE_CASES.md). Same `run_claim()` pipeline and fusion engine
behind all three; only auth and context fields differ:

| Surface | Audience | Auth | `ClaimContext` | Status |
|---|---|---|---|---|
| B2B API | Platform backends (returns integration) | tenant API key when `API_AUTH_ENABLED=true`; local-dev bypass otherwise | full (order/listing) | shipped; auth and rate limits are implemented but optional by config |
| Reviewer dashboard | Tenant's internal fraud-review staff | reviewer auth still pending; today it talks to the stored-claim API surface | full, plus decision capture | scaffold built — queue, claim detail, heatmap overlay, audit, decision capture |
| Public webapp (`webapp/`) | Anyone, self-serve, one image at a time | anonymous path exists; public-IP throttling is available when auth is enabled | none — L5 and damage-plausibility no-op gracefully | code written, not yet run/verified end-to-end in this environment |

The public webapp is also the top-of-funnel every self-serve competitor (AI-or-Not,
TrueMedia) uses — ours shows the fusion breakdown instead of a bare percentage, which is the
wedge from free visitor to enterprise conversation. CORS for `webapp/` and `dashboard/` origins
is configured in `backend/app/config.py` (`cors_allow_origins`).

---

## 11. Honest caveats (say these out loud — reviewers respect it)
- Novel generators will beat L1; that's why L2–L5 exist. **Fusion is the accuracy story.**
- Screenshot evasion is real; we mitigate (recapture detection + augmentation) but don't claim
  to "solve" it.
- Image forensics is a mature academic field; **our differentiator is the e-commerce fusion +
  product cross-check + reviewer workflow**, not a novel detector.
