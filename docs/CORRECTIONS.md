# Corrections — full-system audit log

> Running log of full-system checks: what was verified, what was found broken and fixed, and
> an honest finished-vs-remaining snapshot. Each entry is dated; newest first. This is an audit
> trail, not a plan — see [ROADMAP.md](ROADMAP.md) for the phase-by-phase plan itself.

## 2026-07-08 — full-system audit

### Bug found and fixed

**`FUSION_MODEL_PATH` silently ignored when set only in `.env`.**
`backend/app/fusion/engine.py` read the learned-fusion model path via `os.getenv("FUSION_MODEL_PATH")`
instead of through the app's `Settings` class. Every other config value in the app loads from
`.env` via `pydantic-settings`, which does **not** mutate `os.environ` as a side effect — so a
value set only in `.env` (not exported as a real shell variable) was invisible to `os.getenv`,
and the learned model would silently never load, with no error, no log, nothing. On top of
that, the `try/except Exception: pass` around loading swallowed the failure completely.

Fixed:
- Added `fusion_model_path: str = ""` to `Settings` (`backend/app/config.py`).
- `engine.py` now reads `settings.fusion_model_path` instead of `os.getenv(...)`.
- The fallback path now logs a warning (`logger.warning(...)`) instead of silently passing,
  so a misconfigured or missing model file is visible in the logs instead of invisible.
- Verified: `test_fusion_engine.py` (2/2), full backend suite (38/38), full `ml/` suite (7/7)
  all still pass — the fix is backward compatible because `pydantic-settings` reads real
  process env vars too (which is what the existing tests set via `monkeypatch.setenv`), it
  just *also* now correctly reads `.env`-file-only values, which it didn't before.

### Doc gaps found and fixed

- **ARCHITECTURE.md §4 (Fusion engine)** described the learned meta-classifier as pure future
  work. In reality `backend/app/fusion/learned.py` (runtime scorer) and
  `ml/fusion/{features,train_meta}.py` (training/export) already exist, are tested, and are
  wired into `fuse()` — gated only on `FUSION_MODEL_PATH` being set to an exported model. What's
  actually missing is **labeled claims data to train on**, not code. Doc corrected.
- **`webapp/README.md`** Status section said "not yet built/run in this environment" — false;
  `.codex/runlogs/webapp.out.log` shows a real `npm install` + `npm run dev` + `GET / 200`.
  Corrected to state what was actually verified (boot + form render) vs. what wasn't
  (full submit-to-report round trip since the `StoredClaim` type fix).
- **`dashboard/README.md` didn't exist** — `webapp/` had one, `dashboard/` didn't, despite
  `dashboard/` being a fully-built, previously-verified Next.js app. Added, documenting the
  real verification evidence in `.codex/runlogs/{dashboard,backend}.out.log` (queue list, claim
  detail with heatmap overlay, decision submission, and audit-trail fetch all returned 200s
  against a live backend).

### What full-system verification actually showed (not re-run today, evidence audited)

A prior session (`.codex/runlogs/*.log`, `.codex/tmp/` artifacts) did real, non-mocked
verification: booted backend + webapp + dashboard together, submitted real claim images
(preserved in `backend/artifact_storage/claims/*/original_upload/`), exercised the full
dashboard review flow (queue → detail → decision → audit), and separately did a real TruFor
checkout-and-run attempt (see `docs/TRUFOR_SETUP.md`) — cloned the actual `grip-unina/TruFor`
repo, MD5-verified the official weights archive, confirmed the exact CLI contract and `.npz`
output keys, and ran it, hitting a genuine (and correctly surfaced) `ModuleNotFoundError:
yacs` because the upstream TruFor Python 3.7/torch-1.11/`mmcv-full` environment isn't
installed here. That failure is expected and correctly handled — `run_trufor_inference`
degrades to a clear error, `L2` degrades to a neutral stub, the pipeline doesn't crash.

This session re-ran the full automated test suite (`pytest`, both `backend/` and `ml/` —
**45/45 passing**) and read every file changed since, but did **not** re-run the live
browser verification — a backend process from the prior session (PID 22760) is still running
on `:8000` outside this session's tracking; it predates today's `fusion_model_path` fix (no
`--reload`), so it won't reflect that fix until restarted. Not force-restarted here per the
harness's workload-safety guardrail — restart it yourself (`Ctrl+C` then re-run
`uvicorn app.main:app --port 8000` from `backend/`) before relying on the fusion fix live.

---

## Finished vs remaining — honest snapshot

### Finished (real code, tested, not stub)

| Area | What | Evidence |
|---|---|---|
| Core API | Sync (`POST /v1/claims`) + async (`POST /v1/claims/async`, status polling, webhook callback) claim submission | `main.py`, `jobs.py`, `test_async_claims.py`, `test_pipeline.py` |
| Persistence | SQLite-by-default claim/signal/decision/audit storage, tenant-scoped | `storage/`, `test_persistence_api.py` |
| Artifact storage | Local-disk or S3/MinIO original-upload + heatmap storage, auto-persisted | `artifacts.py`, `signal_artifacts.py` |
| Auth & rate limits | Per-tenant API keys, admin-token-gated tenant/key management, per-tenant + public-IP rate limiting — all off by default | `auth.py`, `test_auth_api_keys.py` |
| L1 (AI-gen) | 3-mode analyzer: local checkpoint → **HF Inference API ensemble (real, zero-training)** → stub | `hf_inference.py`, `l1_aigen.py`, `test_hf_ensemble.py`, `test_l1_aigen.py` |
| L2 (forensics) | Real TruFor subprocess adapter, validated against the actual upstream repo/weights/CLI contract; auto heatmap-PNG artifact persistence | `trufor.py`, `signal_artifacts.py`, `TRUFOR_SETUP.md`, `test_trufor.py`, `test_forensics.py` |
| L3 (recapture) | Real Sightengine API call | `l3_recapture.py`, `test_recapture.py` |
| L4 (metadata) | Real EXIF extraction + real `c2patool` subprocess check | `l4_metadata.py`, `test_metadata.py` |
| L5 (context, v0) | Real perceptual-hash + color-histogram similarity vs. listing photos; intra-system reused-photo detection | `context_checks.py`, `test_context_analyzer.py` |
| Fusion (weighted) | Confidence-weighted average + screenshot-evasion combo rule — the default, always-available path | `fusion/engine.py::_weighted_fuse` |
| Fusion (learned) | Runtime scorer + training/export tooling, wired but **not populated** (no labeled data yet) | `fusion/learned.py`, `ml/fusion/`, `test_fusion_engine.py` |
| Agents | Gemini-on-Vertex semantic inspector / damage plausibility / report writer, cost-gated, stub fallback | `agents/`, `graph/build.py` |
| Public webapp | Upload → fused report UI, thin client | `webapp/`, verified booting |
| Reviewer dashboard | Queue, claim detail, heatmap overlay w/ opacity slider, decision form, audit trail | `dashboard/`, verified end-to-end against a live backend |

### Remaining (genuinely not done — not just "unconfigured")

| Area | What's missing | Blocker |
|---|---|---|
| L1 own model | No trained CLIP-head checkpoint | Needs a training run — plan exists in `COLAB_TRAINING.md`, not executed |
| L1 HF ensemble live use | Needs `HF_API_TOKEN` set to actually call the API | Just needs a token — no code work left |
| L2 real inference | TruFor code is correct but unrunnable here | Needs the upstream Python 3.7 / torch 1.11 / `mmcv-full` / `yacs` env — not installed |
| L5 v1 | DINOv2/Qdrant embeddings, external reverse-image search (TinEye/SerpAPI) | Not started — v0 (hash/histogram) is the only implementation |
| Learned fusion in production | No `FUSION_MODEL_PATH` populated | No labeled claims data yet — tooling is ready and waiting |
| Vertex agents live | Template-fallback report/agent text only | Needs `GOOGLE_CLOUD_PROJECT` + real credentials |
| Async queue in production | Needs a real Celery worker + Redis process | Works today only via `CELERY_TASK_ALWAYS_EAGER=true` (dev shortcut) |
| Dashboard auth | `dashboard/app/api.ts` never sends `X-API-Key` | Fine while `API_AUTH_ENABLED=false`; needs work before turning auth on |
| Demo script | 5 curated images (real damage, SDXL fake, inpainted, screenshot-of-AI, reused photo) | Not created |
| Reviewer dashboard hardening | Tenant switcher, auth, production UX polish | Scaffold works, not production-ready |

**Bottom line:** every one of the five signal layers has a real, working implementation path
today — three (L3, L4, L5-v0) run for free with no external setup, one (L1) runs for free with
an HF token, and one (L2) is fully correct code blocked purely on a heavy upstream Python
environment. Nothing is fake/mocked; everything that's a "stub" is a stub because it's
*unconfigured*, and degrades there deliberately and safely (error isolation, never crashes a
claim). The gap between "demo-ready" and "field-accurate" is data (labeled claims, a trained
L1 head) and infrastructure (a TruFor-capable Python env, Vertex credentials), not missing code.
