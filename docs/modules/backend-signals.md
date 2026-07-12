# Backend Signals Module

## What this module is

Signals are the core evidence-producing layers of TruthPixel.

Main folder:

- `backend/app/analyzers/`

These analyzers answer different questions about the same uploaded image.

## Why there are five layers

One model alone can fail in many ways.

TruthPixel uses five layers because image fraud can show up in different forms:

- synthetic generation
- direct editing
- screenshot/recapture tricks
- metadata problems
- mismatch with expected product context

## Common signal contract

Every analyzer returns `SignalResult`.

That includes:

- `layer`
- `score`
- `confidence`
- `evidence`
- `error`
- `model_version`

This consistency is very important.

It means fusion does not care how each detector works internally. It only needs the shared
output shape.

## Base analyzer

File:

- `backend/app/analyzers/base.py`

Main role:

- guarantee error isolation

Important rule:

- analyzers should not crash the whole claim

If an analyzer fails, the system should still return the other signals.

## L1: AI-generation detection

File:

- `backend/app/analyzers/l1_aigen.py`

Question it answers:

- does the image look AI-generated?

Runtime precedence:

1. local trained checkpoint
2. HF inference ensemble
3. safe fallback

This is a good example of production ML realism:

- one layer can have more than one runtime mode
- local trained model is not the only possible path

## L2: Manipulation / edit forensics

File:

- `backend/app/analyzers/l2_forensics.py`

Question it answers:

- does the image look edited, spliced, inpainted, or manipulated?

Current runtime precedence:

1. TruFor when configured
2. classical CPU fallback

Classical fallback logic lives in:

- `backend/app/forensics_classic.py`

This is important because it means L2 now contributes real evidence even when the heavy
TruFor stack is unavailable.

## L3: Recapture / screenshot detection

File:

- `backend/app/analyzers/l3_recapture.py`

Question it answers:

- is this a screenshot or photo-of-screen rather than a direct original photo?

This layer is especially important because screenshotting is a real evasion pattern.

## L4: Metadata and provenance

File:

- `backend/app/analyzers/l4_metadata.py`

Question it answers:

- what does metadata or provenance tell us?

Examples:

- EXIF presence
- content credential/provenance checks

Important logic rule:

- missing metadata is not proof by itself

This keeps the product from overreacting to common benign cases like reshares.

## L5: Context cross-check

File:

- `backend/app/analyzers/l5_context.py`

Helper files:

- `backend/app/context_checks.py`
- `backend/app/embeddings.py`

Question it answers:

- does the uploaded image match the expected product/listing context?

This is one of the product’s biggest differentiators.

Unlike generic AI detectors, this layer uses domain context.

## Supporting signal modules

### `context_checks.py`

Contains:

- perceptual hash logic
- histogram-based similarity logic
- recent-claim comparison helpers

### `embeddings.py`

Contains:

- frozen CLIP embedding similarity support

This makes L5 stronger without requiring immediate new model training.

### `hf_inference.py`

Contains:

- Hugging Face inference-API ensemble path used by L1

### `trufor.py`

Contains:

- TruFor runtime integration
- heatmap rendering helpers

## Why signal diversity matters

Different layers fail differently.

Examples:

- AI-gen detector may miss some edited real images
- forensics may weaken after recompression
- metadata may be absent for honest reasons
- context may be missing on public uploads

Fusion exists precisely because no single layer is enough.

## Best way to study these modules

Read in this order:

1. `base.py`
2. `__init__.py`
3. `l1_aigen.py`
4. `l2_forensics.py`
5. `l3_recapture.py`
6. `l4_metadata.py`
7. `l5_context.py`

Then inspect helpers like:

- `hf_inference.py`
- `forensics_classic.py`
- `context_checks.py`
- `embeddings.py`

This order helps because it starts with the common contract, then moves from layer to layer.
