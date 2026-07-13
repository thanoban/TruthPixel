"""Semantic artifact inspector — VLM agent.

Looks for AI-generation artifacts that live in image CONTENT, not pixel noise:
garbled/nonsense text, impossible shadows or reflections, unnatural over-smooth
textures, anatomical/geometric errors. These artifacts SURVIVE screenshots and
recompression, which makes this agent the semantic backstop against
screenshot-evasion (where EXIF/PRNU/pixel-forensics are destroyed).
"""

import json

from langchain_core.messages import HumanMessage

from ..schemas import AgentFinding
from .llm import get_vision_llm, image_content_block, record_vertex_usage

PROMPT = """You are a forensic image analyst for e-commerce return-fraud review.
Examine this customer-submitted "damaged product" photo for SEMANTIC signs of AI
generation or AI editing — signs that survive screenshots and recompression:

- garbled, warped, or nonsensical text/logos/labels
- impossible or inconsistent shadows, reflections, lighting direction
- unnaturally smooth or repeating textures; melted/fused object boundaries
- geometric or physical impossibilities (perspective, contact points, damage physics)
- damage that looks painted-on rather than physically caused

Respond with STRICT JSON only:
{"score": <0-1, 1 = strong AI/manipulation indicators>,
 "confidence": <0-1>,
 "findings": ["<short specific observation>", ...]}"""


async def run_semantic_inspector(image: bytes) -> AgentFinding:
    llm = get_vision_llm()
    if llm is None:
        return AgentFinding(
            agent="semantic_inspector",
            score=None,
            confidence=0.0,
            findings=["stub — Vertex AI not configured"],
        )
    msg = HumanMessage(content=[{"type": "text", "text": PROMPT}, image_content_block(image)])
    response = await llm.ainvoke([msg])
    record_vertex_usage(
        operation="semantic_inspector",
        model_name=llm.model_name,
        prompt_text=PROMPT,
        response=response,
    )
    try:
        data = json.loads(response.content.strip().removeprefix("```json").removesuffix("```"))
        return AgentFinding(
            agent="semantic_inspector",
            score=max(0.0, min(1.0, float(data["score"]))),
            confidence=max(0.0, min(1.0, float(data["confidence"]))),
            findings=[str(f) for f in data.get("findings", [])][:10],
            model=llm.model_name,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return AgentFinding(
            agent="semantic_inspector",
            score=None,
            confidence=0.0,
            findings=[f"unparseable agent output: {exc}"],
            model=llm.model_name,
        )
