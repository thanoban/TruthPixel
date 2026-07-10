# TruthPixel backend — production image.
# Build from the repo root so the checkpoint at backend/models/ (if present) is included:
#   docker build -f backend/Dockerfile -t truthpixel-backend .
#
# CPU-only torch/torchvision wheels are used deliberately — the CUDA build is several GB
# larger and this image targets CPU inference hosts (Azure App Service / Container Apps
# without a GPU SKU). See ML_PLAN.md §6 for the GPU-inference plan (Modal/RunPod) if that
# ever changes.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# libgomp1: torch's CPU backend needs the OpenMP runtime, which python:3.12-slim doesn't ship.
# NOT independently verified by building this image in this environment (no Docker daemon
# available here) — build and smoke-test before relying on this in a real deploy; see the
# ROADMAP.md Phase 1 checklist entry for this Dockerfile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
# Optional: only present if a checkpoint has been trained and placed here (see
# docs/KAGGLE_TRAINING.md / docs/COLAB_TRAINING.md §7). Safe to omit — L1 falls back to the
# HF ensemble or the neutral stub when backend/models/ doesn't exist or L1_MODEL_PATH is unset.
COPY backend/models ./models

EXPOSE 8000

# No .env is copied into the image — configuration is injected via environment variables at
# deploy time (Azure App Service "Application settings" / Container Apps env vars), matching
# .env.example's keys. See docs/ROADMAP.md's deploy notes.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
