# Backend API Module

## What this module is

The backend API is the HTTP front door of TruthPixel.

Main file:

- `backend/app/main.py`

Its job is not to do the heavy ML work itself. Its job is to:

- accept requests
- validate them
- call the pipeline
- store outputs
- return structured responses

## Main responsibilities

### 1. Define routes

Examples:

- `POST /v1/claims`
- `POST /v1/claims/async`
- `GET /v1/claims`
- `GET /v1/claims/{claim_id}`
- `GET /v1/claims/{claim_id}/status`
- `POST /v1/claims/{claim_id}/decision`
- `GET /v1/claims/{claim_id}/audit`
- `GET /v1/claims/{claim_id}/artifacts/{artifact_id}`

### 2. Validate inputs

Examples:

- check content type
- check file size
- check empty uploads

### 3. Build runtime context

The API turns form fields into a `ClaimContext`.

This keeps the pipeline code cleaner, because downstream modules receive one normalized object.

### 4. Persist initial and final state

The API does not only return responses. It also:

- stores original artifacts
- creates or updates claim rows
- persists signal artifacts such as heatmaps

### 5. Enforce auth rules

The routes use dependencies from `auth.py`.

That means route code stays mostly focused on business flow.

## Sync vs async

### Sync path

`POST /v1/claims`

Use when:

- you want the full result in one request

Flow:

1. validate request
2. store image
3. run pipeline immediately
4. return `StoredClaim`

### Async path

`POST /v1/claims/async`

Use when:

- you want background processing
- you want queue status first
- you want webhook/polling flow

Flow:

1. validate request
2. store image
3. enqueue Celery job
4. return `ClaimQueueStatus`

## Important schemas

Schemas live in:

- `backend/app/schemas.py`

Important models:

- `ClaimContext`
- `SignalResult`
- `FusionResult`
- `ClaimReport`
- `StoredClaim`
- `ClaimQueueStatus`
- `ClaimArtifact`
- `AuditEvent`

These schemas are very important because they are the contract between:

- backend logic
- frontend surfaces
- tests
- future training export logic

## Health endpoint

`GET /health`

This is a small but important route. It tells you whether:

- app is up
- Vertex path is configured
- L2 TruFor is configured/stub/partial
- queue runs eager or worker mode

This is useful for:

- debugging local env
- deployment checks
- determining which parts are "real" vs "fallback"

## Design principle

The API layer should be thin.

That means:

- no training code
- no frontend rendering logic
- no duplicate fusion logic
- no complicated ML decisions hardcoded into routes

The route should mostly coordinate modules, not become the system itself.

## Beginner reading checklist

When reading `main.py`, notice:

1. where auth dependencies are used
2. where artifact storage happens
3. where `run_claim()` is called
4. where persistence happens
5. where async flow differs from sync flow

If you understand those five things, you understand the backend API layer well.
