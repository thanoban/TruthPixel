# Multi-Agent System — LangGraph + Gemini on Vertex AI

> How LLM agents make TruthPixel smarter than a stack of classifiers — and the rules that
> stop them from becoming expensive noise.
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [ROADMAP.md](ROADMAP.md)

## 0. Why agents at all

Deterministic CV models answer "does this image carry generation/edit artifacts?"
They cannot answer:
- *Is this even the same product as the listing?*
- *Is a shattered screen plausible for a cushion order?*
- *Does the lighting on the "damage" match the rest of the scene?*
- *Does that label text spell anything real?*

Those are **semantic/contextual** judgments — exactly what a VLM does well. And critically:
**semantic artifacts survive screenshots.** When a fraudster screenshots an AI image and
wipes EXIF/PRNU/pixel-noise, the garbled label text and impossible shadow are still in the
content. The agent pass is our screenshot-evasion backstop. The available $1,000 GCP credit
*may* make this near-free to run — but it's scoped to GenAI App Builder (Vertex AI
Search/Conversation/Agent Builder), not a blanket Vertex allowance. **Verify the credit
actually applies to Gemini API calls (a small test call, checked against Billing → Credits)
before budgeting around it** — do not assume it covers this the way it doesn't cover Colab
Enterprise GPU (see [COLAB_TRAINING.md](COLAB_TRAINING.md) and [ML_PLAN.md](ML_PLAN.md) §6).
Cost gating (§ below) keeps the fallback cheap either way — pay-as-you-go Gemini Flash pricing
is low enough that gated agent calls are affordable without relying on the credit at all.

## 1. Non-negotiable design rules

1. **Classifiers are ground truth, agents add on top.** A VLM guessing "is this AI?" from
   pixels is *weaker* than the CLIP head. Agents only do what classifiers can't: semantics
   and context. Fusion weights enforce this.
2. **Cost gating.** Agents run only when they can change the outcome:
   - preliminary fused risk in the uncertain band `(AGENT_TRIGGER_LOW, AGENT_TRIGGER_HIGH)`, or
   - recapture flagged (score ≥ 0.7).
   High-confidence clean or obvious fraud never touches an LLM. Spend scales with risk,
   not volume.
3. **Structured outputs only.** Every agent returns a Pydantic `AgentFinding`
   `{score, confidence, findings[]}` parsed from strict JSON. Unparseable output degrades to
   `score=None` — never crashes the pipeline, never free-texts into fusion.
4. **Full auditability.** Prompt version, model name, and raw findings are logged per claim.
   Reviewer sees exactly what the agent claimed.
5. **Stub fallback.** With no Vertex credentials, agents return neutral stubs — the graph
   runs identically in local dev/CI.

## 2. The agents

| Agent | Input | Judges | Output feeds |
|---|---|---|---|
| **Semantic artifact inspector** | claim image | garbled text/logos, impossible shadows/reflections, melted boundaries, painted-on damage, physics errors | fusion feature + report |
| **Damage plausibility** | claim image + order context (SKU, reason, listing photos) | same product? damage plausible for category/reason? lighting consistent? staged? | fusion feature + report |
| **Report writer** | all signals + fusion result | — (synthesis, not judgment) | reviewer-facing summary text |

Planned (Phase 2):
| Agent | Purpose |
|---|---|
| **Cross-claim pattern agent** | given reviewer-flagged clusters, reasons over repeated damage photos / serial fraudster patterns from L5 reverse-search hits |
| **Triage router** | learns per-tenant routing policies (which claims deserve the expensive pass) replacing the static threshold gate |

## 3. The graph

Implemented in `backend/app/graph/build.py` as a LangGraph `StateGraph`:

```
        ┌────────────────────────────────────────────┐
        │ analyzers (Stage A — parallel fan-out)      │
        │   L1 aigen · L2 forensics · L3 recapture    │
        │   L4 metadata · L5 context                  │
        └──────────────────┬─────────────────────────┘
                           │ route_after_analyzers
         uncertain / recapture-flagged        confident
                           │                      │
        ┌──────────────────▼───────────┐          │
        │ agents (Stage B — parallel)   │          │
        │   semantic inspector          │          │
        │   damage plausibility         │          │
        └──────────────────┬───────────┘          │
                           ▼                      ▼
        ┌────────────────────────────────────────────┐
        │ fusion (meta-classifier; agent scores =     │
        │ extra features; missing signals tolerated)  │
        └──────────────────┬─────────────────────────┘
                           ▼
        │ report (Gemini writer, template fallback)  │
                           ▼
                          END
```

State (`ClaimState`): `claim_id, image, context, signals[], agent_findings[], fusion, report_text`.

## 4. Model & infra choices

- **Model:** `gemini-2.0-flash` on Vertex (`langchain-google-vertexai.ChatVertexAI`),
  temperature 0.1, 1024 max output tokens. Flash over Pro: the judgments are perceptual +
  short-form; Flash is ~10x cheaper and fast enough for the async pipeline. Upgrade the
  plausibility agent to Pro only if evals show it pays.
- **Config:** `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `VERTEX_MODEL`,
  `AGENT_PASS_ENABLED`, `AGENT_TRIGGER_LOW/HIGH` (see `.env.example`).
- **Multimodal input:** inline base64 image blocks (LangChain content-block format).
- **Later:** LangGraph checkpointing (Postgres) for resumable claim runs + human-in-the-loop
  interrupts when a reviewer requests an agent re-pass with added context.

## 5. Evaluating agents (they are features, not magic)

- Each agent's score is a fusion feature → its worth is measured the same way as any layer:
  **ablation** (drop it, measure fusion AUROC/precision delta) on the claims test set.
- Track per-agent: parse-failure rate, latency, cost/claim, agreement with reviewer decisions.
- Prompt changes are versioned; a prompt bump reruns the eval suite before deploy
  (same regression gate as model versions — see ML_PLAN §4).
