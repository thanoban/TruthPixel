# Project Guide

This guide gives a practical order for understanding TruthPixel from product surface to runtime
and ML internals.

## What TruthPixel is in one sentence

TruthPixel is a multi-signal image-integrity system. A user uploads an image, the backend runs
several detection layers, combines them into one risk score, and returns a reviewer-friendly
report.

## What kind of project this is

TruthPixel is not only:

- an ML project
- a backend API
- a dashboard
- a webapp

It is all of them together.

That means you need to understand four things:

1. Product goal
2. Data flow
3. Model logic
4. Runtime and infrastructure

## Recommended reading order

### Stage 1: Understand the product

Read:

1. [USE_CASES.md](USE_CASES.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [ROADMAP.md](ROADMAP.md)

This explains:

- who uses the product
- what gets uploaded
- what output the system returns
- what is already built
- what still remains

### Stage 2: Follow one request end to end

Read:

1. [DATAFLOW.md](DATAFLOW.md)
2. [modules/backend-api.md](modules/backend-api.md)
3. [modules/backend-pipeline.md](modules/backend-pipeline.md)

This explains:

- what happens at `POST /v1/claims`
- where the image bytes go
- how signals are produced
- how fusion decides the final risk score

### Stage 3: Understand the ML layers

Read:

1. [ML_OVERVIEW.md](ML_OVERVIEW.md)
2. [BENCHMARK.md](BENCHMARK.md)
3. [modules/backend-signals.md](modules/backend-signals.md)
4. [modules/ml-layer1.md](modules/ml-layer1.md)
5. [modules/ml-fusion.md](modules/ml-fusion.md)

This explains:

- what each signal layer does
- which parts are trained models
- which parts are pretrained integrations
- where training code lives
- how runtime inference differs from training

### Stage 4: Understand storage, auth, and operations

Read:

1. [modules/backend-storage-auth.md](modules/backend-storage-auth.md)
2. [modules/testing-dev-workflow.md](modules/testing-dev-workflow.md)

This explains:

- where claims are stored
- where artifacts are stored
- how tenants and API keys work
- how async jobs work
- how to test safely

### Stage 5: Understand the product surfaces

Read:

1. [modules/frontend-surfaces.md](modules/frontend-surfaces.md)

This explains:

- the difference between API, dashboard, and public webapp
- why frontend should stay thin
- where UI logic ends and backend truth begins

## Code reading order after the docs

Once the docs make sense, read code in this order:

1. `backend/app/main.py`
2. `backend/app/graph/build.py`
3. `backend/app/analyzers/`
4. `backend/app/fusion/engine.py`
5. `backend/app/storage/repository.py`
6. `ml/layer1_aigen/`
7. `ml/fusion/`

This order is useful because it follows the runtime path instead of folder order.

## Common confusion

### "Is every file ML?"

No.

Only some parts are ML:

- `backend/app/analyzers/l1_aigen.py`
- `backend/app/analyzers/l2_forensics.py`
- `backend/app/analyzers/l3_recapture.py`
- `backend/app/analyzers/l5_context.py`
- `ml/layer1_aigen/`
- `ml/fusion/`

Many other files are standard product and platform code:

- API routes
- auth
- storage
- queue
- artifact handling
- dashboard and frontend
- observability

### "What is the main model?"

There is no single main model.

TruthPixel is a fusion system. The real idea is:

- many signals
- one combined decision

That is why understanding fusion matters more than focusing on only one detector.

### "What is the most important file?"

If you only pick one runtime file, it is:

- `backend/app/graph/build.py`

That file shows the real execution shape:

- analyzers
- agent gating
- fusion
- report generation

## Questions to ask before changing the project

1. Is this a runtime feature, training feature, frontend feature, or docs feature?
2. Does it affect one layer or the whole pipeline?
3. Does it change request and response contracts?
4. Does it require new data, new config, or new infrastructure?

Then use the docs in this folder to locate the right module before editing code.
