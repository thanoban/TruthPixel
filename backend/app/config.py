from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./truthpixel.db"
    storage_backend: str = "local"
    local_artifact_dir: str = "./artifact_storage"
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "truthpixel-images"
    s3_region: str = "us-east-1"

    # CORS — public webapp + reviewer dashboard are separate origins from the API.
    # Comma-separated in env; defaults cover local Next.js dev servers.
    cors_allow_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def artifact_dir(self) -> Path:
        return Path(self.local_artifact_dir).expanduser().resolve()

    # Vertex AI / agents
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    vertex_model: str = "gemini-2.0-flash"
    agent_pass_enabled: bool = True
    # Agents run only when preliminary risk is inside (low, high) — i.e. uncertain —
    # or when recapture is flagged. High-confidence clean/fraud skips the LLM pass.
    agent_trigger_low: float = 0.35
    agent_trigger_high: float = 0.85

    # Fusion
    review_threshold: float = 0.5

    # 3rd-party (optional)
    sightengine_api_user: str = ""
    sightengine_api_secret: str = ""
    sightengine_timeout_seconds: float = 15.0
    c2patool_path: str = "c2patool"
    c2patool_timeout_seconds: float = 8.0
    c2patool_trust_anchors: str = ""
    c2patool_allowed_list: str = ""
    c2patool_trust_config: str = ""

    @property
    def vertex_configured(self) -> bool:
        return bool(self.google_cloud_project)


@lru_cache
def get_settings() -> Settings:
    return Settings()
