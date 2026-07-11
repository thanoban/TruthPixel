import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

for path in (BACKEND_ROOT, PROJECT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

# Force every external/heavy integration off by default for every test, regardless of what
# backend/.env contains. .env now carries real GOOGLE_CLOUD_PROJECT / L1_MODEL_PATH (Vertex
# agents and the trained L1 checkpoint went live 2026-07-10) — without this, tests that
# assume "stub mode" instead load the real ~1.3GB CLIP checkpoint and make real Vertex AI
# calls. That turned a ~20s suite into 136s with 8 failures from resource contention when
# run together (individually each such test passed, just 35-40s instead of near-instant).
# See docs/CORRECTIONS.md 2026-07-10 (4) for the full incident.
#
# A test that specifically wants to exercise a real/configured integration still can: call
# monkeypatch.setenv(...) + get_settings.cache_clear() in the test itself (the existing
# pattern already used throughout this suite) — that runs after this fixture and wins.
_STUB_SAFE_ENV = {
    "GOOGLE_CLOUD_PROJECT": "",
    "L1_MODEL_PATH": "",
    "HF_API_TOKEN": "",
    "L2_TRUFOR_REPO_DIR": "",
    "L2_TRUFOR_MODEL_FILE": "",
    "SIGHTENGINE_API_USER": "",
    "SIGHTENGINE_API_SECRET": "",
    "L5_EMBEDDING_ENABLED": "false",
    "FUSION_MODEL_PATH": "",
}


@pytest.fixture(autouse=True)
def _stub_mode_by_default(monkeypatch):
    for key, value in _STUB_SAFE_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
