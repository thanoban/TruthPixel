# Corrections — full-system audit log

> Running log of full-system checks: what was verified, what was found broken and fixed, and
> an honest finished-vs-remaining snapshot. Each entry is dated; newest first. This is an audit
> trail, not a plan — see [ROADMAP.md](ROADMAP.md) for the phase-by-phase plan itself.

## 2026-07-11 — test-session env isolation fixed; docs synced to current roadmap state

Followed the roadmap's next urgent repo-side item: the test session is now isolated from
`backend/.env` regardless of what real local credentials or model paths that file contains.

**What was broken before:** tests that expected stub mode could accidentally pick up real
`GOOGLE_CLOUD_PROJECT`, `L1_MODEL_PATH`, HF, or other external settings from `backend/.env`
through `Settings(env_file=".env")`. That made the suite environment-sensitive and could turn
"unit-ish" tests into live Vertex/checkpoint runs.

**What changed:** root `conftest.py` now applies an `autouse` fixture that forces stub-safe
defaults for the external settings (`GOOGLE_CLOUD_PROJECT`, `L1_MODEL_PATH`, `HF_API_TOKEN`,
Sightengine keys, TruFor paths, `L5_EMBEDDING_ENABLED`) and clears the relevant runtime caches
before and after each test (`get_settings`, L1 checkpoint loader, Vertex LLM cache, embedding
cache, learned-fusion cache, storage/artifact/job caches).

**Verified live:** ran the full suite with deliberately hostile shell env values
(`GOOGLE_CLOUD_PROJECT=should-not-leak`, `L1_MODEL_PATH=D:/definitely/not/real.pt`) and the
repo still passed cleanly: **78/78**.

**Also synced in docs this pass:** ROADMAP.md no longer treats these as still-missing:
- A1: L2 classical forensics fallback is already wired and verified
- A1b: CASIA v2 eval harness exists in `ml/layer2_forensics/`
- A4: synthetic fraud-pair datagen exists in `ml/datagen/fraud_pairs.py`

## 2026-07-10 (3) — Vertex AI agents wired live; two real bugs found and fixed

Wired `GOOGLE_CLOUD_PROJECT` to a real GCP project (EduFX, GenAI App Builder credit scope —
Vertex API calls only, confirmed consistent with the credit-scope finding in ROADMAP.md's
standing decisions; not a new compute allowance). Auth via local `gcloud` Application Default
Credentials (already present for `thanobansk@gmail.com`) — no service-account key needed for
local dev. `aiplatform.googleapis.com` already enabled on the project.

Testing this live (not just checking config loads) found two real bugs:

**1. `.env.example`'s default `VERTEX_MODEL=gemini-2.0-flash` 404s on Vertex AI.** Vertex's
publisher-model namespace uses different names than Google AI Studio's direct Gemini API —
confirmed by probing several candidate model IDs live against the actual project;
`gemini-2.0-flash-001` also failed (transient connection error on retry, not conclusively
ruled out, but `gemini-2.5-flash` responded correctly on the first attempt). Fixed:
`.env.example` and this deployment's `backend/.env` both updated to `gemini-2.5-flash`, with a
comment noting this is a live-confirmed value that should be re-checked if Google
renames/deprecates it.

**2. `semantic_inspector` failed on every real call: `unparseable agent output: Unterminated
string starting at: line 6 column 5`.** Root cause: `gemini-2.5-flash` spends part of its
`max_output_tokens` budget on hidden "thinking" tokens before the visible answer (confirmed via
a real response's `usage_metadata`: `output_token_details: {reasoning: 20}` even for a 1-word
reply) — with `max_output_tokens=1024` in `backend/app/agents/llm.py`, thinking tokens were
eating enough of the budget that the JSON response got truncated mid-string on real
multi-finding outputs. Fixed: `thinking_budget=0` added to the `ChatVertexAI` constructor —
this task is structured JSON extraction, not something that benefits from extended reasoning,
so disabling it fixes the truncation and reduces latency/cost as a side benefit. Verified live
post-fix: `run_semantic_inspector()` called directly against a real photo returned coherent,
correctly-reasoned findings (score 0.0, confidence 1.0, three specific accurate observations),
no parse failure.

**Verified end-to-end:** `damage_plausibility` (which was already unaffected by the thinking-
token bug, since its shorter expected output apparently stayed under the truncation threshold)
returned real, specific, correct reasoning on a live claim — correctly identified a landscape
photo as irrelevant to a "damaged product" claim reason with a coherent explanation. This meets
ROADMAP.md's "Vertex agents live" Phase 0 exit item.

## 2026-07-10 (2) — demo harness + three real bugs it found live

Backend-only, no model training, no frontend. Built `scripts/demo.py`, the harness behind
ROADMAP.md's Phase 0 exit criterion ("the screenshot-of-AI-image demo case is flagged with a
correct explanation") — submits curated/reproducible claim images to a live backend and
prints the fused report. Deliberately does **not** fabricate fake "AI-generated" or
"manipulated" test images procedurally (a solid-color square is not a meaningful stand-in for
real generator artifacts, and presenting it as one would misrepresent what got tested) —
accepts `--ai-fake`/`--inpainted`/`--real-damage` paths for those, with sourcing guidance
printed when omitted. Two cases run out of the box with no external images: `screenshot_of_ai`
(reuses `ml/layer1_aigen/augment.py::build_robustness_variants` — the same screenshot-sim
already used for T1 eval) and `reused_photo`.

Running it against a live backend — not mocks — found three real bugs a unit-test-only pass
would not have caught:

**1. L5's intra-system reuse detection was completely gated behind supplying listing URLs,
even though it doesn't use them at all.** `ContextAnalyzer._run()` early-returned a neutral
stub whenever `listing_image_urls` was empty, before ever reaching the reuse-scan code below
it — so any claim submitted without listing photos got **zero** reuse-fraud detection, silently.
Given listing URLs are an optional, integration-specific field (not every platform will pass
them), this made one of L5's most valuable, novel signals dead code in a very plausible
real-world configuration. A second, related ordering bug: even *with* listing URLs, if all
listing fetches failed, the old `if best_listing is None: ... elif reuse_matches: ...` branch
order meant a genuine reuse match still lost to the "listing images could not be fetched"
branch. Fixed: the reuse scan now always runs (`backend/app/analyzers/l5_context.py`), and
reuse matches take priority in the scoring branches regardless of listing status. Verified via
2 new regression tests (`test_context_analyzer.py`) and live — case 3 in the demo output below
shows a claim submitted with **no listing URLs** correctly flagged
(`l5_context: 0.92, "claim image closely matches a previously stored claim photo"`).

**2. `L5_EMBEDDING_ENABLED` defaulted to `true`, unlike every other optional signal in this
codebase (L1's HF ensemble, L1's local checkpoint, L2's TruFor, L3's Sightengine all default
to off/stub until explicitly configured).** First use of the embedding path triggers a real
network download of the CLIP model weights — on a slow/offline connection this can hang
indefinitely. Found two ways, live: the full backend test suite went from its normal ~20s to
**431 seconds (7m 11s)** because end-to-end pipeline tests use real (non-mocked) settings and
hit this by default; separately, a demo run against a fresh backend hung and hit an
`httpx.ReadTimeout` after 120s waiting on the same download. Fixed: default changed to
`false` (`backend/app/config.py`, `.env.example`), matching the rest of the codebase's
opt-in-only convention for anything that touches the network or a heavy model on first use.
Re-verified: full suite back to 20s, demo run completes cleanly with no hang.

**3. The embedding call was a blocking synchronous call made directly inside `async def
_run()`, unlike L2's TruFor subprocess call which already correctly uses
`asyncio.to_thread`.** This meant even with the setting explicitly turned on, a slow or
stalled embedding computation (network download or just CPU-bound torch/PIL work) would block
the **entire event loop** — every concurrent request to the server, not just the one being
processed — for its duration. This is exactly what turned bug #2's hang into "the whole demo
run stalled," not just "one slow request." Fixed: `_blended_similarity` and the initial
`_embed(image, ...)` call now run via `asyncio.to_thread(...)`, matching the L2 pattern.

**Also found and fixed in passing:** the demo script's own output was garbled on this
Windows environment's default console codepage (em-dashes and section signs printed as `�`).
Fixed by forcing `sys.stdout.reconfigure(encoding="utf-8")`.

**Verified:** full suite **56/56** (was 55; +1 from the new reuse-without-listing-URLs
regression test), full `ml/` suite **8/8**, three live end-to-end runs against a real backend
via `scripts/demo.py` (the last one clean: no hang, correct UTF-8 output, correct reuse-flag
behavior with no listing URLs supplied) — plus manual cleanup of every temp DB/artifact-dir/
process this pass spun up.

## 2026-07-10 — real migration framework (Alembic), replacing the runtime column-patcher

Backend-only pass, no model training, no frontend — following up directly on the "real
migration framework" gap this doc flagged in the previous entry (`_add_missing_columns` was
explicitly documented as "not a substitute for Alembic").

**What shipped:** `backend/alembic.ini` + `backend/alembic/` (env.py, script.py.mako,
`versions/0001_baseline_schema.py`). `init_db()` now runs `alembic upgrade head`
programmatically instead of `Base.metadata.create_all()` + the ad-hoc `_add_missing_columns`
helper (removed — its logic now lives inside the baseline migration instead of as permanent
runtime code). The baseline migration is deliberately idempotent
(`create_all(checkfirst=True)` + a missing-column backfill), so it can adopt Alembic on a DB
in *any* prior state — brand new, fully current, or drifted like the one from the previous
entry — without forcing anyone to drop and recreate their local DB. Verified via the CLI
directly (`alembic upgrade head` / `alembic current` → `0001 (head)`) and by inspecting the
resulting SQLite file: every table and column matches the ORM models exactly, plus
`alembic_version`.

**A real bug found while building this, not a pre-existing one:** wiring `env.py` the
Alembic-generated-default way (calling `logging.config.fileConfig(config.config_file_name)`)
broke three unrelated tests (`test_observability.py` — `StopIteration` hunting for log
events that were demonstrably still being emitted, visible in captured stderr, but no longer
captured by pytest's `caplog`). Root cause: `fileConfig()` reconfigures the **root logger's
handler list** — since `init_db()` runs Alembic on every app startup, not just standalone CLI
invocations, this silently stripped whatever handler the app (or `caplog`) had already
installed on root. `disable_existing_loggers=False` does not fix this — the handler-list
reset happens regardless of that flag. Fixed by not calling `fileConfig()` at all; Alembic's
own loggers work fine without it (they just propagate to root and use whatever handler is
already there — confirmed still visible in stderr output after the fix).

**Verified:** `test_db_migration.py` (3 tests: backfills a deliberately-stale table, is a
no-op on an already-current DB, and stamps `alembic_version` at `0001` so re-runs are a cheap
version check rather than re-running the whole baseline) + a real CLI run + full suite.
**63/63 passing (55 backend, 8 ml)** — 4 tests failed transiently while chasing the logging
bug above, all now pass; nothing was skipped or weakened to get there.

**Not done / explicitly out of scope this pass:** no second real migration was written (the
baseline is the only one — there's nothing else to migrate yet); L5 v2 (Qdrant, reverse-image
search) untouched; dashboard/webapp untouched per this pass's scope (backend only).

## 2026-07-09 — dashboard auth header + a real bug found via live browser verification

**Dashboard `X-API-Key` support (the documented gap from the previous entry).**
`dashboard/app/api.ts` now sends `X-API-Key: <NEXT_PUBLIC_API_KEY>` on every request when
that env var is set (added `dashboard/.env.local.example`); still a no-op when unset, so the
default `API_AUTH_ENABLED=false` local-dev path is unaffected. `dashboard/README.md` updated
accordingly. Not yet re-verified against a live `API_AUTH_ENABLED=true` backend — only the
unset/default path was exercised live (see below).

**Bug found while verifying that change live, unrelated to it: `claims.tenant_id` missing
from an existing SQLite DB → every `GET /v1/claims` (and other tenant-scoped queries) 500'd.**
Booted backend + dashboard fresh in this session's own tracked preview servers (not reusing
the prior session's untracked process) specifically to verify the auth header change didn't
regress the default path, per this harness's verification requirement for browser-observable
changes. The dashboard queue loaded, but every claims request failed
(`net::ERR_FAILED` in the browser; `sqlite3.OperationalError: no such column: claims.tenant_id`
in the backend log). Root cause: `init_db()` (`backend/app/storage/repository.py`) only ever
called `Base.metadata.create_all()`, which creates missing **tables** but never alters
**existing** ones — so any `truthpixel.db` file created before the `tenant_id` column was
added (i.e., before the auth/tenant feature landed) is permanently broken until someone
manually deletes the file. This project has no migration framework (no Alembic), so this
wasn't a one-off — it would hit anyone upgrading with an existing local DB, silently and
permanently, which is a much bigger deal than the dashboard auth gap I was actually verifying.

Fixed: `init_db()` now also runs `_add_missing_columns(engine)` — inspects each table
SQLAlchemy's models define, and for tables that already exist, `ALTER TABLE ... ADD COLUMN`
for anything the model has that the on-disk table doesn't. Safe no-op on an already-current
DB or a brand-new one (create_all already gave those tables every column). Not a substitute
for Alembic — this only handles "add a nullable column," not renames/drops/backfills/type
changes — but it's what this project needs today, and flags the real gap (no migration
framework) for later.

**Verified, not just asserted:** wrote `test_db_migration.py` (2 new tests — one creates a
deliberately stale `claims` table missing several columns including `tenant_id` and confirms
`init_db()` self-heals it and the previously-failing query now succeeds; one confirms
`init_db()` run twice on an already-current DB doesn't raise). Then, live: restarted this
session's backend preview server (safe — it was started by me this session, unlike the
untracked PID 22760 from the previous entry, which I still haven't touched), reloaded the
dashboard, and confirmed via `preview_network` that `GET /v1/claims` went from
`net::ERR_FAILED`/500 to a sustained run of clean `200 OK`s (the dashboard's 8s auto-refresh
polling kept confirming it), and via `preview_snapshot` that the queue page renders correctly
("0 claims loaded", no error banner — correct for a fresh migrated DB with no claims in it
yet). Full suite: **51/51 backend, 8/8 ml** passing.

**Not verified:** the positive auth path (`API_AUTH_ENABLED=true` + a real issued tenant key
+ `NEXT_PUBLIC_API_KEY` set) — would need creating a tenant and API key via the admin
endpoints first; only the default/unset path was exercised live this pass.

## 2026-07-09 — L5 v1: frozen-CLIP embedding similarity (excludes model training)

Scoped explicitly to **not** train any model — L1's own-checkpoint upgrade stays out of
scope (still tracked in ROADMAP.md, blocked on an actual training run). Everything below is
pretrained-model inference only.

**What shipped:** `backend/app/embeddings.py` — loads a frozen, pretrained CLIP encoder
(default `ViT-B-32`/`openai`, reusing `ml/layer1_aigen/model.py::load_open_clip_encoder`, the
same loader L1's local-checkpoint mode uses) and computes an L2-normalized image embedding.
`l5_context.py` now blends this embedding's cosine similarity with the existing v0
perceptual-hash + color-histogram score (configurable weight, `L5_EMBEDDING_WEIGHT`, default
0.5) for both the listing-photo comparison and the intra-system reused-photo scan. This is
the L5 v1 line item from ROADMAP.md/ML_PLAN.md — previously described as DINOv2/Qdrant target
work, delivered here as the CLIP-embedding half (Qdrant ANN indexing is now scoped as v2,
since it's a scaling concern — the current linear scan is fine at today's claim volume).

**Design choices, and why:**
- **Blend, don't replace.** Swapping v0's thresholds (`LISTING_MATCH_THRESHOLD=0.82`, etc.)
  for a raw CLIP cosine score would need real threshold recalibration against labeled
  same-product/different-product pairs, which don't exist yet (same blocker as learned
  fusion). Blending keeps the existing, already-reasoned-about thresholds valid while still
  letting the embedding signal move the score — consistent with the rest of this codebase's
  philosophy of fusing independent signals rather than betting on one.
- **Graceful degradation is mandatory, not optional.** `EmbeddingUnavailable` is caught at
  every call site; if `torch`/`open_clip_torch` are missing or the model fails to load, L5
  silently falls back to v0-only (`method: "hash+histogram-only"` in evidence) — L5 must
  never fail a claim over an optional accuracy upgrade. Same pattern L1's HF-ensemble
  fallback and fusion's learned-model fallback already use.
- **`ViT-B-32`, not L1's `ViT-L-14`.** Similarity doesn't need the bigger model; cheaper CPU
  inference matters more for a signal computed against up to `L5_RECENT_CLAIM_WINDOW` (40 by
  default) prior claims per request on the synchronous endpoint.
- **Evidence transparency.** Every comparison now records which `method` produced its score
  (`hash+embedding` vs `hash+histogram-only`) and whether an embedding was available at all —
  so a reviewer or a later debugging session can tell whether the upgrade actually engaged for
  a given claim, not just that it's configured.

**Tests:** `test_embeddings.py` (pure-math cosine-similarity edge cases — identical, orthogonal,
opposite, mismatched-dimension, zero-vector), `test_context_analyzer.py` (two new cases: blend
math with deterministic mocked vectors — weight=1.0 isolates the embedding term so the exact
resulting score is asserted rather than just "changed somehow" — and the `EmbeddingUnavailable`
fallback path). Full suite: **49/49 backend, 8/8 ml** passing.

**Not yet verified — and now confirmed stalled, not just slow.** A real (non-mocked)
end-to-end run of `embed_image_bytes` was started to confirm the model genuinely downloads
and runs in this environment beyond unit-test mocks. The `ViT-B-32`/`openai` weight download
reached 134MB (`~/.cache/huggingface/hub/models--timm--vit_base_patch32_clip_224.openai/blobs/*.incomplete`)
and then stopped growing entirely — file size and mtime unchanged across multiple checks
spanning ~15+ minutes, while the process itself kept accumulating CPU time (consistent with a
retry/backoff loop, not a hang). Read as: this sandbox's network is rate-limited or cuts off
long-lived transfers, not that the code is broken. **Treat the embedding path as
code-complete and unit-tested (all mocked tests pass), but not yet confirmed against real
downloaded weights in this specific environment.** Verify in an environment with normal
network access before depending on `L5_EMBEDDING_ENABLED=true` in anything beyond local dev
with a pre-warmed model cache.

**What was intentionally left alone:** L1's own-model training (explicitly excluded this
pass), Qdrant integration (scoped as v2 — no reason to add a hard infra dependency before
volume requires it), and any threshold retuning (needs labeled data, tracked with learned
fusion's same blocker).

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
| L5 (context, v0+v1) | Perceptual-hash + color-histogram similarity, blended with a frozen-CLIP embedding cosine similarity (zero-training, off by default — opt-in, non-blocking via `asyncio.to_thread`); intra-system reused-photo detection that runs independent of listing URLs | `context_checks.py`, `embeddings.py`, `l5_context.py`, `test_context_analyzer.py`, `test_embeddings.py` |
| Demo harness | `scripts/demo.py` — submits curated claim images to a live backend, prints the fused report; 2/5 cases reproducible with no external images | `scripts/demo.py`, verified live 3x against a real backend |
| Fusion (weighted) | Confidence-weighted average + screenshot-evasion combo rule — the default, always-available path | `fusion/engine.py::_weighted_fuse` |
| Fusion (learned) | Runtime scorer + training/export tooling, wired but **not populated** (no labeled data yet) | `fusion/learned.py`, `ml/fusion/`, `test_fusion_engine.py` |
| Agents | Gemini-on-Vertex semantic inspector / damage plausibility / report writer, cost-gated, stub fallback | `agents/`, `graph/build.py` |
| Public webapp | Upload → fused report UI, thin client | `webapp/`, verified booting |
| Reviewer dashboard | Queue, claim detail, heatmap overlay w/ opacity slider, decision form, audit trail, `X-API-Key` auth header (opt-in) | `dashboard/`, verified end-to-end against a live backend |
| DB migrations | Real Alembic framework; `init_db()` runs `upgrade head` on every startup (fast no-op once current); idempotent baseline migration self-heals a drifted DB instead of 500ing forever | `backend/alembic/`, `test_db_migration.py`, verified via CLI + full suite |

### Remaining (genuinely not done — not just "unconfigured")

| Area | What's missing | Blocker |
|---|---|---|
| L1 own model | No trained CLIP-head checkpoint | Needs a training run — plan exists in `COLAB_TRAINING.md`, not executed |
| L1 HF ensemble live use | Needs `HF_API_TOKEN` set to actually call the API | Just needs a token — no code work left |
| L2 real inference | TruFor code is correct but unrunnable here | Needs the upstream Python 3.7 / torch 1.11 / `mmcv-full` / `yacs` env — not installed |
| L5 v2 | Qdrant ANN search, external reverse-image search (TinEye/SerpAPI) | Not started — v1 (CLIP-embedding blend, 2026-07-09) is the current ceiling. Deliberately did NOT implement TinEye/SerpAPI this pass: TinEye's real API needs correct HMAC request-signing I can't verify without live credentials, and SerpAPI's reverse-image engines need a *publicly fetchable* image URL, which this system's private artifact storage doesn't provide yet — shipping either as "done" without a way to confirm it actually works against the real service would violate this project's own honesty standard. Qdrant only matters once claim volume outgrows a linear scan |
| Learned fusion in production | No `FUSION_MODEL_PATH` populated | No labeled claims data yet — tooling is ready and waiting |
| Vertex agents live | Template-fallback report/agent text only | Needs `GOOGLE_CLOUD_PROJECT` + real credentials |
| Async queue in production | Needs a real Celery worker + Redis process | Works today only via `CELERY_TASK_ALWAYS_EAGER=true` (dev shortcut) |
| Dashboard auth positive path | `X-API-Key` header support shipped 2026-07-09 but not exercised against a live `API_AUTH_ENABLED=true` backend | Needs a tenant + issued key created via the admin endpoints, then a live check |
| Demo script — full 5 cases | `scripts/demo.py` exists and runs 2/5 cases (screenshot_of_ai, reused_photo) reproducibly; real_damage/ai_fake/inpainted need real source images | Needs someone to actually source a real damage photo, an AI-generated image, and a manipulated image (see script's own printed guidance) — not a code gap |
| Reviewer dashboard hardening | Tenant switcher, production UX polish | Scaffold works, not production-ready |

**Bottom line:** every one of the five signal layers has a real, working implementation path
today — three (L3, L4, L5-v0) run for free with no external setup, one (L1) runs for free with
an HF token, and one (L2) is fully correct code blocked purely on a heavy upstream Python
environment. Nothing is fake/mocked; everything that's a "stub" is a stub because it's
*unconfigured*, and degrades there deliberately and safely (error isolation, never crashes a
claim). The gap between "demo-ready" and "field-accurate" is data (labeled claims, a trained
L1 head) and infrastructure (a TruFor-capable Python env, Vertex credentials), not missing code.
