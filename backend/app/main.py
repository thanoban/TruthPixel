import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .artifacts import get_artifact_store
from .auth import (
    AuthContext,
    allow_public_submission,
    generate_api_key,
    hash_api_key,
    key_prefix,
    require_admin_token,
    require_tenant_api_key,
)
from .config import get_settings
from .graph import run_claim
from .jobs import enqueue_claim_processing
from .schemas import (
    ArtifactKind,
    ApiKeyCreateRequest,
    AuditEvent,
    ClaimArtifact,
    ClaimContext,
    ClaimQueueStatus,
    ClaimDecisionRequest,
    ClaimListItem,
    ClaimReport,
    IssuedApiKeyResponse,
    StoredClaim,
    TenantCreateRequest,
    TenantResponse,
)
from .storage import (
    add_artifact,
    create_api_key,
    create_pending_claim,
    create_tenant,
    create_or_update_claim,
    get_artifact_record,
    get_claim,
    get_claim_audit_events,
    get_claim_queue_status,
    init_db,
    list_claim_artifacts,
    list_claims,
    record_decision,
    set_claim_task_info,
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
SubmissionAuth = Annotated[AuthContext, Depends(allow_public_submission)]
TenantAuth = Annotated[AuthContext, Depends(require_tenant_api_key)]


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "vertex_agents": "configured" if settings.vertex_configured else "stub",
        "storage": "configured" if settings.database_url else "disabled",
        "queue": "eager" if settings.celery_task_always_eager else "worker",
    }


@app.post("/v1/claims", response_model=StoredClaim)
async def analyze_claim(
    auth: SubmissionAuth,
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
    create_or_update_claim(report, tenant_id=auth.tenant_id)
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
        tenant_id=auth.tenant_id,
    )
    claim = get_claim(report.claim_id, tenant_id=auth.tenant_id)
    if claim is None:
        raise HTTPException(500, "claim was analyzed but could not be loaded after persistence")
    return claim


@app.post("/v1/claims/async", response_model=ClaimQueueStatus, status_code=status.HTTP_202_ACCEPTED)
async def queue_claim_analysis(
    auth: TenantAuth,
    image: UploadFile = File(...),
    order_id: str = Form(""),
    product_sku: str = Form(""),
    claim_reason: str = Form(""),
    listing_image_urls: str = Form(""),
    webhook_url: str = Form(""),
) -> ClaimQueueStatus:
    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"unsupported content type: {image.content_type}")
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "image exceeds 15 MB limit")
    if not data:
        raise HTTPException(400, "empty image upload")

    claim_id = str(uuid4())
    context = ClaimContext(
        order_id=order_id,
        product_sku=product_sku,
        claim_reason=claim_reason,
        listing_image_urls=[u.strip() for u in listing_image_urls.split(",") if u.strip()],
    )
    create_pending_claim(claim_id, context, webhook_url=webhook_url, tenant_id=auth.tenant_id)
    stored = get_artifact_store().put_bytes(
        claim_id=claim_id,
        kind=ArtifactKind.ORIGINAL_UPLOAD.value,
        data=data,
        filename=image.filename or "claim-upload",
        media_type=image.content_type or "application/octet-stream",
    )
    add_artifact(
        claim_id=claim_id,
        kind=ArtifactKind.ORIGINAL_UPLOAD,
        filename=stored.filename,
        media_type=stored.media_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        storage_backend=stored.storage_backend,
        storage_key=stored.storage_key,
        tenant_id=auth.tenant_id,
    )
    task_id = enqueue_claim_processing(claim_id)
    queue_status = set_claim_task_info(claim_id, task_id)
    if queue_status is None:
        raise HTTPException(500, "claim was queued but task metadata could not be stored")
    return queue_status


@app.get("/v1/claims", response_model=list[ClaimListItem])
async def list_claim_reports(
    auth: TenantAuth,
    limit: int = Query(default=20, ge=1, le=100),
    needs_review: bool | None = Query(default=None),
    decided: bool | None = Query(default=None),
) -> list[ClaimListItem]:
    return list_claims(
        limit=limit,
        needs_review=needs_review,
        decided=decided,
        tenant_id=auth.tenant_id,
    )


@app.get("/v1/claims/{claim_id}", response_model=StoredClaim)
async def get_claim_report(claim_id: str, auth: TenantAuth) -> StoredClaim:
    claim = get_claim(claim_id, tenant_id=auth.tenant_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return claim


@app.get("/v1/claims/{claim_id}/status", response_model=ClaimQueueStatus)
async def get_claim_status(claim_id: str, auth: TenantAuth) -> ClaimQueueStatus:
    claim = get_claim_queue_status(claim_id, tenant_id=auth.tenant_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return claim


@app.post("/v1/claims/{claim_id}/decision", response_model=StoredClaim)
async def submit_claim_decision(
    claim_id: str, request: ClaimDecisionRequest, auth: TenantAuth
) -> StoredClaim:
    claim = record_decision(claim_id, request, tenant_id=auth.tenant_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return claim


@app.get("/v1/claims/{claim_id}/audit", response_model=list[AuditEvent])
async def get_claim_audit(claim_id: str, auth: TenantAuth) -> list[AuditEvent]:
    claim = get_claim(claim_id, tenant_id=auth.tenant_id)
    if claim is None:
        raise HTTPException(404, "claim not found")
    return get_claim_audit_events(claim_id, tenant_id=auth.tenant_id)


@app.get("/v1/claims/{claim_id}/artifacts", response_model=list[ClaimArtifact])
async def get_claim_artifacts(claim_id: str, auth: TenantAuth) -> list[ClaimArtifact]:
    artifacts = list_claim_artifacts(claim_id, tenant_id=auth.tenant_id)
    if artifacts is None:
        raise HTTPException(404, "claim not found")
    return artifacts


@app.get("/v1/claims/{claim_id}/artifacts/{artifact_id}")
async def download_claim_artifact(claim_id: str, artifact_id: int, auth: TenantAuth) -> Response:
    artifact = get_artifact_record(claim_id, artifact_id, tenant_id=auth.tenant_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")
    data = get_artifact_store().get_bytes(artifact.storage_key)
    headers = {"Content-Disposition": f'inline; filename="{artifact.filename}"'}
    return Response(content=data, media_type=artifact.media_type, headers=headers)


@app.post("/v1/claims/{claim_id}/artifacts/heatmap", response_model=ClaimArtifact)
async def upload_claim_heatmap(
    claim_id: str,
    auth: TenantAuth,
    heatmap: UploadFile = File(...),
) -> ClaimArtifact:
    claim = get_claim(claim_id, tenant_id=auth.tenant_id)
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
        tenant_id=auth.tenant_id,
    )
    if artifact is None:
        raise HTTPException(404, "claim not found")
    return artifact


@app.post(
    "/v1/admin/tenants",
    response_model=TenantResponse,
    dependencies=[Depends(require_admin_token)],
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant_route(request: TenantCreateRequest) -> TenantResponse:
    return create_tenant(
        name=request.name,
        slug=request.slug,
        rate_limit_requests=request.rate_limit_requests,
        rate_limit_window_seconds=request.rate_limit_window_seconds,
    )


@app.post(
    "/v1/admin/tenants/{tenant_id}/api-keys",
    response_model=IssuedApiKeyResponse,
    dependencies=[Depends(require_admin_token)],
    status_code=status.HTTP_201_CREATED,
)
async def issue_api_key_route(tenant_id: str, request: ApiKeyCreateRequest) -> IssuedApiKeyResponse:
    raw_key = generate_api_key()
    issued = create_api_key(
        tenant_id=tenant_id,
        name=request.name,
        raw_key=raw_key,
        key_hash=hash_api_key(raw_key),
        key_prefix=key_prefix(raw_key),
        rate_limit_requests=request.rate_limit_requests,
        rate_limit_window_seconds=request.rate_limit_window_seconds,
    )
    if issued is None:
        raise HTTPException(404, "tenant not found")
    return issued
