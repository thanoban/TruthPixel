# ML Overview

This document explains the core ML ideas needed to understand TruthPixel as a production ML
system.

## 1. What makes an ML project different from a normal app?

A normal app usually follows fixed rules written by developers.

An ML project has two kinds of logic:

1. Deterministic software logic
2. Statistical model behavior

In TruthPixel, both exist together.

Examples of deterministic logic:

- FastAPI routes
- auth checks
- queue behavior
- database writes
- rate limits
- file storage

Examples of ML and statistical logic:

- AI-generated image detection
- edit and manipulation forensics
- screenshot and recapture detection
- similarity scoring
- learned fusion

## 2. The main ML idea in TruthPixel

TruthPixel does not trust one model alone.

Instead it uses a fusion approach:

1. Run multiple detectors
2. Normalize their outputs
3. Combine them into one final risk score

That is why the project is described as a multi-signal system.

## 3. Key ML concepts used in this repo

### Input

The image uploaded by the user.

Sometimes extra structured context is included too:

- order ID
- product SKU
- claim reason
- listing image URLs

### Feature

A feature is a measurable piece of information the model or system uses.

Examples in TruthPixel:

- L1 AI-gen score
- L2 forensic score
- L3 recapture score
- whether EXIF exists
- similarity to listing images
- agent semantic score

### Label

A label is the ground-truth answer used for training.

Examples:

- fraud or not fraud
- AI-generated or real
- needs reviewer escalation or does not need escalation

### Inference

Inference means using a model at runtime to score a new input.

In TruthPixel:

- backend analyzers do inference
- training code does not run during normal API use

### Training

Training means learning model parameters from labeled data.

In TruthPixel, training mainly applies to:

- L1 CLIP-head
- learned fusion model
- future recapture model

### Calibration

Calibration means the score should reflect reality reasonably well.

If the system says `0.85`, that should be meaningfully more risky than `0.55`.

TruthPixel cares about this because humans review the result. A badly calibrated score can
mislead operations teams.

## 4. What is trained vs. what is reused?

TruthPixel intentionally mixes:

- trained local models
- pretrained external models
- deterministic heuristics

This matters because many ML projects are not "train everything yourself."

### Trained locally

- L1 CLIP-head
- future learned fusion artifact

### Pretrained and external

- HF Inference API ensemble for L1 fallback
- TruFor for L2 when configured
- Sightengine recapture path
- Gemini and Vertex agents

### Deterministic and heuristic

- metadata checks
- hash and histogram similarity
- classical CPU forensics fallback

## 5. Why the project has both `backend/` and `ml/`

This is one of the most important distinctions in the repo.

### `backend/`

Runtime application code.

It answers questions like:

- how do we receive a request?
- how do we run inference?
- how do we store results?
- how do we return a report?

### `ml/`

Training and feature-engineering code.

It answers questions like:

- how do we prepare datasets?
- how do we train a model?
- how do we export a runtime artifact?
- how do we evaluate a trained model?

## 6. Why data matters more than code in many ML systems

You can have good training code and still get weak results if:

- labels are noisy
- data does not match production reality
- the train and test split is weak
- evaluation is dishonest

TruthPixel already has strong runtime structure, but some future quality improvements still
depend on better data:

- learned fusion needs labeled claims
- external splice benchmark work is still needed
- the future recapture model needs a dedicated dataset

## 7. Why evaluation matters

An ML project is not "done" just because it runs.

You also need to ask:

- does it generalize?
- does it fail safely?
- what is the real benchmark?
- what happens on unseen cases?

TruthPixel already tries to be honest here:

- held-out-generator thinking for L1
- planned external eval for classical L2
- calibrated fusion goal instead of vague "high accuracy"

The current measured L1 results are documented in [BENCHMARK.md](BENCHMARK.md).

## 8. Basic data flow in an ML product

```mermaid
flowchart LR
    A["Input Image"] --> B["Feature Extraction / Signal Layers"]
    B --> C["Fusion / Decision Layer"]
    C --> D["Human-Readable Output"]
    D --> E["Human Review / Feedback"]
    E --> F["Labeled Data"]
    F --> G["Model Retraining"]
    G --> B
```

TruthPixel fits this pattern exactly.

## 9. Skills useful for working on this project

### Software skills

- Python basics
- FastAPI basics
- async job basics
- SQL and persistence basics
- API contract thinking

### ML skills

- classification basics
- train, val, and test split
- evaluation metrics
- feature engineering
- calibration
- model versioning

### Product skills

- understanding false positives and false negatives
- reviewer workflow thinking
- data retention and audit thinking
- cost-aware inference decisions

## 10. The mindset shift

Do not think:

"Where is the one model that solves everything?"

Think:

"How does each signal contribute, and how does the system combine them safely?"

That mindset will help you understand TruthPixel much faster.
