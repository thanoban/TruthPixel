# TruthPixel — Image Integrity Verification for E-commerce Returns

> Master design doc. Draft v0.3 — 2026-07-08.
>
> Companion docs: [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) ·
> [AGENTS.md](AGENTS.md) · [USE_CASES.md](USE_CASES.md) · [ROADMAP.md](ROADMAP.md)

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
| L1 | AI-generation detection | CLIP ViT-L/14 features + trained MLP head (UniversalFakeDetect approach) + lightweight NPR CNN as second opinion | **Train head only** | Best cross-generator generalization; head is cheap to train |
| L2 | Manipulation / edit forensics | TruFor (pretrained) for forgery localization + heatmap; CAT-Net/MVSS-Net as alternates | **Buy (pretrained inference)** | Gives the demo-friendly region heatmap |
| L3 | Recapture / screenshot | Sightengine Recapture API (day 1) → custom moiré/screen-artifact CNN (later) | **Buy → Build** | The screenshot-fraud answer |
| L4 | Metadata & provenance | exiftool + piexif (EXIF), c2patool/c2pa-python (C2PA), SynthID check | **Buy (libs/CLIs)** | Neutral-weight signal only |
| L5 | E-commerce context cross-check | DINOv2/OpenCLIP embeddings + vector DB (Qdrant) vs seller listing photos; reverse-image search (TinEye/SerpAPI) for reused/stolen damage photos; lighting/shadow consistency | **Build (our moat)** | No public dataset — we build the seller-listing↔claim pair data |

**Scope discipline:** we train *one* head (L1) and *one* small recapture model (L3, later
phase). Everything else is pretrained inference or third-party libs. That keeps compute and
timeline sane while still being a "legend" fused system.

---

## 4. Fusion engine — the accuracy story

Each layer emits a normalized `{score ∈ [0,1], confidence, evidence}`. A **meta-classifier**
(gradient-boosted trees or logistic regression — a stacking model) trained on labeled
fraud/legit claims combines them into one calibrated risk score.

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
   │    ├─ L3 recapture   (API now → own model later)
   │    ├─ L4 metadata    (CPU: exiftool/c2pa)
   │    └─ L5 context     (DINOv2 embed → Qdrant search + reverse-image API)
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
- **Queue/workers**: Celery + Redis (self-host) or SQS + Lambda/Modal (cloud).
- **Models**: PyTorch; served on Modal or RunPod serverless GPU (scale-to-zero).
- **Vector DB**: Qdrant (embeddings for L5 product matching).
- **Data stores**: Postgres (claims/results/audit), MinIO or S3 (images).
- **Dashboard**: Next.js + React (reviewer UI, heatmap overlays).
- **Forensics/metadata**: exiftool, piexif, c2patool/c2pa-python.
- **3rd-party APIs (early)**: Sightengine (AI-gen + recapture), TinEye/SerpAPI (reverse image).

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
- **Phase 0 — demo:** local end-to-end pipeline; L1 trained, L2 TruFor, L3 Sightengine,
  agents live on Vertex; exit = the screenshot-of-AI case is flagged with correct explanation.
- **Phase 1 — product:** queue + persistence, learned fusion, L5 (DINOv2+Qdrant), reviewer
  dashboard, serverless GPU, published honest benchmark; exit = pilot-able.
- **Phase 2 — enterprise:** own recapture model, multi-tenancy, model registry, drift
  monitoring, retrain-from-reviewer-labels loop, SDK/webhooks.

---

## 9. Implemented repo layout (Phase 0 scaffold)

```
backend/
  app/
    main.py            # FastAPI: POST /v1/claims, GET /health
    config.py          # pydantic-settings; Vertex + gating + threshold env
    schemas.py         # SignalResult, AgentFinding, FusionResult, ClaimReport
    analyzers/         # L1–L5 behind one Analyzer ABC (error-isolated)
    agents/            # Gemini agents (semantic, plausibility, report) + stub fallback
    graph/build.py     # LangGraph: analyzers → gated agents → fusion → report
    fusion/engine.py   # weighted fusion + screenshot-evasion combo rule
  tests/               # end-to-end smoke + fusion rules
ml/                    # training scaffolds (see ML_PLAN.md §5)
webapp/                # public self-serve webapp (thin client, same API)
dashboard/             # Next.js reviewer UI (Phase 1, internal/tenant-scoped)
docs/                  # this doc suite
```

---

## 10. Product surfaces — one core, three doors in

Full detail in [USE_CASES.md](USE_CASES.md). Same `run_claim()` pipeline and fusion engine
behind all three; only auth and context fields differ:

| Surface | Audience | Auth | `ClaimContext` |
|---|---|---|---|
| B2B API | Platform backends (returns integration) | per-tenant API key | full (order/listing) |
| Reviewer dashboard | Tenant's internal fraud-review staff | SSO / tenant login | full, plus decision capture |
| Public webapp (`webapp/`) | Anyone, self-serve, one image at a time | anonymous (rate-limited later) | none — L5 and damage-plausibility no-op gracefully |

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
