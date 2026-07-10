"""Vertex AI (Gemini) LLM factory with a no-credentials stub fallback.

Design rule: agents add semantic/contextual reasoning ON TOP of the deterministic
CV signals — they never replace the classifiers. They run only on the gated branch
(uncertain / recapture-flagged claims), so Vertex spend scales with risk, not volume.
"""

import base64
import logging
from math import ceil
from functools import lru_cache

from ..config import get_settings
from ..observability import record_external_usage

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
        # Gemini 2.5 models spend part of max_output_tokens on hidden "thinking" tokens before
        # the visible answer (confirmed live: a real call returned usage_metadata with
        # output_token_details.reasoning=20 even for a 1-word reply) — for agents here, the
        # output is a short structured JSON blob, not a task that benefits from extended
        # reasoning, and the thinking tokens were eating enough of the 1024 budget to truncate
        # the JSON mid-string (semantic_inspector's "Unterminated string" parse failures,
        # confirmed live 2026-07-10). Disabling it fixes truncation and cuts latency/cost.
        thinking_budget=0,
    )


def image_content_block(image: bytes, mime: str = "image/jpeg") -> dict:
    """LangChain multimodal content block for an inline image."""
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"},
    }


def _extract_usage_metadata(response) -> dict:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        return usage
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        nested = response_metadata.get("usage_metadata")
        if isinstance(nested, dict):
            return nested
    return {}


def _text_token_estimate(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, ceil(len(stripped) / 4))


def _response_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def record_vertex_usage(*, operation: str, model_name: str, prompt_text: str, response) -> None:
    settings = get_settings()
    usage = _extract_usage_metadata(response)
    input_tokens = int(
        usage.get("input_tokens")
        or usage.get("prompt_token_count")
        or usage.get("prompt_tokens")
        or _text_token_estimate(prompt_text)
    )
    output_tokens = int(
        usage.get("output_tokens")
        or usage.get("candidates_token_count")
        or usage.get("completion_tokens")
        or _text_token_estimate(_response_text(response))
    )
    estimated_cost_usd = 0.0
    if settings.vertex_input_cost_per_1m_tokens > 0:
        estimated_cost_usd += (
            input_tokens * settings.vertex_input_cost_per_1m_tokens / 1_000_000
        )
    if settings.vertex_output_cost_per_1m_tokens > 0:
        estimated_cost_usd += (
            output_tokens * settings.vertex_output_cost_per_1m_tokens / 1_000_000
        )
    record_external_usage(
        provider="vertex_ai",
        operation=operation,
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
