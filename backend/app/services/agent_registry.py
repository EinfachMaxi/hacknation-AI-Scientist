from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.integrations import SupabaseRepository


@dataclass(frozen=True)
class AgentDefinition:
    id: str | None
    key: str
    name: str
    role: str
    personality: str
    capabilities: tuple[str, ...]
    prompt_template: str
    is_active: bool
    sort_order: int
    metadata: dict[str, Any]


DEFAULT_AGENT_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "planner",
        "name": "Planner LLM",
        "role": "Plan experiments and activate agents",
        "personality": "Strategic and decisive",
        "capabilities": ["planning", "orchestration"],
        "prompt_template": "Plan the experiment workflow and delegate tasks. Always communicate with other agents in English.",
        "is_active": True,
        "sort_order": 1,
        "metadata": {"role_kind": "planner"},
    },
    {
        "key": "literature",
        "name": "Literature Scout",
        "role": "Check novelty and references",
        "personality": "Precise and evidence-first",
        "capabilities": ["literature", "qc", "references"],
        "prompt_template": "Find similar work and novelty signal for the hypothesis.",
        "is_active": True,
        "sort_order": 10,
        "metadata": {
            "allowed_tools": ["tavily.search", "tavily.extract"],
            "max_tool_calls": 2,
            "max_results": 3,
        },
    },
    {
        "key": "protocol",
        "name": "Protocol Designer",
        "role": "Design experimental methodology",
        "personality": "Methodical and practical",
        "capabilities": ["protocol", "methodology"],
        "prompt_template": "Build protocol steps and controls.",
        "is_active": True,
        "sort_order": 20,
        "metadata": {
            "allowed_tools": ["tavily.search", "tavily.extract"],
            "max_tool_calls": 2,
            "include_domains": [
                "protocols.io",
                "nature.com",
                "bio-protocol.org",
            ],
        },
    },
    {
        "key": "materials",
        "name": "Materials Agent",
        "role": "List reagents and catalog numbers",
        "personality": "Catalog-accurate and cost-aware",
        "capabilities": ["materials", "catalog", "pricing"],
        "prompt_template": "Find materials with supplier and catalog number.",
        "is_active": True,
        "sort_order": 30,
        "metadata": {
            "allowed_tools": ["tavily.search", "tavily.extract"],
            "max_tool_calls": 3,
            "include_domains": [
                "sigmaaldrich.com",
                "thermofisher.com",
                "neb.com",
                "bio-rad.com",
                "abcam.com",
            ],
        },
    },
    {
        "key": "budget",
        "name": "Budget Agent",
        "role": "Estimate experiment costs",
        "personality": "Conservative and transparent",
        "capabilities": ["budget", "costing"],
        "prompt_template": "Calculate a detailed budget from materials.",
        "is_active": True,
        "sort_order": 40,
        "metadata": {
            "allowed_tools": ["tavily.extract"],
            "max_tool_calls": 2,
        },
    },
    {
        "key": "timeline",
        "name": "Timeline Agent",
        "role": "Create dependency-aware schedule",
        "personality": "Dependency-aware planner",
        "capabilities": ["timeline", "schedule", "dependencies"],
        "prompt_template": "Create timeline from protocol steps and dependencies.",
        "is_active": True,
        "sort_order": 50,
        "metadata": {
            "allowed_tools": ["tavily.search"],
            "max_tool_calls": 2,
            "include_domains": [
                "protocols.io",
                "nature.com",
                "bio-protocol.org",
            ],
        },
    },
    {
        "key": "review",
        "name": "Review Agent",
        "role": "Validate consistency across outputs",
        "personality": "Strict QA reviewer",
        "capabilities": ["review", "validation", "consistency"],
        "prompt_template": "Find internal issues and return warnings/errors.",
        "is_active": True,
        "sort_order": 60,
        "metadata": {
            "allowed_tools": ["tavily.search"],
            "max_tool_calls": 2,
        },
    },
    {
        "key": "validation",
        "name": "Validation Agent",
        "role": "Define hypothesis-specific success criteria, controls and stats plan",
        "personality": "Rigorous and measurement-driven",
        "capabilities": ["validation", "controls", "success_criteria", "statistics"],
        "prompt_template": (
            "Derive measurable success criteria, the required controls and a "
            "concrete statistical plan that fits the hypothesis, protocol and "
            "materials of this experiment."
        ),
        "is_active": True,
        "sort_order": 70,
        "metadata": {
            "allowed_tools": [],
            "max_tool_calls": 0,
            "depends_on": ["protocol", "materials"],
        },
    },
]


class AgentRegistry:
    def __init__(self, repository: SupabaseRepository) -> None:
        self._repository = repository

    async def get_active_agents(self) -> list[AgentDefinition]:
        rows = await self._repository.list_agents()
        if not rows:
            await self._repository.upsert_agents(DEFAULT_AGENT_DEFINITIONS)
            rows = await self._repository.list_agents()
        else:
            # Idempotenter Backfill: wenn die DB schon Agents kennt, aber neue
            # Default-Eintraege (z.B. der Validation-Agent) noch nicht vorhanden
            # sind, ergaenzen wir die fehlenden -- ohne bestehende Customizings
            # zu ueberschreiben.
            existing_keys = {row["key"] for row in rows if row.get("key")}
            missing = [
                definition
                for definition in DEFAULT_AGENT_DEFINITIONS
                if definition["key"] not in existing_keys
            ]
            if missing:
                await self._repository.upsert_agents(missing)
                rows = await self._repository.list_agents()

        return [
            AgentDefinition(
                id=row.get("id") or row["key"],
                key=row["key"],
                name=row["name"],
                role=row["role"],
                personality=row.get("personality") or "",
                capabilities=tuple(row.get("capabilities") or ()),
                prompt_template=row.get("prompt_template") or "",
                is_active=bool(row.get("is_active", True)),
                sort_order=int(row.get("sort_order") or 100),
                metadata=row.get("metadata") or {},
            )
            for row in rows
            if row.get("is_active", True)
        ]
