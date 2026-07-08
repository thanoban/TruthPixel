"""Vertex AI (Gemini) LLM factory with a no-credentials stub fallback.

Design rule: agents add semantic/contextual reasoning ON TOP of the deterministic
CV signals — they never replace the classifiers. They run only on the gated branch
(uncertain / recapture-flagged claims), so Vertex spend scales with risk, not volume.
"""

import base64
import logging
from functools import lru_cache

from ..config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_vision_llm():
    """Return a LangChain chat model bound to Gemini on Vertex, or None (stub mode)."""
    settings = get_settings()
    if not settings.vertex_configured:
        logger.info("Vertex AI not configured — agents run in stub mode")
        return None
    from langchain_google_vertexai import ChatVertexAI

    return ChatVertexAI(
        model_name=settings.vertex_model,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        temperature=0.1,
        max_output_tokens=1024,
    )


def image_content_block(image: bytes, mime: str = "image/jpeg") -> dict:
    """LangChain multimodal content block for an inline image."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"},
    }
