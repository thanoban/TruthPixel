from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./truthpixel.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: str = "local"
    local_artifact_dir: str = "./artifact_storage"
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "truthpixel-images"
    s3_region: str = "us-east-1"
    celery_result_backend: str = ""
    celery_task_always_eager: bool = False
    webhook_timeout_seconds: float = 10.0
    listing_fetch_timeout_seconds: float = 8.0
    listing_max_images: int = 5
    l5_recent_claim_window: int = 40
    # L5 v1: blend a frozen-CLIP embedding cosine similarity into the v0 hash+histogram
    # score. No training — pure inference, same open_clip loader as L1's checkpoint path.
    # ViT-B-32 (not L1's default ViT-L-14) — cheaper, similarity doesn't need the bigger model.
    # Defaults OFF, matching L1/L2/L3's opt-in-only pattern: found live (a real ~7-minute
    # test-suite run and a hung demo request) that first use triggers a real network
    # download of the model weights, which can stall indefinitely on a slow/offline
    # connection — see docs/CORRECTIONS.md. Opt in once weights are pre-warmed locally.
    l5_embedding_enabled: bool = False
    l5_embedding_model: str = "ViT-B-32"
    l5_embedding_pretrained: str = "openai"
    l5_embedding_device: str = "cpu"
    l5_embedding_weight: float = 0.5
    l1_model_path: str = ""
    l1_model_device: str = "auto"
    # L1 HF Inference API ensemble (zero-training path). When no local checkpoint is set
    # but an HF token + model list are, L1 calls these pretrained detectors and averages.
    # Defaults are commercially-licensed (Apache-2.0). Add Organika/sdxl-detector only for
    # non-commercial eval — it is CC-BY-NC.
    hf_api_token: str = ""
    l1_hf_models: str = "Ateeqq/ai-vs-human-image-detector,Nahrawy/AIorNot"
    hf_inference_timeout_seconds: float = 30.0
    l2_trufor_repo_dir: str = ""
    l2_trufor_model_file: str = ""
    l2_trufor_python_executable: str = ""
    l2_trufor_device: str = "-1"
    l2_trufor_experiment: str = "trufor_ph3"
    l2_trufor_timeout_seconds: float = 180.0
    api_auth_enabled: bool = False
    admin_api_token: str = ""
    default_tenant_rate_limit_requests: int = 120
    default_tenant_rate_limit_window_seconds: int = 60
    public_submission_enabled: bool = False
    public_rate_limit_requests: int = 5
    public_rate_limit_window_seconds: int = 3600
    artifact_access_token_secret: str = ""
    artifact_access_token_ttl_seconds: int = 300

    # CORS — public webapp + reviewer dashboard are separate origins from the API.
    # Comma-separated in env; defaults cover local Next.js dev servers on localhost
    # and 127.0.0.1 because both show up in real local verification workflows.
    cors_allow_origins: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def l1_hf_model_list(self) -> list[str]:
        return [m.strip() for m in self.l1_hf_models.split(",") if m.strip()]

    @property
    def l1_hf_ensemble_configured(self) -> bool:
        return bool(self.hf_api_token and self.l1_hf_model_list)

    @property
    def artifact_dir(self) -> Path:
        return Path(self.local_artifact_dir).expanduser().resolve()

    # Vertex AI / agents
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    vertex_model: str = "gemini-2.0-flash"
    vertex_input_cost_per_1m_tokens: float = 0.0
    vertex_output_cost_per_1m_tokens: float = 0.0
    agent_pass_enabled: bool = True
    # Agents run only when preliminary risk is inside (low, high) — i.e. uncertain —
    # or when recapture is flagged. High-confidence clean/fraud skips the LLM pass.
    agent_trigger_low: float = 0.35
    agent_trigger_high: float = 0.85

    # Fusion
    review_threshold: float = 0.5
    fusion_model_path: str = ""

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

    @property
    def l2_trufor_configured(self) -> bool:
        return bool(self.l2_trufor_repo_dir and self.l2_trufor_model_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
