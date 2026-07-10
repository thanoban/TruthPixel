"""Report writer — turns raw signals into the human-readable reviewer summary.

Uses Gemini when configured; falls back to a deterministic template so the
pipeline always produces a readable report.
"""

from langchain_core.messages import HumanMessage

from ..schemas import AgentFinding, FusionResult, SignalResult
from .llm import get_vision_llm, record_vertex_usage

PROMPT_TEMPLATE = """Write a concise fraud-review summary (max 120 words) for a human
reviewer of an e-commerce return claim. Plain language, lead with the overall risk,
then the strongest evidence. Never call it a verdict — the reviewer decides.

Fused risk score: {risk:.2f} (needs_review={needs_review})
Signals: {signals}
Agent findings: {agents}"""


def _template_report(
    fusion: FusionResult, signals: list[SignalResult], agents: list[AgentFinding]
) -> str:
    lines = [f"Fused fraud-risk score: {fusion.risk_score:.0%}."]
    for s in signals:
        if s.error:
            lines.append(f"- {s.layer.value}: unavailable ({s.error})")
        elif s.score is not None and s.confidence >= 0.3:
            lines.append(f"- {s.layer.value}: score {s.score:.2f} (conf {s.confidence:.2f})")
    for a in agents:
        if a.findings and a.score is not None:
            lines.append(f"- {a.agent}: {a.findings[0]}")
    lines.append(
        "Recommended for human review." if fusion.needs_review else "Low risk — routine handling."
    )
    return "\n".join(lines)


async def write_report(
    fusion: FusionResult, signals: list[SignalResult], agents: list[AgentFinding]
) -> str:
    llm = get_vision_llm()
    if llm is None:
        return _template_report(fusion, signals, agents)
    prompt = PROMPT_TEMPLATE.format(
        risk=fusion.risk_score,
        needs_review=fusion.needs_review,
        signals=[s.model_dump(exclude={"model_version"}) for s in signals],
        agents=[a.model_dump() for a in agents],
    )
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        record_vertex_usage(
            operation="report_writer",
            model_name=llm.model_name,
            prompt_text=prompt,
            response=response,
        )
        return str(response.content).strip()
    except Exception:  # noqa: BLE001 — report generation must never fail the pipeline
        return _template_report(fusion, signals, agents)
