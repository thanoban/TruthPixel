# Corrections — full-system audit log

> Running log of full-system checks: what was verified, what was found broken and fixed, and
> an honest finished-vs-remaining snapshot. This is an audit trail, not a plan.

## 2026-07-11 — reconciliation pass: docs drift removed, narrow verified slices promoted

This pass reconciles `origin/main` with already-built focused `codex/*` branches without
promoting broader unfinished work as complete.

### Landed in this pass

- **Reviewer dashboard hardening**
  Queue/detail flow now includes reviewer-context proxying, clearer queue-state/status
  visibility, stronger decision UX, artifact open-in-new-tab fallbacks, and auth-proxy support
  for tenant-protected backend routes.
- **Public webapp productization**
  The webapp now matches the current backend response shape, renders artifact previews/links
  cleanly, adds retention/privacy/risk-disclaimer copy, and explicitly calls out the anonymous
  public path versus the future API-key upgrade path.
- **Labeled reviewer feedback export**
  Added tenant/admin endpoints to export reviewed claims as JSON or CSV plus summary counts,
  giving the backend a real label-export surface for future retraining workflows.
- **Test-session env isolation**
  Root `conftest.py` now forces stub-safe defaults for external/runtime settings and clears key
  caches so the test suite no longer depends on local `backend/.env` values.

### Branch-only work intentionally not promoted here

The following areas remain branch-only and are **not** treated as landed in this reconciliation:

- observability/tracing and cost-counter work
- classical L2 fallback and related evaluation branches
- batch claims API
- larger deployment/migration/runtime hardening stacks

### Verification target for this pass

- run `pytest -c pytest.ini -q`
- keep the reconciliation scoped to the landed slices above plus the matching docs refresh

## 2026-07-08 — full-system audit

### Bug found and fixed

**`FUSION_MODEL_PATH` silently ignored when set only in `.env`.**
`backend/app/fusion/engine.py` read the learned-fusion model path via `os.getenv("FUSION_MODEL_PATH")`
instead of through the app's `Settings` class. Every other config value in the app loads from
`.env` via `pydantic-settings`, which does not mutate `os.environ` as a side effect, so a value
set only in `.env` was invisible to `os.getenv(...)`.

Fixed:
- Added `fusion_model_path` to `Settings`
- `engine.py` now reads `settings.fusion_model_path`
- Fallback logging now emits a warning instead of silently swallowing the failure

### Snapshot after that audit

Finished then:
- core sync/async claim API
- persistence, artifacts, audit log, and reviewer decisions
- tenant/admin auth hooks and rate limits
- L1 local-checkpoint/HF paths
- L2 TruFor adapter with heatmap persistence
- L3/L4/L5 v0 live paths
- fusion runtime and learned-fusion tooling scaffold
- public webapp scaffold
- reviewer dashboard scaffold

Still missing then:
- trained own-model L1 artifact
- live Vertex verification
- broader deployment/runtime proof
- production-ready reviewer/dashboard auth flow
