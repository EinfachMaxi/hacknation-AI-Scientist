from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import uuid4

from backend.app.config import Settings
from backend.app.schemas.plan import AgentEvent, ExperimentPlan, ExperimentRun, GeneratePlanRequest
from backend.app.services.agents import (
    build_title,
    default_validation,
    run_dynamic_agent,
)
from backend.app.services.agent_registry import AgentDefinition, AgentRegistry
from backend.app.services.execution_plan import ExecutionNode
from backend.app.services.integrations import SupabaseRepository, TavilyClient
from backend.app.services.message_bus import MessageBus
from backend.app.services.planner import Planner

AGENT_TIMEOUT_S = 30
REVIEW_TIMEOUT_S = 20


class PlanOrchestrator:
    """Dynamische Agent-Orchestrierung per DB-Registry und Planner-DAG."""

    def __init__(self, settings: Settings, repository: SupabaseRepository):
        self._settings = settings
        self._repository = repository
        self._tavily = TavilyClient(settings)
        self._registry = AgentRegistry(repository)
        self._planner = Planner()
        self._message_bus = MessageBus(repository)

    async def _run_node(
        self,
        run_id: str,
        state: dict[str, Any],
        node: ExecutionNode,
        agent_id_by_key: dict[str, str],
        agent_by_key: dict[str, AgentDefinition],
    ) -> tuple[str, Any]:
        agent_key = node.agent_key
        agent_id = agent_id_by_key[agent_key]
        agent = agent_by_key[agent_key]
        await self._repository.update_run_agent(
            run_id,
            agent_id,
            {"status": "running", "progress_pct": 5, "started_at": datetime.utcnow().isoformat()},
        )
        await self._message_bus.publish_event(
            run_id,
            agent=agent_key,
            phase="progress",
            status="started",
            message=f"{agent_key} gestartet",
            agent_id=agent_id,
        )
        for upstream in node.depends_on:
            await self._message_bus.publish_message(
                run_id,
                message_type="handoff",
                from_agent_id=agent_id_by_key[upstream],
                to_agent_id=agent_id,
                from_agent=upstream,
                to_agent=agent_key,
                subject=f"{upstream}_to_{agent_key}",
                message=f"Handoff von {upstream} an {agent_key}",
                payload={"from": upstream, "to": agent_key},
            )

        try:
            timeout = REVIEW_TIMEOUT_S if agent_key == "review" else AGENT_TIMEOUT_S
            output, tool_traces = await asyncio.wait_for(
                run_dynamic_agent(
                    agent,
                    prompt=state["prompt"],
                    settings=self._settings,
                    use_mock=state["use_mock"],
                    tavily=self._tavily,
                    state=state,
                ),
                timeout=timeout,
            )
            for trace in tool_traces:
                await self._message_bus.publish_message(
                    run_id,
                    message_type="request",
                    from_agent_id=agent_id,
                    to_agent_id=agent_id,
                    from_agent=agent_key,
                    to_agent=agent_key,
                    subject=f"tool::{trace.get('tool')}",
                    message=f"Tool-Call {trace.get('tool')} ({trace.get('status')})",
                    payload={"tool_trace": trace},
                )

            await self._repository.update_run_agent(
                run_id,
                agent_id,
                {"status": "completed", "progress_pct": 100, "completed_at": datetime.utcnow().isoformat()},
            )
            await self._message_bus.publish_event(
                run_id,
                agent=agent_key,
                phase="progress",
                status="completed",
                payload={node.output_key: output},
                message=f"{agent_key} abgeschlossen",
                agent_id=agent_id,
            )
            return node.output_key, output
        except Exception as exc:  # noqa: BLE001
            await self._repository.update_run_agent(
                run_id,
                agent_id,
                {"status": "failed", "progress_pct": 100, "error_message": str(exc), "completed_at": datetime.utcnow().isoformat()},
            )
            await self._message_bus.publish_event(
                run_id,
                agent=agent_key,
                phase="error",
                status="failed",
                payload={"error": str(exc)},
                message=str(exc),
                agent_id=agent_id,
            )
            raise

    async def _execute_dynamic_plan(
        self,
        request: GeneratePlanRequest,
        run_id: str,
        *,
        streaming: bool,
    ) -> ExperimentPlan:
        active_agents = await self._registry.get_active_agents()
        execution_plan = self._planner.create_execution_plan(request.prompt, active_agents)
        agent_by_key = {agent.key: agent for agent in active_agents}
        agent_id_by_key = {agent.key: str(agent.id) for agent in active_agents if agent.id}
        run_agent_rows = [
            {"run_id": run_id, "agent_id": agent_id_by_key[node.agent_key], "status": "pending", "progress_pct": 0}
            for node in execution_plan.nodes
        ]
        await self._repository.create_run_agents(run_agent_rows)

        state: dict[str, Any] = {
            "prompt": request.prompt,
            "use_mock": request.use_mock,
            "experiment_type": request.experiment_type,
            "literature": {},
            "protocol": {},
            "materials": [],
            "budget": {},
            "timeline": {},
            "review_issues": [],
        }
        for level in execution_plan.levels:
            tasks = [self._run_node(run_id, state, node, agent_id_by_key, agent_by_key) for node in level]
            results = await asyncio.gather(*tasks)
            for output_key, output in results:
                state[output_key] = output

        meta: dict[str, Any] = {
            "experiment_type": state.get("experiment_type") or "general",
            "generated_by": "dynamic-orchestrator-v2",
            "orchestration_mode": "dynamic_db_registry",
            "tool_calling_enabled": self._settings.agent_tool_calling_enabled,
        }
        if streaming:
            meta["streaming"] = True
        plan = ExperimentPlan(
            title=build_title(state["prompt"]),
            hypothesis=state["prompt"],
            literature_qc=state["literature"],
            protocol=state["protocol"],
            materials=state["materials"],
            budget=state["budget"],
            timeline=state["timeline"],
            validation=default_validation(),
            review_issues=state.get("review_issues", []),
            metadata=meta,
        )
        node = {
            "id": f"kn-exp-{plan.plan_id}",
            "title": plan.title,
            "node_type": "experiment",
            "content": plan.hypothesis,
            "confidence_score": 0.7,
            "times_applied": 1,
            "tags": ["experiment", "auto-generated"],
            "created_by": "ai-agent",
        }
        plan.knowledge_nodes_extracted = [node["id"]]
        await self._repository.save_plan(plan.model_dump(mode="json"))
        await self._repository.upsert_knowledge_nodes([node])
        await self._repository.add_knowledge_edges([])
        await self._repository.update_run(
            run_id,
            {"status": "completed", "plan_id": plan.plan_id, "error_message": None},
        )
        await self._message_bus.publish_event(
            run_id,
            agent="orchestrator",
            phase="complete",
            status="completed",
            payload={"plan_id": plan.plan_id},
            message="Run abgeschlossen",
        )
        return plan

    async def build_plan(
        self,
        request: GeneratePlanRequest,
        run_id: str | None = None,
        create_run: bool = True,
    ) -> ExperimentPlan:
        resolved_run_id = run_id or str(uuid4())
        if create_run:
            run = ExperimentRun(
                run_id=resolved_run_id,
                hypothesis=request.prompt,
                experiment_type=request.experiment_type,
                status="running",
            )
            await self._repository.create_run(run.model_dump(mode="json"))
        try:
            return await self._execute_dynamic_plan(request, resolved_run_id, streaming=False)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            await self._repository.update_run(resolved_run_id, {"status": "failed", "error_message": msg})
            raise RuntimeError(msg)

    async def stream_plan(self, request: GeneratePlanRequest) -> AsyncGenerator[dict[str, Any], None]:
        started_at = datetime.utcnow().isoformat()
        yield {
            "agent": "orchestrator",
            "phase": "starting",
            "status": "started",
            "payload": {"message": "LangGraph-Orchestrator gestartet"},
            "timestamp": started_at,
        }
        run_id = str(uuid4())
        run = ExperimentRun(
            run_id=run_id,
            hypothesis=request.prompt,
            experiment_type=request.experiment_type,
            status="running",
        )
        await self._repository.create_run(run.model_dump(mode="json"))
        await self._repository.append_agent_event(
            AgentEvent(
                run_id=run_id,
                sequence=0,
                agent="orchestrator",
                phase="starting",
                status="started",
                payload={"message": "Run gestartet"},
                message="Run gestartet",
            ).model_dump(mode="json")
        )
        try:
            plan = await self._execute_dynamic_plan(request, run_id, streaming=True)
            yield {
                "agent": "orchestrator",
                "phase": "complete",
                "status": "completed",
                "payload": {"plan": plan.model_dump(mode="json")},
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            await self._repository.update_run(run_id, {"status": "failed", "error_message": str(exc)})
            yield {
                "agent": "orchestrator",
                "phase": "error",
                "status": "failed",
                "payload": {"message": str(exc)},
                "timestamp": datetime.utcnow().isoformat(),
            }
