import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

for path in (ROOT, BACKEND):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_TEST_ISOLATED_ENV_DEFAULTS = {
    "GOOGLE_CLOUD_PROJECT": "",
    "L1_MODEL_PATH": "",
    "HF_API_TOKEN": "",
    "SIGHTENGINE_API_USER": "",
    "SIGHTENGINE_API_SECRET": "",
    "L2_TRUFOR_REPO_DIR": "",
    "L2_TRUFOR_MODEL_FILE": "",
    "L5_EMBEDDING_ENABLED": "false",
}


def _clear_runtime_caches() -> None:
    from app.agents.llm import get_vision_llm
    from app.analyzers import l1_aigen
    from app.artifacts import reset_artifact_store_state
    from app.config import get_settings
    from app.embeddings import reset_embedding_cache
    from app.fusion.learned import load_learned_fusion_model
    from app.jobs import reset_job_state
    from app.storage import reset_storage_state

    get_settings.cache_clear()
    l1_aigen._load_runtime.cache_clear()
    get_vision_llm.cache_clear()
    reset_embedding_cache()
    load_learned_fusion_model.cache_clear()
    reset_job_state()
    reset_storage_state()
    reset_artifact_store_state()


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Force stub-safe defaults regardless of what backend/.env contains."""

    for key, value in _TEST_ISOLATED_ENV_DEFAULTS.items():
        monkeypatch.setenv(key, value)
    _clear_runtime_caches()
    yield
    _clear_runtime_caches()
