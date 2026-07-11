# Execution Plan — Post-Reconciliation

> This file tracks the next repo-facing slices after the mainline reconciliation pass.

## What just landed

- reviewer dashboard hardening on top of tenant-protected backend routes
- public webapp productization and backend-shape cleanup
- labeled reviewer feedback export endpoints
- test-session env isolation from local `backend/.env`

## What is still branch-only

These areas exist on `codex/*` branches but were intentionally not promoted in this pass because
they are broader, stacked, or need separate verification:

- observability / tracing / CI-deploy chain
- classical L2 fallback and adjacent evaluation/datagen branches
- batch claims API and later fusion-training branches

## Next recommended slices

### Track A — Runtime proof

1. Verify the dashboard against a live `API_AUTH_ENABLED=true` backend with a real issued tenant key.
2. Re-run the public webapp end to end against the reconciled backend and record evidence in docs.
3. Confirm the new feedback export endpoints against representative reviewed claims.

### Track B — Training loop

1. Define the first training-ready export contract from `/v1/labels/export` and `/v1/admin/labels/export.csv`.
2. Connect exported labels to the learned-fusion tooling in `ml/fusion/`.
3. Only after that, promote any broader fusion-training branch.

### Track C — Larger branch promotion

1. Review observability/tracing as its own promotion candidate.
2. Review classical L2 fallback as its own promotion candidate.
3. Review batch intake as its own promotion candidate.

Promotion rule: do not merge stacked `codex/*` work just because it exists; each slice needs its
own scope check, docs update, and verification.
