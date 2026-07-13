# Codebase Map

This is the repo map for TruthPixel. Use it when you want to know what each folder and major
module is responsible for.

## Top-level structure

```text
TruthPixel/
  backend/    runtime API, pipeline, storage, auth, jobs
  dashboard/  reviewer UI
  webapp/     public self-serve UI
  ml/         training, datasets, feature extraction, export artifacts
  docs/       product, architecture, benchmark, and module references
  scripts/    helper scripts and demos
```

## Backend modules

### `backend/app/main.py`

Purpose:

- API entrypoint
- request validation
- route definitions
- HTTP contract

Read this when:

- you want to know what the backend exposes
- you want to change endpoints
- you want to trace request flow

### `backend/app/config.py`

Purpose:

- central environment and config source of truth

Read this when:

- you want to know which env var controls something
- runtime and docs disagree
- a feature seems disabled unexpectedly

### `backend/app/auth.py`

Purpose:

- tenant API keys
- public submission gating
- Supabase-backed public-user rate path
- admin token checks

Read this when:

- auth behavior is confusing
- public uploads fail
- you need to understand rate limiting

### `backend/app/graph/`

Purpose:

- orchestrator for the whole claim-analysis pipeline

Main file:

- `build.py`

Read this when:

- you want to understand the main runtime flow

### `backend/app/analyzers/`

Purpose:

- L1-L5 signal layers

Files:

- `base.py`: common analyzer contract
- `l1_aigen.py`: AI-generation scoring
- `l2_forensics.py`: manipulation and edit forensics
- `l3_recapture.py`: screenshot and recapture checks
- `l4_metadata.py`: EXIF and provenance checks
- `l5_context.py`: product, listing, and recent-claim context checks

Read this when:

- you want to improve detection signals
- you want to understand evidence generation

### `backend/app/agents/`

Purpose:

- Gemini-based reasoning helpers

Files:

- `semantic_inspector.py`
- `damage_plausibility.py`
- `report_writer.py`
- `llm.py`

Read this when:

- you want to understand the agent pass
- you want to tune semantic and report behavior

### `backend/app/fusion/`

Purpose:

- combine signals into the final decision

Files:

- `engine.py`: runtime fusion logic
- `learned.py`: learned-fusion artifact loader and runtime scorer

Read this when:

- you want to understand the final risk score

### `backend/app/storage/`

Purpose:

- persistence layer

Files:

- `models.py`: SQLAlchemy schema
- `repository.py`: read and write operations

Read this when:

- you want to understand database behavior
- you need to add or change stored fields

### `backend/app/artifacts.py`

Purpose:

- binary artifact storage abstraction

Examples:

- original images
- heatmap images

### `backend/app/signal_artifacts.py`

Purpose:

- converts runtime signal outputs into persisted downloadable artifacts

### `backend/app/jobs.py`

Purpose:

- async claim processing
- Celery task enqueueing
- webhook dispatch

### `backend/app/observability.py`

Purpose:

- trace IDs
- structured logging
- usage accounting helpers

## ML modules

### `ml/layer1_aigen/`

Purpose:

- train and evaluate the L1 AI-generation model

Files:

- `dataset.py`
- `augment.py`
- `model.py`
- `train.py`
- `eval.py`

### `ml/fusion/`

Purpose:

- train a learned fusion meta-model from labeled claims

Files:

- `features.py`
- `train_meta.py`

### `ml/tests/`

Purpose:

- verify training helpers and exported artifact logic

## Frontend modules

### `webapp/`

Purpose:

- public self-serve upload and report surface

Important point:

- it should stay thin
- it must not contain model logic

### `dashboard/`

Purpose:

- reviewer-facing internal queue, detail, and decision UI

Important point:

- it is a workflow surface on top of stored claims

## Docs modules

### Core docs

- `ARCHITECTURE.md`
- `ROADMAP.md`
- `EXECUTION_PLAN.md`
- `ML_PLAN.md`
- `BENCHMARK.md`
- `USE_CASES.md`
- `AGENTS.md`
- `CORRECTIONS.md`

### Reference docs

- `README.md`
- `PROJECT_GUIDE.md`
- `ML_OVERVIEW.md`
- `DATAFLOW.md`
- `CODEBASE_MAP.md`
- `modules/`

## Best doc for each question

| Question | Best doc |
|---|---|
| What does the product do? | `USE_CASES.md` |
| What is the big-picture design? | `ARCHITECTURE.md` |
| What is already built? | `ROADMAP.md` |
| What are the measured model results? | `BENCHMARK.md` |
| What happens during one request? | `DATAFLOW.md` |
| What does each folder do? | `CODEBASE_MAP.md` |
| What is the recommended reading order? | `PROJECT_GUIDE.md` |
| How does the ML side work? | `ML_OVERVIEW.md` |
