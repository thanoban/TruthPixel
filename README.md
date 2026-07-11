# TruthPixel

**Multi-signal image-integrity verification for e-commerce return / refund fraud.**

Given a customer-submitted "damaged product" photo, TruthPixel returns a calibrated fraud-risk
score with an explainable report by combining AI-generation detection, edit forensics,
screenshot/recapture detection, metadata/provenance checks, and listing-photo context checks.
A human reviewer makes the final call.

## Documentation

| Doc | Covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and signal-layer architecture |
| [docs/COMPETITORS.md](docs/COMPETITORS.md) | Landscape and product positioning |
| [docs/ML_PLAN.md](docs/ML_PLAN.md) | Model/training strategy and evaluation stance |
| [docs/AGENTS.md](docs/AGENTS.md) | LangGraph agent layer and cost-gating approach |
| [docs/USE_CASES.md](docs/USE_CASES.md) | API, reviewer dashboard, and public webapp surfaces |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What is actually landed versus still pending |
| [docs/CORRECTIONS.md](docs/CORRECTIONS.md) | Audit log of bugs found/fixed and reconciliation notes |
| [docs/EXECUTION_PLAN.md](docs/EXECUTION_PLAN.md) | Recommended next slices after this reconciliation |

## Current product surfaces

- `backend/`: FastAPI API for sync/async claims, storage, artifacts, audit trail, auth hooks,
  reviewer decisions, and labeled-feedback exports
- `dashboard/`: reviewer queue/detail workflow with artifact preview, audit trail, and decision capture
- `webapp/`: self-serve upload/report surface over the same backend claim pipeline

## Current status

Landed on this branch:
- sync + async claim submission
- persistence, artifact storage, audit trail, reviewer decisions
- tenant/admin auth hooks and public submission gate
- public webapp productization
- reviewer dashboard hardening
- tenant/admin label export endpoints for reviewed claims
- test-suite isolation from local `backend/.env`

Not yet landed here:
- observability/tracing stack
- classical L2 fallback branch
- batch claims API
- trained learned-fusion artifact in production
- full production verification of dashboard auth against a live protected backend

## Quickstart

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Submit a claim:

```bash
curl -X POST http://localhost:8000/v1/claims ^
  -F "image=@sample.jpg" ^
  -F "order_id=A123" ^
  -F "product_sku=SKU-9"
```

Run the public webapp:

```bash
cd webapp
npm install
copy .env.local.example .env.local
npm run dev
```

Run the reviewer dashboard:

```bash
cd dashboard
npm install
copy .env.local.example .env.local
npm run dev
```

Run tests from the repo root:

```bash
pytest -c pytest.ini -q
```

## Notes

- Anonymous webapp uploads require `PUBLIC_SUBMISSION_ENABLED=true` on the backend.
- The dashboard can proxy `X-API-Key` when `NEXT_PUBLIC_API_KEY` is configured.
- Label exports now exist at tenant/admin endpoints for retraining and audit workflows.

## License

TBD.
