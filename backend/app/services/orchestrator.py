from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from backend.app.config import Settings
from backend.app.schemas.plan import AgentEvent, ExperimentPlan, ExperimentRun, GeneratePlanRequest
from backend.app.services.agents import (
    build_title,
    budget_agent,
    default_validation,
    literature_scout,
    materials_agent,
    protocol_designer,
    review_agent,
    timeline_agent,
)
from backend.app.services.integrations import SupabaseRepository, TavilyClient

AGENT_TIMEOUT_S = 30
REVIEW_TIMEOUT_S = 20


class PlanGraphState(TypedDict, total=False):
    """LangGraph geteilter Zustand fuer den Plan-Pipeline."""

    prompt: str
    use_mock: bool
    streaming: bool
    experiment_type: str | None
    literature: dict[str, Any]
    protocol: dict[str, Any]
    materials: list[dict[str, Any]]
    budget: dict[str, Any]
    timeline: dict[str, Any]
    review_issues: list[dict[str, Any]]
    plan: dict[str, Any]
    run_id: str
    error: str | None


def _state_from_request(request: GeneratePlanRequest) -> PlanGraphState:
    return {
        "prompt": request.prompt,
        "use_mock": request.use_mock,
        "experiment_type": request.experiment_type,
        "error": None,
    }


class PlanOrchestrator:
    """Multi-Agent-Orchestrierung mit LangGraph (StateGraph, Fan-out/Fan-in)."""

    def __init__(self, settings: Settings, repository: SupabaseRepository):
        self._settings = settings
        self._repository = repository
        self._tavily = TavilyClient(settings)
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        tavily = self._tavily
        repository = self._repository

        async def publish_event(
            state: PlanGraphState,
            agent: str,
            phase: str,
            status: str,
            payload: dict[str, Any],
            message: str | None = None,
            from_agent: str | None = None,
            to_agent: str | None = None,
        ) -> None:
            run_id = state.get("run_id")
            if not run_id:
                return
            event = AgentEvent(
                run_id=run_id,
                sequence=0,
                agent=agent,
                phase=phase,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                payload=payload,
                message=message,
                from_agent=from_agent,
                to_agent=to_agent,
            )
            await repository.append_agent_event(event.model_dump(mode="json"))

        async def node_literature(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "literature", "progress", "started", {}, "Literature scout gestartet")
                lit = await asyncio.wait_for(
                    literature_scout(state["prompt"], tavily, self._settings, state["use_mock"]),
                    timeout=AGENT_TIMEOUT_S,
                )
                await publish_event(
                    state,
                    "literature",
                    "progress",
                    "completed",
                    {"literature": lit},
                    "Literaturrecherche abgeschlossen",
                )
                return {"literature": lit}
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "literature", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"literature: {exc!s}"}

        async def node_protocol(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "protocol", "progress", "started", {}, "Protocol agent gestartet")
                proto = await asyncio.wait_for(
                    protocol_designer(state["prompt"], self._settings, state["use_mock"]),
                    timeout=AGENT_TIMEOUT_S,
                )
                await publish_event(state, "protocol", "progress", "completed", {"protocol": proto}, "Protokoll erstellt")
                await publish_event(
                    state,
                    "protocol",
                    "progress",
                    "completed",
                    {"intent": "handoff_protocol_to_timeline"},
                    "Protocol an Timeline uebergeben",
                    from_agent="protocol",
                    to_agent="timeline",
                )
                return {"protocol": proto}
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "protocol", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"protocol: {exc!s}"}

        async def node_materials(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "materials", "progress", "started", {}, "Materials agent gestartet")
                raw = await asyncio.wait_for(
                    materials_agent(state["prompt"], self._settings, state["use_mock"]),
                    timeout=AGENT_TIMEOUT_S,
                )
                materials = raw["materials"] if isinstance(raw, dict) else raw
                await publish_event(
                    state,
                    "materials",
                    "progress",
                    "completed",
                    {"materials": materials},
                    "Materialliste erstellt",
                )
                return {"materials": raw["materials"]}
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "materials", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"materials: {exc!s}"}

        async def node_budget(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "budget", "progress", "started", {}, "Budget agent gestartet")
                b = await asyncio.wait_for(budget_agent(state["materials"]), timeout=AGENT_TIMEOUT_S)
                await publish_event(state, "budget", "progress", "completed", {"budget": b}, "Budget berechnet")
                return {"budget": b}
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "budget", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"budget: {exc!s}"}

        async def node_timeline(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "timeline", "progress", "started", {}, "Timeline agent gestartet")
                steps = state["protocol"].get("steps", [])
                tl = await asyncio.wait_for(timeline_agent(steps), timeout=AGENT_TIMEOUT_S)
                await publish_event(state, "timeline", "progress", "completed", {"timeline": tl}, "Timeline erstellt")
                return {"timeline": tl}
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "timeline", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"timeline: {exc!s}"}

        async def node_review(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {}
            try:
                await publish_event(state, "review", "progress", "started", {}, "Review agent gestartet")
                issues = await asyncio.wait_for(
                    review_agent(state["protocol"], state["materials"], state["budget"]),
                    timeout=REVIEW_TIMEOUT_S,
                )
                payload = {"review_issues": [issue.model_dump() for issue in issues]}
                await publish_event(state, "review", "progress", "completed", payload, "Review abgeschlossen")
                return payload
            except Exception as exc:  # noqa: BLE001
                await publish_event(state, "review", "error", "failed", {"error": str(exc)}, str(exc))
                return {"error": f"review: {exc!s}"}

        async def node_finalize(state: PlanGraphState) -> dict[str, Any]:
            if state.get("error"):
                return {"plan": {}, "error": state["error"]}
            meta: dict[str, Any] = {
                "experiment_type": state.get("experiment_type") or "general",
                "generated_by": "langgraph-orchestrator-v1",
            }
            if state.get("streaming"):
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
            nodes = [
                {
                    "id": f"kn-exp-{plan.plan_id}",
                    "title": plan.title,
                    "node_type": "experiment",
                    "content": plan.hypothesis,
                    "confidence_score": 0.7,
                    "times_applied": 1,
                    "tags": ["experiment", "auto-generated"],
                    "created_by": "ai-agent",
                }
            ]
            edges: list[dict[str, Any]] = []
            plan.knowledge_nodes_extracted = [node["id"] for node in nodes]
            await repository.save_plan(plan.model_dump(mode="json"))
            await repository.upsert_knowledge_nodes(nodes)
            await repository.add_knowledge_edges(edges)
            if state.get("run_id"):
                await repository.update_run(
                    state["run_id"],
                    {"status": "completed", "plan_id": plan.plan_id, "error_message": None},
                )
            await publish_event(
                state,
                "orchestrator",
                "complete",
                "completed",
                {"plan_id": plan.plan_id},
                "Run abgeschlossen",
            )
            return {"plan": plan.model_dump(mode="json")}

        builder = StateGraph(PlanGraphState)
        builder.add_node("literature", node_literature)
        builder.add_node("protocol", node_protocol)
        builder.add_node("materials", node_materials)
        builder.add_node("budget", node_budget)
        builder.add_node("timeline", node_timeline)
        builder.add_node("review", node_review)
        builder.add_node("finalize", node_finalize)

        builder.add_edge(START, "literature")
        builder.add_edge(START, "protocol")
        builder.add_edge(START, "materials")

        scout_join: list[str] = ["literature", "protocol", "materials"]
        builder.add_edge(scout_join, "budget")
        builder.add_edge(scout_join, "timeline")
        builder.add_edge(["budget", "timeline"], "review")
        builder.add_edge("review", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

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
        result = await self._graph.ainvoke({**_state_from_request(request), "run_id": resolved_run_id})
        if result.get("error"):
            msg = result["error"]
            await self._repository.update_run(resolved_run_id, {"status": "failed", "error_message": msg})
            raise RuntimeError(msg)
        plan_dict = result.get("plan")
        if not plan_dict:
            raise RuntimeError("Plan-Erzeugung ohne Ergebnis (finalize)")
        return ExperimentPlan.model_validate(plan_dict)

    def _sse_payload_for_node(self, node_name: str, update: dict[str, Any]) -> dict[str, Any]:
        if node_name == "literature" and "literature" in update:
            return update["literature"]
        if node_name == "protocol" and "protocol" in update:
            return update["protocol"]
        if node_name == "materials" and "materials" in update:
            return update["materials"]
        if node_name == "budget" and "budget" in update:
            return update["budget"]
        if node_name == "timeline" and "timeline" in update:
            return update["timeline"]
        if node_name == "review" and "review_issues" in update:
            return {"issues": update["review_issues"]}
        return update

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
        initial = _state_from_request(request)
        initial["streaming"] = True
        initial["run_id"] = run_id

        async for chunk in self._graph.astream(initial, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name == "finalize":
                    if update.get("error"):
                        yield {
                            "agent": "orchestrator",
                            "phase": "error",
                            "status": "failed",
                            "payload": {"message": update["error"]},
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        return
                    plan = update.get("plan")
                    if plan:
                        yield {
                            "agent": "orchestrator",
                            "phase": "complete",
                            "status": "completed",
                            "payload": {"plan": plan},
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    continue

                payload = self._sse_payload_for_node(node_name, update)
                yield {
                    "agent": node_name,
                    "phase": "progress",
                    "status": "completed",
                    "payload": payload,
                    "timestamp": datetime.utcnow().isoformat(),
                }
