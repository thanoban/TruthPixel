"""Damage plausibility agent — VLM agent for the e-commerce context layer.

Reasons about things no classifier can: is this the same product as the listing?
Is this damage type physically plausible for this product category? Is the lighting
on the "damaged" region consistent with the rest of the scene?
"""

import json

from langchain_core.messages import HumanMessage

from ..schemas import AgentFinding, ClaimContext
from .llm import get_vision_llm, image_content_block

PROMPT_TEMPLATE = """You are reviewing an e-commerce return claim for fraud.

Claim context:
- product SKU: {sku}
- stated reason: {reason}

Examine the customer's "damaged product" photo and assess:
1. Is the visible product consistent with the stated product/claim?
2. Is the damage physically plausible for this product type and the stated reason?
3. Is lighting/shadow on the damaged region consistent with the rest of the scene?
4. Does the damage look staged, painted-on, or digitally added?

Respond with STRICT JSON only:
{{"score": <0-1, 1 = implausible/likely fraudulent>,
 "confidence": <0-1>,
 "findings": ["<short specific observation>", ...]}}"""


async def run_damage_plausibility(image: bytes, context: ClaimContext) -> AgentFinding:
    llm = get_vision_llm()
    if llm is None:
        return AgentFinding(
            agent="damage_plausibility",
            score=None,
            confidence=0.0,
            findings=["stub — Vertex AI not configured"],
        )
    prompt = PROMPT_TEMPLATE.format(
        sku=context.product_sku or "unknown", reason=context.claim_reason or "unspecified"
    )
    msg = HumanMessage(content=[{"type": "text", "text": prompt}, image_content_block(image)])
    response = await llm.ainvoke([msg])
    try:
        data = json.loads(response.content.strip().removeprefix("```json").removesuffix("```"))
        return AgentFinding(
            agent="damage_plausibility",
            score=max(0.0, min(1.0, float(data["score"]))),
            confidence=max(0.0, min(1.0, float(data["confidence"]))),
            findings=[str(f) for f in data.get("findings", [])][:10],
            model=llm.model_name,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return AgentFinding(
            agent="damage_plausibility",
            score=None,
            confidence=0.0,
            findings=[f"unparseable agent output: {exc}"],
            model=llm.model_name,
        )
