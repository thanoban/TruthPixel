# Backend Pipeline Module

## What this module is

This is the runtime pipeline that turns one uploaded image into one structured report.

Main file:

- `backend/app/graph/build.py`

This is one of the most important files in the project.

## Core idea

TruthPixel uses an orchestrated pipeline, not a single detector.

The pipeline does this:

1. run analyzers
2. decide whether agents are needed
3. fuse results
4. write report

## Why LangGraph is used

LangGraph is useful here because the flow is not just a simple linear function call.

It has:

- multiple stages
- conditional branching
- structured state
- future room for more branches or agents

## Pipeline state

The main shared state is `ClaimState`.

It carries:

- claim ID
- image bytes
- context
- signals
- agent findings
- fusion result
- report text

This is useful because each node can update part of the state instead of passing many
independent variables around.

## Nodes in the graph

### `node_analyzers`

Runs all analyzers in parallel.

This stage is the deterministic evidence layer.

### `route_after_analyzers`

Decides whether to send the claim into the agent pass.

This is cost-aware routing.

### `node_agents`

Runs the Gemini-based reasoning steps.

### `node_fusion`

Combines signals and agent findings into one final risk result.

### `node_report`

Turns technical outputs into reviewer-friendly text.

## Why analyzers run first

This is an important design choice.

The project treats analyzers as primary evidence.

Agents are secondary helpers, not replacements.

That is a strong architectural rule because:

- analyzers are usually cheaper
- analyzers are usually more stable for fixed signals
- agents are better for semantic nuance, not core scoring alone

## Conditional routing logic

Agent routing depends on:

- config
- preliminary fusion result
- strong recapture signal

This means:

- easy claims can skip expensive agent work
- suspicious or uncertain claims can receive extra reasoning

That is both:

- a cost optimization
- a product decision

## Output of the pipeline

`run_claim()` returns `ClaimReport`.

That includes:

- claim ID
- claim context
- list of signal results
- list of agent findings
- fusion result
- report text

The API later turns that into a `StoredClaim` by adding persistence-related fields.

## Why this module matters so much

If you change:

- analyzers
- agents
- fusion
- routing policy

then the pipeline behavior changes.

So this file is the best place to understand how the product really works at runtime.

## Mental model

Think of this module as the conductor of an orchestra.

It does not play every instrument itself.

Instead it decides:

- who plays
- in what order
- when extra reasoning is needed
- how outputs become one final result

## Future growth

This structure makes future additions easier, such as:

- more agent branches
- batch routing
- tenant-specific pathways
- different workflows for different product surfaces

That is why a graph-based orchestrator is a good fit here.
