import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .graph import run_claim
from .schemas import ClaimContext, ClaimReport

logging.basicConfig(level=get_settings().log_level)

app = FastAPI(
    title="TruthPixel",
    description="Multi-signal image-integrity verification — return fraud, and beyond.",
    version="0.1.0",
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
    }


@app.post("/v1/claims", response_model=ClaimReport)
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
    return await run_claim(data, context)
