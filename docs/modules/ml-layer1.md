# ML Layer 1 Module

## What this module is

Layer 1 is the AI-generation detection layer.

Runtime file:

- `backend/app/analyzers/l1_aigen.py`

Training folder:

- `ml/layer1_aigen/`

## What problem L1 solves

It answers:

- does this image look AI-generated?

This is one of the strongest early signals in the system, but it is not the whole system.

## Why L1 exists in both `backend/` and `ml/`

### Runtime side

`backend/` is responsible for:

- loading the model or fallback
- scoring uploaded images
- returning a `SignalResult`

### Training side

`ml/` is responsible for:

- dataset discovery
- augmentation
- model architecture
- training
- evaluation
- artifact export

This split is normal in mature ML systems.

## Runtime modes

L1 currently has multiple runtime paths.

### 1. Local trained checkpoint

This is the preferred runtime mode when configured.

### 2. HF inference ensemble

If local checkpoint is not configured but HF path is configured, runtime can call pretrained
external detectors and combine them.

### 3. Safe fallback

If neither path is configured, system still degrades safely.

## Training module files

### `dataset.py`

Purpose:

- discover samples
- organize dataset records
- build train/val/test splits

### `augment.py`

Purpose:

- screenshot-style and robustness-oriented augmentation

This is important because the product cares about real-world transformations like resaves and
recaptures.

### `model.py`

Purpose:

- encoder and head config
- probe head building
- checkpoint metadata

### `train.py`

Purpose:

- training loop
- optimizer setup
- split usage
- checkpoint writing

### `eval.py`

Purpose:

- model evaluation

## Model design

TruthPixel’s L1 training strategy is intentionally practical.

It uses:

- frozen encoder
- smaller probe head on top

Why this is smart:

- cheaper than full end-to-end retraining
- easier to train with modest compute
- fast enough for an early-stage project

## Checkpoint metadata

A good ML project does not save only weights.

It should also save:

- encoder config
- head config
- training summary
- held-out generator info
- split summary

TruthPixel already does this, which is good practice.

## Held-out generator idea

One of the most important evaluation ideas in this project is:

- do not trust only same-distribution accuracy

Instead, the project wants performance that still holds on generators not seen during training.

That is a more honest benchmark for AI-image detection.

## What to learn from this module

This module teaches several important ML lessons:

1. runtime and training code should be separated
2. metadata and reproducibility matter
3. augmentation should match real evasion patterns
4. fallback paths matter in real deployment

## If you want to improve L1 later

Possible directions:

- better dataset quality
- larger or higher-resolution data
- broader held-out evaluation
- blend local checkpoint with HF ensemble
- better calibration

But the structure is already set up well for those future improvements.
