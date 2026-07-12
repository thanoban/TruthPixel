# Backend Agents and Fusion Module

## What this module is

This part of the system answers two questions:

1. When should extra reasoning happen?
2. How do all signals become one final decision?

Main folders/files:

- `backend/app/agents/`
- `backend/app/fusion/`

## Agents vs analyzers

This distinction is very important.

### Analyzers

- deterministic signal producers
- closer to classical CV / direct model outputs
- run first

### Agents

- reasoning helpers
- semantic interpretation
- natural-language reporting
- run only when useful

TruthPixel’s rule is:

- analyzers are primary evidence
- agents are secondary reasoning support

## Agent modules

### `semantic_inspector.py`

Purpose:

- look for semantic or visual oddities that survive recompression or screenshotting

Examples:

- impossible details
- weird text
- inconsistent reflections/shadows

### `damage_plausibility.py`

Purpose:

- judge whether the claimed damage story makes sense relative to image/context

This is especially useful in the return-fraud domain.

### `report_writer.py`

Purpose:

- convert structured outputs into a readable summary

This matters because the product is built for human review, not only internal numeric scores.

### `llm.py`

Purpose:

- central LLM access/wiring

## Why agents are gated

Gemini calls cost more and take more time than simple deterministic checks.

So the system avoids using them on every claim.

This is controlled in:

- `backend/app/graph/build.py`

Agents usually run when:

- risk is uncertain
- or recapture is strongly flagged

## Fusion module

Main file:

- `backend/app/fusion/engine.py`

Purpose:

- combine all usable signals into one final risk score

## Weighted fusion

Current default behavior:

- confidence-weighted combination
- per-layer base weights
- extra recapture combo boost rule

This means some layers matter more than others.

Example:

- metadata is intentionally lower-weight than stronger direct evidence layers

## Learned fusion

Supporting file:

- `backend/app/fusion/learned.py`

Purpose:

- load a trained fusion artifact if available

If `FUSION_MODEL_PATH` is configured and valid:

- learned model is used

Otherwise:

- weighted fallback stays active

This is a good production pattern because it allows runtime upgrade without rewriting the
whole pipeline contract.

## Why fusion matters so much

Fusion is the true product intelligence layer.

Why:

- single detectors are commodity-like
- combining signals intelligently is harder
- the final review decision depends on system-level behavior, not only one model

## Contribution breakdown

Fusion also returns contribution info.

That is important because the system is reviewer-facing.

A reviewer needs more than:

- "score = 0.82"

They also need:

- what pushed the score upward
- which layer mattered most

## Error handling

Fusion must degrade gracefully.

That means:

- missing layer should not break final result
- bad learned artifact should not kill runtime
- system should still return something useful

This is one reason the weighted fallback remains valuable even after learned fusion exists.

## What to study first

Read:

1. `backend/app/agents/__init__.py`
2. each agent file
3. `backend/app/fusion/engine.py`
4. `backend/app/fusion/learned.py`
5. `ml/fusion/` docs after that

That order helps because runtime understanding should come before training understanding.
