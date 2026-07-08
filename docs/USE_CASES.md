# Use Cases & Product Surfaces

> TruthPixel's fusion engine (L1–L5, see [ARCHITECTURE.md](ARCHITECTURE.md)) is domain-agnostic
> — it scores "is this image what it claims to be?" The **e-commerce return claim is the
> beachhead**, not the ceiling. This doc covers who else can use it and through what surface.
>
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) ·
> [COMPETITORS.md](COMPETITORS.md) · [ML_PLAN.md](ML_PLAN.md) · [AGENTS.md](AGENTS.md) ·
> [ROADMAP.md](ROADMAP.md)

## 1. Product surfaces — three ways in

| Surface | Who uses it | Auth | Status |
|---|---|---|---|
| **B2B API** (`POST /v1/claims`) | Marketplace/platform backends, integrated into their returns flow | Per-tenant API key | Phase 0 scaffold done |
| **Reviewer dashboard** (`dashboard/`) | A tenant's internal fraud-review staff | SSO / tenant-scoped login | Phase 1 |
| **Public webapp** (`webapp/`) | Anyone — self-serve, one image at a time | Anonymous (rate-limited) or free API key | **Scaffolded now** |

All three sit on top of the same `run_claim()` LangGraph pipeline and the same fusion engine —
one detection core, three doors in. This matters for the moat: every use case feeds the same
signal-quality and (eventually) fusion-training loop.

## 2. Use cases beyond return fraud

The signals don't care why someone wants to know if a photo is real. Same five layers,
different framing per audience:

| Use case | Who | What they upload | What changes |
|---|---|---|---|
| **E-commerce return fraud** (primary) | Marketplace trust & safety teams | "Damaged product" claim photo | L5 context cross-check against seller listing is load-bearing |
| **Marketplace listing integrity** | Marketplace ops, before a listing goes live | Seller's product photos | Flips L5: is *this* photo itself AI-generated/stock, not "does it match a claim" |
| **Consumer self-check** | Anyone — buyer, journalist, casual user | Any image ("is this AI?") | L5 context is skipped (no order/listing to compare against); L1–L4 only |
| **UGC / journalism verification** | Newsrooms, content moderators | Social-media or submitted photos | L3 recapture matters most — screenshots/reposts are the norm here, not the exception |
| **Insurance claim photos** | Insurers (property/auto damage claims) | "Damage" photo submitted with a claim | Structurally identical to return fraud — same pipeline, different `claim_reason` vocabulary |
| **Dating / social profile photos** | Platforms doing photo-verification | Profile photo | L1 (AI-gen) and L2 (face-swap-adjacent manipulation) dominate; L5 irrelevant |

**Design implication:** `ClaimContext` (see `backend/app/schemas.py`) already treats
`listing_image_urls` and `claim_reason` as optional — when absent, L5 and the damage-plausibility
agent degrade gracefully (see `fusion/engine.py`'s missing-signal handling). No schema change
needed to serve the non-e-commerce cases; only the *product surface and copy* differ.

## 3. The public webapp

**Why add it:** every commercial competitor we mapped in [COMPETITORS.md](COMPETITORS.md)
(AI-or-Not, TrueMedia, etc.) has a free self-serve checker as the top-of-funnel — it's how
users discover the product before any enterprise sells. TruthPixel's webapp is the same
funnel, but the report it returns already demonstrates the fusion advantage (multi-signal
breakdown + heatmap) instead of a bare "87% AI" — that's the wedge that turns a free-tier
visitor into an enterprise conversation.

**Scope (Phase 0):**
- Single-page upload → fused report (score, per-layer breakdown, heatmap overlay, plain-English
  summary from the report-writer agent).
- No order/listing context fields — consumer-facing, so L5 and damage-plausibility naturally
  no-op (see §2 above; the backend already handles this).
- Calls the same `POST /v1/claims` endpoint the B2B integration uses — zero backend duplication.

**Deferred to Phase 1+:**
- Anonymous rate limiting (IP or browser-fingerprint based) to control cost — public traffic is
  the reason Phase 1 formalizes per-tenant/per-key rate limits (see [ROADMAP.md](ROADMAP.md)).
- Image retention policy for anonymous uploads (short TTL, no persistence beyond the response,
  unlike tenant claims which are retained for audit) — a privacy commitment worth stating on
  the page itself.
- Optional free API key signup if usage needs throttling beyond anonymous limits.

## 4. What does NOT change

- **One detection core.** The webapp is a thin client; it must never grow its own copy of
  fusion logic, analyzer calls, or agent prompts. If a use case needs different behavior, the
  change belongs in `backend/app/` (schemas, fusion weights, or a new `ClaimContext` field),
  not in webapp-only code.
- **Same honesty discipline.** No use case gets a binary verdict. The public webapp shows the
  same confidence-scored, human-readable report as the enterprise path — no consumer-grade
  "AI or not?" oversimplification, because that's exactly the framing we said we're better than.
