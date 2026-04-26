from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionNode:
    agent_key: str
    output_key: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRationale:
    """Strukturierte Begruendung warum ein Agent ausgewaehlt wurde.

    Wird vom Planner pro Knoten erzeugt und vom Orchestrator als Spawn-Event-
    Payload + im `run_agents.metadata` persistiert. Frontend liest sie im
    Why-this-agent-Inspector aus.
    """

    agent_key: str
    score: int
    matched_capabilities: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    inclusion_reason: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPlan:
    nodes: tuple[ExecutionNode, ...]
    levels: tuple[tuple[ExecutionNode, ...], ...] = field(default_factory=tuple)
    rationales: dict[str, AgentRationale] = field(default_factory=dict)
