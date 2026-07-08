from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from .config import get_settings


def _guess_extension(filename: str, media_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(media_type or "")
    return guessed or ".bin"


@dataclass(frozen=True, slots=True)
class StoredObject:
    storage_backend: str
    storage_key: str
    filename: str
    media_type: str
    byte_size: int
    sha256: str


class ArtifactStore:
    def put_bytes(
        self, *, claim_id: str, kind: str, data: bytes, filename: str, media_type: str
    ) -> StoredObject:
        raise NotImplementedError

    def get_bytes(self, storage_key: str) -> bytes:
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self, *, claim_id: str, kind: str, data: bytes, filename: str, media_type: str
    ) -> StoredObject:
        extension = _guess_extension(filename, media_type)
        storage_key = f"claims/{claim_id}/{kind}/{uuid4().hex}{extension}"
        target = self.root / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StoredObject(
            storage_backend="local",
            storage_key=storage_key,
            filename=filename or f"{kind}{extension}",
            media_type=media_type or "application/octet-stream",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get_bytes(self, storage_key: str) -> bytes:
        return (self.root / storage_key).read_bytes()


class S3ArtifactStore(ArtifactStore):
    def __init__(self):
        settings = get_settings()
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("boto3 is required for S3 artifact storage") from exc
        self.bucket = settings.s3_bucket
        self.region = settings.s3_region
        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
            region_name=settings.s3_region or None,
        )
        self._client_error = ClientError
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except self._client_error:
            create_kwargs = {"Bucket": self.bucket}
            if self.region and self.region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.region
                }
            self.client.create_bucket(**create_kwargs)

    def put_bytes(
        self, *, claim_id: str, kind: str, data: bytes, filename: str, media_type: str
    ) -> StoredObject:
        extension = _guess_extension(filename, media_type)
        storage_key = f"claims/{claim_id}/{kind}/{uuid4().hex}{extension}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=data,
            ContentType=media_type or "application/octet-stream",
        )
        return StoredObject(
            storage_backend="s3",
            storage_key=storage_key,
            filename=filename or f"{kind}{extension}",
            media_type=media_type or "application/octet-stream",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get_bytes(self, storage_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
        return response["Body"].read()


@lru_cache
def get_artifact_store() -> ArtifactStore:
    settings = get_settings()
    if settings.storage_backend.lower() == "s3":
        return S3ArtifactStore()
    return LocalArtifactStore(settings.artifact_dir)


def reset_artifact_store_state() -> None:
    get_artifact_store.cache_clear()
