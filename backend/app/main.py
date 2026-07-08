import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .artifacts import get_artifact_store
from .config import get_settings
from .graph import run_claim
from .schemas import (
    ArtifactKind,
    AuditEvent,
    ClaimArtifact,
    ClaimContext,
    ClaimDecisionRequest,
    ClaimListItem,
    ClaimReport,
    StoredClaim,
)
from .storage import (
    add_artifact,
    create_or_update_claim,
    get_artifact_record,
    get_claim,
    get_claim_audit_events,
    init_db,
    list_claim_artifacts,
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
    create_or_update_claim(report)
    stored = get_artifact_store().put_bytes(
        claim_id=report.claim_id,
        kind=ArtifactKind.ORIGINAL_UPLOAD.value,
        data=data,
        filename=image.filename or "claim-upload",
        media_type=image.content_type or "application/octet-stream",
    )
    add_artifact(
        claim_id=report.claim_id,
        kind=ArtifactKind.ORIGINAL_UPLOAD,
        filename=stored.filename,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        storage_backend=stored.storage_backend,
        storage_key=stored.storage_key,
    )
    claim = get_claim(report.claim_id)
    if claim is None:
        raise HTTPException(500, "claim was analyzed but could not be loaded after persistence")
    return claim


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


@app.get("/v1/claims/{claim_id}/artifacts", response_model=list[ClaimArtifact])
async def get_claim_artifacts(claim_id: str) -> list[ClaimArtifact]:
    artifacts = list_claim_artifacts(claim_id)
    if artifacts is None:
        raise HTTPException(404, "claim not found")
    return artifacts


@app.get("/v1/claims/{claim_id}/artifacts/{artifact_id}")
async def download_claim_artifact(claim_id: str, artifact_id: int) -> Response:
    artifact = get_artifact_record(claim_id, artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")
    data = get_artifact_store().get_bytes(artifact.storage_key)
    headers = {"Content-Disposition": f'inline; filename="{artifact.filename}"'}
    return Response(content=data, media_type=artifact.media_type, headers=headers)


@app.post("/v1/claims/{claim_id}/artifacts/heatmap", response_model=ClaimArtifact)
async def upload_claim_heatmap(
    claim_id: str,
    heatmap: UploadFile = File(...),
) -> ClaimArtifact:
    claim = get_claim(claim_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    if heatmap.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(415, f"unsupported heatmap content type: {heatmap.content_type}")
    data = await heatmap.read()
    if not data:
        raise HTTPException(400, "empty heatmap upload")
    stored = get_artifact_store().put_bytes(
        claim_id=claim_id,
        kind=ArtifactKind.HEATMAP.value,
        data=data,
        filename=heatmap.filename or "heatmap",
        media_type=heatmap.content_type or "application/octet-stream",
    )
    artifact = add_artifact(
        claim_id=claim_id,
        kind=ArtifactKind.HEATMAP,
        filename=stored.filename,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        storage_backend=stored.storage_backend,
        storage_key=stored.storage_key,
    )
    if artifact is None:
        raise HTTPException(404, "claim not found")
    return artifact
