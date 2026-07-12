# TruthPixel Docs Index

This folder has two main layers:

1. Existing project-planning docs
2. Reference docs for understanding the codebase, runtime, and ML stack

If you are new to the project, start here before jumping straight into code.

## Start here

1. [PROJECT_GUIDE.md](PROJECT_GUIDE.md)
2. [ML_OVERVIEW.md](ML_OVERVIEW.md)
3. [DATAFLOW.md](DATAFLOW.md)
4. [CODEBASE_MAP.md](CODEBASE_MAP.md)
5. [BENCHMARK.md](BENCHMARK.md)

## Core product docs

- [ARCHITECTURE.md](ARCHITECTURE.md): high-level system design and product thinking
- [ROADMAP.md](ROADMAP.md): what is built and what still remains
- [EXECUTION_PLAN.md](EXECUTION_PLAN.md): current work order
- [USE_CASES.md](USE_CASES.md): surfaces and user types
- [ML_PLAN.md](ML_PLAN.md): ML strategy and training direction
- [BENCHMARK.md](BENCHMARK.md): measured results from the current trained model artifacts
- [AGENTS.md](AGENTS.md): agent layer strategy
- [CORRECTIONS.md](CORRECTIONS.md): audit log of real bugs and reality checks

## Module references

- [modules/backend-api.md](modules/backend-api.md)
- [modules/backend-pipeline.md](modules/backend-pipeline.md)
- [modules/backend-signals.md](modules/backend-signals.md)
- [modules/backend-agents-fusion.md](modules/backend-agents-fusion.md)
- [modules/backend-storage-auth.md](modules/backend-storage-auth.md)
- [modules/ml-layer1.md](modules/ml-layer1.md)
- [modules/ml-fusion.md](modules/ml-fusion.md)
- [modules/frontend-surfaces.md](modules/frontend-surfaces.md)
- [modules/testing-dev-workflow.md](modules/testing-dev-workflow.md)

## Recommended reading order by goal

If you want to understand the whole product:

1. [PROJECT_GUIDE.md](PROJECT_GUIDE.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [DATAFLOW.md](DATAFLOW.md)
4. [CODEBASE_MAP.md](CODEBASE_MAP.md)
5. [ROADMAP.md](ROADMAP.md)

If you want to understand the ML parts:

1. [ML_OVERVIEW.md](ML_OVERVIEW.md)
2. [modules/ml-layer1.md](modules/ml-layer1.md)
3. [modules/ml-fusion.md](modules/ml-fusion.md)
4. [ML_PLAN.md](ML_PLAN.md)
5. [BENCHMARK.md](BENCHMARK.md)

If you want to understand the backend:

1. [modules/backend-api.md](modules/backend-api.md)
2. [modules/backend-pipeline.md](modules/backend-pipeline.md)
3. [modules/backend-signals.md](modules/backend-signals.md)
4. [modules/backend-storage-auth.md](modules/backend-storage-auth.md)

If you want to work on frontend:

1. [modules/frontend-surfaces.md](modules/frontend-surfaces.md)
2. [USE_CASES.md](USE_CASES.md)
3. [ROADMAP.md](ROADMAP.md)

## Why these docs exist

TruthPixel already had planning and architecture docs, but it needed a clearer set of system
references for the runtime, ML stack, and module layout. These files are meant to answer
questions like:

- What problem is this project solving?
- What happens when an image is uploaded?
- Which parts are ML, which parts are product, and which are infrastructure?
- What does each folder do?
- What should I read first before changing code?
- What is already real vs still planned?
