# ML Fusion Module

## What this module is

Fusion training turns many layer outputs into one learned decision model.

Runtime files:

- `backend/app/fusion/engine.py`
- `backend/app/fusion/learned.py`

Training folder:

- `ml/fusion/`

## Why learned fusion matters

Weighted fusion is useful early, but learned fusion is where the system becomes more
data-driven.

Instead of manually deciding all layer importance forever, the project can learn:

- which signals matter most
- which combinations matter most
- which patterns predict true fraud better

## Training files

### `features.py`

Purpose:

- convert signals and agent findings into numeric feature rows

This is very important because models do not train directly on arbitrary Python objects.

They train on fixed feature vectors.

### `train_meta.py`

Purpose:

- load labeled claim examples
- build feature matrix
- train logistic regression
- calibrate outputs
- export runtime artifact

## Training input

Learned fusion is trained from labeled claims.

Each training example needs:

- signals
- agent findings, if any
- final label

Possible labels might reflect:

- fraud vs non-fraud
- reviewer-confirmed outcomes

## Runtime artifact idea

The training code exports an artifact the backend can load later.

That artifact contains:

- feature names
- means and scales
- coefficients
- intercept
- calibration values
- metrics

This is a very good pattern because it avoids retraining inside runtime.

## Why logistic regression is reasonable here

Beginners sometimes assume bigger model means better system.

But for fusion, logistic regression is often a strong choice because:

- features are already meaningful
- calibration can be strong
- explainability is easier
- export/runtime loading is simpler

For an early production system, this is often better than overcomplicating things.

## Calibration

This module explicitly cares about calibration, not only raw classification.

That matters because the output risk score is consumed by humans and thresholds.

If calibration is poor:

- review budgets are wasted
- reviewers lose trust
- thresholds become unstable

## Why this module is not fully complete yet

The code exists, but the real blocker is data.

Learned fusion needs:

- enough labeled claims
- trustworthy labels
- representative claim examples

This is a common real-world ML situation:

- code can be ready before data is ready

## Important lesson

In many applied ML systems, the most important future improvement is not a new huge model.

It is:

- better labels
- better features
- better calibration
- better evaluation

That is exactly what this module represents in TruthPixel.
