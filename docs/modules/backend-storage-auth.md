# Backend Storage and Auth Module

## What this module is

This part of the system handles:

- who is allowed to call the system
- how claims are stored
- how artifacts are stored
- how audit and usage data are recorded

Main files:

- `backend/app/auth.py`
- `backend/app/storage/repository.py`
- `backend/app/storage/models.py`
- `backend/app/artifacts.py`
- `backend/app/signal_artifacts.py`
- `backend/app/jobs.py`

## Why this matters in an ML product

It is easy to think ML projects are only about models.

But in real products, storage and auth matter a lot because you need:

- auditability
- reproducibility
- multi-user safety
- artifact access
- future training labels

TruthPixel is a product system, not only a notebook.

## Auth model

### Tenant API keys

Used for:

- B2B integrations
- dashboard reviewer access path

Important concepts:

- each tenant has keys
- keys are hashed in storage
- rate limits are enforced

### Admin token

Used for:

- tenant creation
- API key issuance
- admin usage views

### Public submission path

Used for:

- public webapp

Modes:

- anonymous public submission
- signed-in public user via Supabase bearer token

## Rate limiting

Rate limiting protects:

- tenant API traffic
- anonymous public traffic
- signed-in public traffic

This is a product and operations feature, not just a security feature.

It prevents abuse and controls cost.

## Storage layers

TruthPixel has two kinds of storage.

### Relational data

Stored in DB:

- claims
- artifacts metadata
- audit events
- tenants
- API keys
- rate-limit events
- usage summaries

### Binary files

Stored in artifact backend:

- original uploads
- heatmaps

These can live on:

- local disk
- S3-compatible storage

## Repository layer

Main file:

- `backend/app/storage/repository.py`

This is the main data access layer.

It contains operations like:

- create pending claim
- create processing claim
- update completed claim
- list claims
- record reviewer decision
- add artifact
- get audit events
- usage summary aggregation

This file is large because it centralizes persistence behavior.

## Why a repository layer is useful

Instead of scattering DB calls across route files and analyzers, the project centralizes them.

Benefits:

- easier to reason about
- easier to test
- easier to change schema behavior safely

## Artifact flow

Artifacts are stored in two steps:

1. raw bytes go into artifact storage backend
2. metadata goes into relational DB

This is important because the system needs both:

- downloadable files
- queryable metadata

## Heatmap persistence

This happens through:

- `signal_artifacts.py`

Why it exists:

- analyzers can generate runtime-only internal artifact bytes
- this helper converts them into stored downloadable artifacts

This keeps analyzer code cleaner.

## Async jobs

File:

- `backend/app/jobs.py`

Purpose:

- process async claims in background
- recover stored original artifact
- run the same pipeline
- persist results
- optionally dispatch webhook

This is important because enterprise usage often wants non-blocking processing.

## Alembic migrations

Schema evolution is handled through Alembic.

This matters because:

- schema changes happen over time
- `create_all()` alone is not enough for real evolution
- production databases need controlled migrations

When navigating the project, remember:

- runtime DB use lives in repository/models
- schema change history lives in Alembic

## Most important system insight

Storage and auth are not side details.

They are part of what makes TruthPixel a real product rather than only an ML experiment.

Without them, you would not have:

- reviewer decisions
- audit trails
- claim histories
- safe multi-tenant usage
- reliable async workflows
