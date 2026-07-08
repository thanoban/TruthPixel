"""LangGraph orchestrator — the claim-analysis state graph.

    analyzers ──► route ──┬──► agents ──► fusion ──► report ──► END
                          └──────────────► fusion (skip agents — cost gating)

Stage A (analyzers) runs the five deterministic layers in parallel; they are the
ground-truth signals. The conditional edge sends only uncertain or
recapture-flagged claims through the Gemini agent pass (Stage B), so Vertex
spend scales with risk, not volume. Fusion treats agent findings as extra
features; the report node produces the reviewer-facing summary.
"""

import asyncio
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..agents import run_damage_plausibility, run_semantic_inspector, write_report
from ..analyzers import ALL_ANALYZERS
from ..config import get_settings
from ..fusion import fuse
from ..schemas import AgentFinding, ClaimContext, ClaimReport, FusionResult, Layer, SignalResult


class ClaimState(TypedDict, total=False):
    claim_id: str
    image: bytes
    context: ClaimContext
    signals: list[SignalResult]
    agent_findings: list[AgentFinding]
    fusion: FusionResult
    report_text: str


async def node_analyzers(state: ClaimState) -> dict[str, Any]:
    results = await asyncio.gather(
        *(a().analyze(state["image"], state["context"], state["claim_id"]) for a in ALL_ANALYZERS)
    )
    return {"signals": list(results)}


def route_after_analyzers(state: ClaimState) -> str:
    """Cost gate: run agents only when it can change the outcome."""
    settings = get_settings()
    if not settings.agent_pass_enabled:
        return "fusion"
    preliminary = fuse(state["signals"], [])
    recapture_flagged = any(
        s.layer == Layer.L3_RECAPTURE and s.score is not None and s.score >= 0.7
        for s in state["signals"]
    )
    uncertain = settings.agent_trigger_low <= preliminary.risk_score <= settings.agent_trigger_high
    return "agents" if (uncertain or recapture_flagged) else "fusion"


async def node_agents(state: ClaimState) -> dict[str, Any]:
    findings = await asyncio.gather(
        run_semantic_inspector(state["image"]),
        run_damage_plausibility(state["image"], state["context"]),
    )
    return {"agent_findings": list(findings)}


async def node_fusion(state: ClaimState) -> dict[str, Any]:
    return {"fusion": fuse(state["signals"], state.get("agent_findings", []))}


async def node_report(state: ClaimState) -> dict[str, Any]:
    text = await write_report(
        state["fusion"], state["signals"], state.get("agent_findings", [])
    )
    return {"report_text": text}


def build_graph():
    g = StateGraph(ClaimState)
    g.add_node("analyzers", node_analyzers)
    g.add_node("agents", node_agents)
    g.add_node("fusion", node_fusion)
    g.add_node("report", node_report)

    g.set_entry_point("analyzers")
    g.add_conditional_edges(
        "analyzers", route_after_analyzers, {"agents": "agents", "fusion": "fusion"}
    )
    g.add_edge("agents", "fusion")
    g.add_edge("fusion", "report")
    g.add_edge("report", END)
    return g.compile()


_graph = None


async def run_claim(image: bytes, context: ClaimContext, claim_id: str | None = None) -> ClaimReport:
    global _graph
    if _graph is None:
        _graph = build_graph()
    claim_id = claim_id or str(uuid.uuid4())
    final: ClaimState = await _graph.ainvoke(
        {"claim_id": claim_id, "image": image, "context": context}
    )
    return ClaimReport(
        claim_id=claim_id,
        context=context,
        signals=final["signals"],
        agent_findings=final.get("agent_findings", []),
        fusion=final["fusion"],
        report_text=final["report_text"],
    )
