# Frontend Surfaces Module

## What this module is

TruthPixel currently has two frontend surfaces:

- `webapp/`
- `dashboard/`

They serve different users but share the same backend truth.

## The most important rule

Frontend should stay thin.

That means:

- no local fusion logic
- no duplicate ML logic
- no separate scoring rules

Frontend should:

- collect input
- call backend APIs
- render backend results

## Surface 1: Public webapp

Folder:

- `webapp/`

Audience:

- anyone
- self-serve users
- demo users
- top-of-funnel discovery

Main behavior:

- upload one image
- call `POST /v1/claims`
- display returned stored claim / report

Important limitation:

- public surface intentionally has less context than enterprise claim flow

## Surface 2: Reviewer dashboard

Folder:

- `dashboard/`

Audience:

- internal tenant reviewers
- operations staff

Main behavior:

- review claim queue
- inspect claim detail
- see heatmap artifacts
- record human decisions
- inspect audit trail

This is more of a workflow surface than a marketing/discovery surface.

## Why two surfaces exist

Because the product has two different needs:

### Public webapp need

- make the product understandable quickly
- allow self-serve exploration
- demonstrate the fusion story

### Dashboard need

- help humans review and decide on cases
- provide operational workflow
- persist audit and decision history

## Shared backend principle

Both surfaces sit on top of the same core backend.

That is important because:

- one detection core stays consistent
- results stay comparable
- feature development happens once in backend

## What frontend developers should focus on

Frontend work in this project should mostly improve:

- clarity
- reviewer ergonomics
- upload flow
- evidence readability
- trust and transparency

Frontend should not try to secretly "improve detection" in the UI layer.

## Main files to read

### Public webapp

- `webapp/app/page.tsx`
- `webapp/app/types.ts`
- `webapp/app/globals.css`

### Reviewer dashboard

- `dashboard/app/page.tsx`
- `dashboard/app/claims/[claimId]/page.tsx`
- `dashboard/app/types.ts`
- `dashboard/app/api.ts`

## Good frontend questions to ask

- Is the risk story easy for humans to understand?
- Can a reviewer see which evidence matters?
- Is the upload flow honest about limitations?
- Are artifacts and heatmaps easy to inspect?
- Does the UI preserve the existing product language?

Those are better project questions than:

- "Can I add more frontend-only logic?"

## Long-term frontend maturity

Future frontend work may include:

- stronger auth flows
- better reviewer queue filters
- explicit privacy/retention UX
- onboarding/help surfaces
- richer audit/usage views

But all of that should still stay on top of the same backend contracts.
