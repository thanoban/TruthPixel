import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .graph import run_claim
from .schemas import (
    AuditEvent,
    ClaimContext,
    ClaimDecisionRequest,
    ClaimListItem,
    ClaimReport,
    StoredClaim,
)
from .storage import (
    create_or_update_claim,
    get_claim,
    get_claim_audit_events,
    init_db,
    list_claims,
    record_decision,
)

logging.basicConfig(level=get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TruthPixel",
    description="Multi-signal image-integrity verification — return fraud, and beyond.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "vertex_agents": "configured" if settings.vertex_configured else "stub",
        "storage": "configured" if settings.database_url else "disabled",
    }


@app.post("/v1/claims", response_model=StoredClaim)
async def analyze_claim(
    image: UploadFile = File(...),
    order_id: str = Form(""),
    product_sku: str = Form(""),
    claim_reason: str = Form(""),
    listing_image_urls: str = Form(""),  # comma-separated
) -> ClaimReport:
    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"unsupported content type: {image.content_type}")
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "image exceeds 15 MB limit")
    if not data:
        raise HTTPException(400, "empty image upload")

    context = ClaimContext(
        order_id=order_id,
        product_sku=product_sku,
        claim_reason=claim_reason,
        listing_image_urls=[u.strip() for u in listing_image_urls.split(",") if u.strip()],
    )
    report = await run_claim(data, context)
    return create_or_update_claim(report)


@app.get("/v1/claims", response_model=list[ClaimListItem])
async def list_claim_reports(
    limit: int = Query(default=20, ge=1, le=100),
    needs_review: bool | None = Query(default=None),
    decided: bool | None = Query(default=None),
) -> list[ClaimListItem]:
    return list_claims(limit=limit, needs_review=needs_review, decided=decided)


@app.get("/v1/claims/{claim_id}", response_model=StoredClaim)
async def get_claim_report(claim_id: str) -> StoredClaim:
    claim = get_claim(claim_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return claim


@app.post("/v1/claims/{claim_id}/decision", response_model=StoredClaim)
async def submit_claim_decision(claim_id: str, request: ClaimDecisionRequest) -> StoredClaim:
    claim = record_decision(claim_id, request)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return claim


@app.get("/v1/claims/{claim_id}/audit", response_model=list[AuditEvent])
async def get_claim_audit(claim_id: str) -> list[AuditEvent]:
    claim = get_claim(claim_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return get_claim_audit_events(claim_id)
