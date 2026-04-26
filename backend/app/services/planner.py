from __future__ import annotations

import re

from backend.app.services.agent_registry import AgentDefinition
from backend.app.services.execution_plan import (
    AgentRationale,
    ExecutionNode,
    ExecutionPlan,
)


# Wir halten Keyword-Buckets zentral, damit `_intent_capabilities` und der
# Why-this-agent-Inspector dieselbe Quelle benutzen.
_KEYWORD_BUCKETS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (
        frozenset({"paper", "study", "novel", "literature", "doi", "reference"}),
        frozenset({"literature", "qc", "references"}),
    ),
    (
        frozenset({"protocol", "method", "assay", "steps", "procedure"}),
        frozenset({"protocol", "methodology"}),
    ),
    (
        frozenset({"material", "reagent", "catalog", "supplier"}),
        frozenset({"materials", "catalog"}),
    ),
    (
        frozenset({"cost", "budget", "price", "eur", "usd"}),
        frozenset({"budget", "costing", "pricing"}),
    ),
    (
        frozenset({"timeline", "schedule", "duration", "week", "day"}),
        frozenset({"timeline", "schedule", "dependencies"}),
    ),
    (
        frozenset({"validate", "consistency", "review", "quality"}),
        frozenset({"review", "validation", "consistency"}),
    ),
    (
        frozenset(
            {"criteria", "control", "controls", "statistic", "statistical", "replicate"}
        ),
        frozenset({"validation", "controls", "success_criteria", "statistics"}),
    ),
)


class Planner:
    """Selects active agents and builds a dynamic DAG."""

    def create_execution_plan(self, prompt: str, active_agents: list[AgentDefinition]) -> ExecutionPlan:
        by_key = {agent.key: agent for agent in active_agents}
        if not by_key:
            raise RuntimeError("Keine aktiven Agenten in der Registry gefunden")

        prompt_tokens = self._prompt_tokens(prompt)
        intent_capabilities = self._intent_capabilities_from_tokens(prompt_tokens)
        scored = sorted(
            active_agents,
            key=lambda agent: self._agent_score(agent, intent_capabilities),
            reverse=True,
        )
        selected_keys = {agent.key for agent in scored if self._agent_score(agent, intent_capabilities) > 0}

        # Core outputs bleiben verpflichtend fuer den aktuellen Plan-Contract.
        # Der Validation-Agent ist optional: wenn er in der DB-Registry fehlt
        # (z.B. alte Installationen ohne Backfill), faellt der Orchestrator auf
        # den Legacy-Direktaufruf von `validation_agent(...)` zurueck.
        required_outputs = {"literature", "protocol", "materials", "budget", "timeline", "review"}
        optional_outputs = {"validation"}
        selected_keys.update(required_outputs)
        for optional_key in optional_outputs:
            if optional_key in by_key:
                selected_keys.add(optional_key)

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
            # Validation laeuft parallel zum Review (beides braucht Protocol +
            # Materials), bringt aber inhaltlich was anderes: Review prueft auf
            # Inkonsistenzen, Validation erzeugt Erfolgskriterien & Stats-Plan.
            "validation": ("protocol", "materials"),
        }
        output_map: dict[str, str] = {
            "literature": "literature",
            "protocol": "protocol",
            "materials": "materials",
            "budget": "budget",
            "timeline": "timeline",
            "review": "review_issues",
            "validation": "validation",
        }

        # Es kann passieren, dass der Validation-Agent zwar in der DB ist, aber
        # nicht in den selected_keys (z.B. Score 0). Da er Teil des Plan-
        # Contracts ist, ziehen wir ihn unbedingt rein, wenn die Registry ihn
        # liefert -- analog zu den required_outputs.
        for optional_key in optional_outputs:
            if optional_key in by_key:
                selected_keys.add(optional_key)
                if optional_key not in available_required:
                    available_required.append(optional_key)

        run_keys = [key for key in available_required if key in selected_keys]
        nodes = tuple(
            ExecutionNode(
                agent_key=key,
                output_key=output_map[key],
                depends_on=tuple(dep for dep in dependency_map[key] if dep in run_keys),
            )
            for key in run_keys
        )
        rationales = self._build_rationales(
            nodes, by_key, prompt_tokens, intent_capabilities
        )
        return ExecutionPlan(
            nodes=nodes,
            levels=self._topological_levels(nodes),
            rationales=rationales,
        )

    def _build_rationales(
        self,
        nodes: tuple[ExecutionNode, ...],
        by_key: dict[str, AgentDefinition],
        prompt_tokens: set[str],
        intent_capabilities: set[str],
    ) -> dict[str, AgentRationale]:
        core_keys = {"literature", "protocol", "materials", "budget", "timeline", "review"}
        rationales: dict[str, AgentRationale] = {}
        for node in nodes:
            agent = by_key.get(node.agent_key)
            if agent is None:
                continue
            agent_caps = set(agent.capabilities)
            matched_caps = sorted(agent_caps & intent_capabilities)
            matched_keywords = sorted(self._keywords_for_capabilities(agent_caps, prompt_tokens))
            score = self._agent_score(agent, intent_capabilities)

            if node.agent_key in core_keys:
                if matched_caps:
                    reason = (
                        f"Required for every plan; the prompt also matched "
                        f"{', '.join(matched_caps)}."
                    )
                else:
                    reason = "Required for every plan (mandatory output of the plan contract)."
            elif node.agent_key == "validation":
                if matched_caps:
                    reason = (
                        "Adds measurable success criteria, controls and a statistical "
                        f"plan; matched intent capabilities: {', '.join(matched_caps)}."
                    )
                else:
                    reason = (
                        "Adds measurable success criteria, controls and a statistical "
                        "plan to make the experiment reproducible."
                    )
            elif matched_caps:
                reason = (
                    "Selected because the prompt matches its capabilities: "
                    f"{', '.join(matched_caps)}."
                )
            else:
                reason = "Selected as a supporting agent in this plan."

            rationales[node.agent_key] = AgentRationale(
                agent_key=node.agent_key,
                score=score,
                matched_capabilities=tuple(matched_caps),
                matched_keywords=tuple(matched_keywords),
                inclusion_reason=reason,
                depends_on=node.depends_on,
            )
        return rationales

    @staticmethod
    def _prompt_tokens(prompt: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_]+", prompt.lower()))

    def _intent_capabilities_from_tokens(self, tokens: set[str]) -> set[str]:
        capabilities: set[str] = set()
        for keywords, mapped in _KEYWORD_BUCKETS:
            if keywords & tokens:
                capabilities.update(mapped)
        return capabilities

    def _intent_capabilities(self, prompt: str) -> set[str]:
        # Beibehalten fuer Tests / externe Aufrufer.
        return self._intent_capabilities_from_tokens(self._prompt_tokens(prompt))

    def _keywords_for_capabilities(
        self, agent_capabilities: set[str], prompt_tokens: set[str]
    ) -> set[str]:
        """Welche Prompt-Keywords haben dazu gefuehrt, dass dieser Agent
        relevant erscheint? (= Schnittmenge aus Buckets, deren Mapping mit
        `agent.capabilities` ueberlappt, und tatsaechlich vorhandenen Tokens.)
        """
        hits: set[str] = set()
        for keywords, mapped in _KEYWORD_BUCKETS:
            if mapped & agent_capabilities and keywords & prompt_tokens:
                hits.update(keywords & prompt_tokens)
        return hits

    def _agent_score(self, agent: AgentDefinition, intent_capabilities: set[str]) -> int:
        capability_overlap = len(set(agent.capabilities) & intent_capabilities)
        core_bonus = (
            2
            if agent.key
            in {"literature", "protocol", "materials", "budget", "timeline", "review", "validation"}
            else 0
        )
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
