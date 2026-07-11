# Roadmap — Phase 0 → 2

> Concrete, checkable milestones. Local-first development; cloud only when it earns its cost.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md) ·
> [CORRECTIONS.md](CORRECTIONS.md) (full-system audit log — bugs found/fixed each pass)

## Reality snapshot — 2026-07-08

Before reading the phase checklist, anchor on the repo as it really exists today:

| Area | Already built on `origin/main` | Branch-only today | Still missing before the own-model L1 upgrade is complete |
|---|---|---|---|
| Core backend | Sync + async claims, persistence, audit log, artifact storage, webhook callbacks, tenant/admin auth hooks, public-submission rate limiting | No major unmerged backend capability confirmed; most historical feature branches already landed on `main` | Hosted auth rollout, worker/GPU deployment, observability |
| Signal layers | L1 local-checkpoint path plus HF ensemble path, L2 TruFor adapter + heatmap artifact persistence, L3 Sightengine, L4 EXIF + `c2patool`, L5 v0 hash/histogram checks | No meaningful branch-only signal-layer implementation confirmed | Train and evaluate a domain-tuned L1 checkpoint, configure TruFor artifacts, then verify live inference |
| Reviewer surfaces | `dashboard/` exists with queue, claim detail, decision capture, audit trail, and heatmap overlay | — | Auth polish, live API verification, reviewer workflow hardening |
| ML tooling | `ml/layer1_aigen/` training scaffold and `ml/fusion/` learned-fusion tooling both exist | — | Real data, exported artifacts, calibrated model versions in runtime |

The main distinction is not branch-only code anymore, but configured-vs-unconfigured runtime:
the repo already contains the L1/L2 integration paths, yet they still depend on external
configuration. L1 can already run via the HF ensemble with `HF_API_TOKEN`, but the
domain-tuned checkpoint path still needs a real training run; L2 still needs an external
TruFor checkout/weights.

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
- [x] L1 own-model upgrade: **trained, deployed, and verified live (2026-07-10).** First real
      checkpoint trained on Kaggle (`run_20260710_0737`, see
      [docs/KAGGLE_TRAINING.md](KAGGLE_TRAINING.md)) — CIFAKE (3k/class) + DiffusionDB (3k) +
      COCO real fallback (3k) + 25-prompt self-generated SDXL held-out bucket, 5 epochs.
      **Held-out-generator headline metric (sdxl/midjourney/flux, unseen in training): 0.9688
      AUROC / 0.8959 accuracy on `screenshot_sim`**, robustness matrix holds across all four
      variants (0.9688–0.9728 AUROC). Val 0.8891 vs. train 0.8904 — no overfitting. Checkpoint
      wired into `backend/models/l1_clip_head.pt` via `L1_MODEL_PATH`/`L1_MODEL_DEVICE=cpu` and
      confirmed running through the live backend: `provider: local-clip-head`, real inference,
      contributes as the top-weighted signal in the end-to-end demo (`scripts/demo.py`).
      **Follow-up (not blocking):** CIFAKE is 32×32, so this is a bootstrap-scale run — a
      larger/higher-res training set would raise the ceiling; and pre-warm the ViT-L/14 encoder
      weights on any inference host (first load pulls ~1.3GB over the network).
- [x] L2 real: TruFor subprocess inference (`backend/app/trufor.py`) + heatmap PNG artifact,
      gated on `l2_trufor_configured` (repo dir + model file set), stub fallback otherwise
- [x] L3 real: Sightengine recapture API call (keys already templated in `.env.example`)
- [x] L4: add c2patool subprocess check
- [x] L5 real (v0): `context_checks.py` perceptual-hash + color-histogram similarity —
      listing-photo match/mismatch scoring, plus intra-system reused-photo detection by
      scanning recent claim artifacts.
- [x] L5 real (v1, zero-training): `backend/app/embeddings.py` blends a frozen-CLIP
      (ViT-B-32) embedding cosine similarity into the v0 score — pure inference, reuses the
      `open_clip` loader L1's checkpoint path uses. Degrades to v0-only automatically when
      torch/open_clip_torch aren't available or the model fails to load (never breaks L5).
      Config: `L5_EMBEDDING_ENABLED`/`_MODEL`/`_PRETRAINED`/`_DEVICE`/`_WEIGHT`. Tests:
      `test_embeddings.py`, `test_context_analyzer.py`. **Not yet done:** Qdrant ANN search
      (only matters once claim volume makes the linear scan too slow) or TinEye/SerpAPI
      (catches photos stolen from *outside* our own claims DB) — tracked as L5 v2 below.
- [x] Async claim queue: `POST /v1/claims/async`, `GET /v1/claims/{id}/status`, webhook
      dispatch on completion (`backend/app/jobs.py`, `celery_app.py`) — **operational caveat:**
      needs a running Celery worker + Redis, or `CELERY_TASK_ALWAYS_EAGER=true` for local dev;
      without either, queued claims stay `pending` forever (not yet documented anywhere but
      here and the README quickstart)
- [x] Claim persistence + review: SQLite-by-default storage, `GET /v1/claims`,
      `POST /v1/claims/{id}/decision`, `GET /v1/claims/{id}/audit`, artifact upload/download
      (original upload + heatmap) — `backend/app/storage/`, `artifacts.py`
- [x] Vertex agents live (2026-07-10): `GOOGLE_CLOUD_PROJECT` set (EduFX project, GenAI App
      Builder credits — Vertex API calls only, not compute; local auth via `gcloud` ADC, no
      service-account key needed for dev). **Found and fixed two real bugs getting here:**
      (1) `.env.example`'s `VERTEX_MODEL=gemini-2.0-flash` 404s as a Vertex publisher model —
      Vertex's Gemini naming differs from Google AI Studio's; `gemini-2.5-flash` confirmed
      working live, both `.env.example` and this deploy's `.env` updated. (2) `semantic_inspector`
      failed on every real call with "unparseable agent output: Unterminated string" — Gemini
      2.5's hidden "thinking" tokens were eating into `max_output_tokens=1024`, truncating the
      JSON response mid-string; fixed via `thinking_budget=0` in `backend/app/agents/llm.py`
      (structured JSON extraction doesn't need extended reasoning; also cuts latency/cost).
      **Verified live** post-fix: `damage_plausibility` and `semantic_inspector` both return
      real, coherent, specific Gemini findings (not stub) — e.g. correctly identifying an
      irrelevant landscape photo as fraud-signal-bearing with a specific explanation.
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
- [x] Fixed: `FUSION_MODEL_PATH` was read via `os.getenv` instead of the `Settings` class, so
      setting it only in `.env` silently never took effect (and the failure was silently
      swallowed). Now reads `settings.fusion_model_path`, logs a warning on fallback. See
      [CORRECTIONS.md](CORRECTIONS.md) 2026-07-08.
- [x] Dashboard auth: `dashboard/app/api.ts` now sends `X-API-Key` (from `NEXT_PUBLIC_API_KEY`)
      when set; no-op otherwise, so the default `API_AUTH_ENABLED=false` path is unaffected.
      `dashboard/.env.local.example` added. Auth-on backend tests now cover tenant issuance,
      keyed dashboard requests, missing-key 401s, and cross-tenant 404s. Still not done:
      deployed dashboard smoke against Cloud Run.
- [x] Fixed: `init_db()` only ever called `Base.metadata.create_all()`, which creates missing
      tables but never alters existing ones — so any SQLite DB created before a column (e.g.
      `claims.tenant_id`) was added would 500 forever on every query touching it, found via
      live browser verification of the dashboard-auth change above. Original fix was a
      lightweight self-healing column-adder; **superseded 2026-07-10 by a real migration
      framework** — see below.
- [x] Real migration framework: `backend/alembic/` — `init_db()` now runs `alembic upgrade
      head` instead of the ad-hoc column-adder, which is gone (its logic lives in the
      idempotent baseline migration `0001_baseline_schema.py` instead). Future schema
      changes are real, reviewed migrations (`alembic revision --autogenerate`), not more
      runtime patching. Verified via CLI (`alembic current` → `0001 (head)`) and full suite
      (63/63). Found and fixed a real footgun along the way: `env.py`'s Alembic-generated
      default calls `logging.config.fileConfig()`, which resets the *root* logger's handler
      list — since this runs on every app startup, it was silently breaking `caplog`-based
      log-capture tests (and would break the app's own logging in production the same way).
      See [CORRECTIONS.md](CORRECTIONS.md) 2026-07-10.
- [ ] Reviewer dashboard hardening: tenant switcher, production UX polish (auth header support
      landed above)
- [x] Demo script: `scripts/demo.py` — submits curated claims to a live backend, prints the
      fused report. 2/5 cases (`screenshot_of_ai`, `reused_photo`) run reproducibly with no
      external images (reuses `ml/layer1_aigen/augment.py`'s screenshot-sim); the other 3
      (`real_damage`, `ai_fake`, `inpainted`) need real source images via CLI flags —
      deliberately not fabricated procedurally (see script docstring). Running it live found
      and fixed **three real bugs**: L5's reuse detection was dead code without listing URLs,
      `L5_EMBEDDING_ENABLED` defaulting to `true` could hang a request (and inflated the full
      test suite from ~20s to 431s) by attempting a network model download inline, and that
      same embedding call blocked the whole event loop instead of running in a thread. All
      fixed; see [CORRECTIONS.md](CORRECTIONS.md) 2026-07-10 (2).
- [x] Fixed live via the demo script above: L5 reuse-photo detection now runs independent of
      listing URLs, and `L5_EMBEDDING_ENABLED` now defaults to `false` (opt-in, matching
      L1/L2/L3's pattern) with the embedding call properly backgrounded via `asyncio.to_thread`.

**Exit criterion:** the screenshot-of-AI-image demo case is flagged with a correct explanation
— **met**: `scripts/demo.py`'s `screenshot_of_ai` case is flagged (risk 0.80) in a live run
against a real backend, with **L1 now a real trained checkpoint** (see the L1 own-model item
above) contributing as the top-weighted signal (score 0.76, `provider: local-clip-head`) rather
than a stub. L3 recapture is still a Sightengine stub in this environment, so the "screenshot"
half of the explanation still leans on L5 reuse-match rather than genuine recapture-artifact
detection; wiring Sightengine keys (or training T3) would complete that. The L1/AI-generation
half of the explanation is now genuinely model-driven. **Caveat on demo numbers:** the 3
reproducible cases run against a plain placeholder image (no real photo/AI-fake supplied), so
L1's 0.76 there proves the *wiring and fusion contribution*, not discrimination — for a
meaningful real-vs-AI accuracy demonstration, run `scripts/demo.py --real-damage <photo>
--ai-fake <ai-image>` with genuine source images (the held-out 0.9688 AUROC is the real
accuracy number; see KAGGLE_TRAINING.md).

## Phase 1 — Real product (target: +2–3 months)

**Goal:** a platform could pilot it. (Async job queue landed ahead of schedule during
Phase 0 — see the Phase 0 checklist above; its operational caveat about needing a running
Celery worker still applies.)

- [x] Persistence foundation: database-backed claims, signals, reviewer decisions, and audit log
- [x] Object storage: local/S3-compatible claim images + heatmaps
- [x] Learned-fusion tooling scaffold: `ml/fusion/features.py` + `ml/fusion/train_meta.py`
- [ ] L5 v2: Qdrant ANN search to replace the linear scan over `L5_RECENT_CLAIM_WINDOW`; add
      external reverse-image search (TinEye/SerpAPI) for photos stolen from outside our own
      claims DB (v1 — embedding blend — landed in Phase 0, see above)
- [x] Public webapp: anonymous submission path (IP rate-limited via `PUBLIC_SUBMISSION_ENABLED`,
      see Phase 0 above). **Still not done:** image-retention policy stated on the page itself,
      optional free API-key signup for higher usage (see USE_CASES.md §3)
- [ ] Learned fusion in production: LightGBM/LogReg + calibration + SHAP trained on real labels,
      exported for backend runtime use (tooling exists, model artifacts do not)
- [ ] Reviewer dashboard productionization: auth, tenant verification, deploy/runtime proof, and
      reviewer ergonomics on top of the existing scaffold
- [ ] Feedback capture → labeled-claims table (fuel for fusion retraining)
- [ ] Serverless GPU inference (Modal or RunPod) for L1/L2; scale-to-zero
- [x] Held-out-generator benchmark + robustness matrix, published in docs — 0.9688 AUROC
      (screenshot_sim, sdxl/midjourney/flux held out), full matrix in
      [docs/KAGGLE_TRAINING.md](KAGGLE_TRAINING.md) and the L1 own-model item above
- [x] Backend containerized: `backend/Dockerfile` (CPU-only torch, no `.env` baked in, checkpoint
      included if `backend/models/` has one) + root `.dockerignore`. The documented hosted path
      is now Cloud Run + Supabase Postgres; see [CLOUD_RUN_SUPABASE.md](CLOUD_RUN_SUPABASE.md).
      **Not yet done:** live Cloud Run deployment from this environment, because no target GCP
      project/secrets/Supabase connection are available here. The repo-side workflow, runtime
      env requirements, and smoke checklist are documented.
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
