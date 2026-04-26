from __future__ import annotations

import re

from backend.app.services.agent_registry import AgentDefinition
from backend.app.services.execution_plan import ExecutionNode, ExecutionPlan


class Planner:
    """Selects active agents and builds a dynamic DAG."""

    def create_execution_plan(self, prompt: str, active_agents: list[AgentDefinition]) -> ExecutionPlan:
        by_key = {agent.key: agent for agent in active_agents}
        if not by_key:
            raise RuntimeError("Keine aktiven Agenten in der Registry gefunden")

        intent_capabilities = self._intent_capabilities(prompt)
        scored = sorted(
            active_agents,
            key=lambda agent: self._agent_score(agent, intent_capabilities),
            reverse=True,
        )
        selected_keys = {agent.key for agent in scored if self._agent_score(agent, intent_capabilities) > 0}

        # Core outputs bleiben verpflichtend fuer den aktuellen Plan-Contract.
        required_outputs = {"literature", "protocol", "materials", "budget", "timeline", "review"}
        selected_keys.update(required_outputs)

        available_required = [agent_key for agent_key in required_outputs if agent_key in by_key]
        missing = [agent_key for agent_key in required_outputs if agent_key not in by_key]
        if missing:
            raise RuntimeError(f"Aktive Agenten fehlen in DB: {', '.join(missing)}")

        dependency_map: dict[str, tuple[str, ...]] = {
            "literature": (),
            "protocol": (),
            "materials": (),
            "budget": ("materials",),
            "timeline": ("protocol",),
            "review": ("protocol", "materials", "budget"),
        }
        output_map: dict[str, str] = {
            "literature": "literature",
            "protocol": "protocol",
            "materials": "materials",
            "budget": "budget",
            "timeline": "timeline",
            "review": "review_issues",
        }

        run_keys = [key for key in available_required if key in selected_keys]
        nodes = tuple(
            ExecutionNode(
                agent_key=key,
                output_key=output_map[key],
                depends_on=tuple(dep for dep in dependency_map[key] if dep in run_keys),
            )
            for key in run_keys
        )
        return ExecutionPlan(nodes=nodes, levels=self._topological_levels(nodes))

    def _intent_capabilities(self, prompt: str) -> set[str]:
        text = prompt.lower()
        tokens = set(re.findall(r"[a-zA-Z0-9_]+", text))
        capabilities: set[str] = set()
        if {"paper", "study", "novel", "literature", "doi", "reference"} & tokens:
            capabilities.update({"literature", "qc", "references"})
        if {"protocol", "method", "assay", "steps", "procedure"} & tokens:
            capabilities.update({"protocol", "methodology"})
        if {"material", "reagent", "catalog", "supplier"} & tokens:
            capabilities.update({"materials", "catalog"})
        if {"cost", "budget", "price", "eur", "usd"} & tokens:
            capabilities.update({"budget", "costing", "pricing"})
        if {"timeline", "schedule", "duration", "week", "day"} & tokens:
            capabilities.update({"timeline", "schedule", "dependencies"})
        if {"validate", "consistency", "review", "quality"} & tokens:
            capabilities.update({"review", "validation", "consistency"})
        return capabilities

    def _agent_score(self, agent: AgentDefinition, intent_capabilities: set[str]) -> int:
        capability_overlap = len(set(agent.capabilities) & intent_capabilities)
        core_bonus = 2 if agent.key in {"literature", "protocol", "materials", "budget", "timeline", "review"} else 0
        return capability_overlap + core_bonus

    def _topological_levels(self, nodes: tuple[ExecutionNode, ...]) -> tuple[tuple[ExecutionNode, ...], ...]:
        by_key = {node.agent_key: node for node in nodes}
        remaining = set(by_key.keys())
        resolved: set[str] = set()
        levels: list[tuple[ExecutionNode, ...]] = []

        while remaining:
            ready = sorted(
                [
                    by_key[key]
                    for key in remaining
                    if all(dep in resolved for dep in by_key[key].depends_on)
                ],
                key=lambda node: node.agent_key,
            )
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise RuntimeError(f"Zyklische oder unaufloesbare Abhaengigkeiten im Plan: {cycle}")
            level = tuple(ready)
            levels.append(level)
            resolved.update(node.agent_key for node in level)
            remaining.difference_update(node.agent_key for node in level)
        return tuple(levels)
