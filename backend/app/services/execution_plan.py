from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionNode:
    agent_key: str
    output_key: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPlan:
    nodes: tuple[ExecutionNode, ...]
    levels: tuple[tuple[ExecutionNode, ...], ...] = field(default_factory=tuple)
