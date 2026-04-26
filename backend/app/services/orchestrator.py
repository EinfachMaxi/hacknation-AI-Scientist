from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import uuid4

from backend.app.config import Settings
from backend.app.schemas.plan import AgentEvent, ExperimentPlan, ExperimentRun, GeneratePlanRequest
from backend.app.services.agents import (
    build_title,
    run_dynamic_agent,
    validation_agent,
)
from backend.app.services.agent_registry import AgentDefinition, AgentRegistry
from backend.app.services.execution_plan import AgentRationale, ExecutionNode
from backend.app.services.integrations import SupabaseRepository, TavilyClient
from backend.app.services.message_bus import AgentBus, MessageBus
from backend.app.services.planner import Planner

AGENT_TIMEOUT_S = 120
REVIEW_TIMEOUT_S = 60
PLANNER_AGENT_KEY = "planner"
SPAWN_DELAY_S = 0.15

# Schwellenwerte fuer die Bedarfs-Heuristik.
MATERIALS_MIN_ITEMS = 2
PROTOCOL_LONG_STEPS = 8
BUDGET_HIGH_TOTAL = 500.0
REVIEW_MAX_ISSUES_TO_ASK = 2


def _rationale_to_dict(rationale: AgentRationale | None) -> dict[str, Any] | None:
    """JSON-fertige Repraesentation der Planner-Rationale.

    Wir wandeln die `AgentRationale` in ein flaches dict, damit es sicher in
    Supabase-jsonb (run_agents.metadata, agent_events.payload) wandern kann.
    """
    if rationale is None:
        return None
    return {
        "agent_key": rationale.agent_key,
        "score": rationale.score,
        "matched_capabilities": list(rationale.matched_capabilities),
        "matched_keywords": list(rationale.matched_keywords),
        "inclusion_reason": rationale.inclusion_reason,
        "depends_on": list(rationale.depends_on),
    }


def _assess_agent_needs(
    agent_key: str,
    output: Any,
    state: dict[str, Any],
) -> list[tuple[str, str]]:
    """Heuristik: Pruefe Agent-Output auf konkrete Luecken und leite nur dann
    eine Frage an einen anderen Agent ab.

    Im Mock-Modus mit sauberen Daten liefert das oft eine leere Liste -- der
    Agent ist eigenstaendig fertig. Im Real-Modus, wenn OpenAI/Tavily Probleme
    machen oder Outputs schwach sind, treten konkrete Bedarfe auf und es kommt
    zu echter Inter-Agent-Kommunikation.
    """
    needs: list[tuple[str, str]] = []

    if agent_key == "materials":
        materials = output if isinstance(output, list) else []
        if len(materials) < MATERIALS_MIN_ITEMS:
            needs.append(
                (
                    "literature",
                    f"Mein Katalog liefert nur {len(materials)} Eintrag/-e. "
                    "Welche Standard-Reagenzien werden in der Literatur empfohlen?",
                )
            )

    elif agent_key == "protocol":
        steps: list[Any] = []
        if isinstance(output, dict):
            raw_steps = output.get("steps") or []
            if isinstance(raw_steps, list):
                steps = raw_steps
        if len(steps) > PROTOCOL_LONG_STEPS:
            needs.append(
                (
                    "timeline",
                    f"Mein Protokoll hat {len(steps)} Schritte. Welche koennten "
                    "parallelisiert werden, um die Timeline zu kuerzen?",
                )
            )

    elif agent_key == "budget":
        total = 0.0
        if isinstance(output, dict):
            try:
                total = float(output.get("total", 0) or 0)
            except (TypeError, ValueError):
                total = 0.0
        if total <= 0:
            needs.append(
                (
                    "materials",
                    "Ich konnte kein Budget berechnen. Sind alle Materialien "
                    "mit Preisen gepflegt?",
                )
            )
        elif total > BUDGET_HIGH_TOTAL:
            needs.append(
                (
                    "materials",
                    f"Mein Budget liegt bei {total:.2f} EUR. Gibt es guenstigere "
                    "Lieferanten fuer die teuersten Posten?",
                )
            )

    elif agent_key == "timeline":
        phases: list[Any] = []
        if isinstance(output, dict):
            raw_phases = output.get("phases") or []
            if isinstance(raw_phases, list):
                phases = raw_phases
        if not phases:
            needs.append(
                (
                    "protocol",
                    "Ich konnte keine Phasen ableiten. Kannst du mir "
                    "Schrittdauern als Liste geben?",
                )
            )

    elif agent_key == "review":
        issues = output if isinstance(output, list) else []
        for issue in issues[:REVIEW_MAX_ISSUES_TO_ASK]:
            if not isinstance(issue, dict):
                continue
            path = str(issue.get("path", ""))
            severity = str(issue.get("severity", "warning"))
            target = None
            if path.startswith("protocol"):
                target = "protocol"
            elif path.startswith("materials"):
                target = "materials"
            elif path.startswith("budget"):
                target = "budget"
            elif path.startswith("timeline"):
                target = "timeline"
            if target:
                needs.append(
                    (
                        target,
                        f"Ich habe ein {severity}-Issue bei '{path}' gefunden. "
                        "Kannst du das bestaetigen oder einordnen?",
                    )
                )

    return needs


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

            agent_bus: AgentBus | None = state.get("agent_bus")

            # Bedarfsorientierte Inter-Agent-Kommunikation:
            # Der Agent prueft seinen eigenen Output und fragt nur dann einen
            # Kollegen, wenn ein konkreter Bedarf besteht (z.B. zu wenige
            # Materialien gefunden, Budget zu hoch, Review-Issue ungeklaert).
            # Bekommt er Antwort -> Hinweis im Output; bei Timeout macht er
            # weiter ohne Input.
            if agent_bus is not None:
                consultations: list[dict[str, Any]] = []
                for target_key, question in _assess_agent_needs(agent_key, output, state):
                    if target_key not in agent_id_by_key:
                        continue
                    answer = await agent_bus.ask(run_id, agent_key, target_key, question)
                    consultations.append(
                        {
                            "asked": target_key,
                            "question": question,
                            "answered": answer is not None,
                        }
                    )
                if consultations and isinstance(output, dict):
                    output.setdefault("_consultations", []).extend(consultations)

            if agent_bus is not None:
                agent_bus.mark_completed(agent_key, output)

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
        plan_start = datetime.utcnow()
        active_agents = await self._registry.get_active_agents()
        agent_by_key = {agent.key: agent for agent in active_agents}
        agent_id_by_key = {agent.key: str(agent.id) for agent in active_agents if agent.id}

        # 1. Planner-Node sofort als laufend anlegen, damit sie als einzige
        #    Node am Anfang im UI erscheint.
        planner_agent_id = agent_id_by_key.get(PLANNER_AGENT_KEY)
        if planner_agent_id:
            await self._repository.create_run_agents(
                [
                    {
                        "run_id": run_id,
                        "agent_id": planner_agent_id,
                        "status": "running",
                        "progress_pct": 5,
                        "started_at": datetime.utcnow().isoformat(),
                    }
                ]
            )
            await self._message_bus.publish_event(
                run_id,
                agent=PLANNER_AGENT_KEY,
                phase="starting",
                status="started",
                message="Planner LLM analysiert Hypothese.",
                agent_id=planner_agent_id,
            )

        # 2. Plan generieren (selber Schritt; deterministisch + schnell).
        execution_plan = self._planner.create_execution_plan(request.prompt, active_agents)

        # 3. Andere Agenten Schritt fuer Schritt spawnen, damit sie im UI
        #    nacheinander aufploppen und Edges vom Planner sichtbar werden.
        for index, node in enumerate(execution_plan.nodes, start=1):
            if node.agent_key == PLANNER_AGENT_KEY:
                continue
            agent_id = agent_id_by_key[node.agent_key]
            await asyncio.sleep(SPAWN_DELAY_S)
            rationale = execution_plan.rationales.get(node.agent_key)
            rationale_payload = _rationale_to_dict(rationale)
            run_agent_row: dict[str, Any] = {
                "run_id": run_id,
                "agent_id": agent_id,
                "status": "ready",
                "progress_pct": 0,
            }
            if rationale_payload:
                # `metadata` haelt die strukturierte Begruendung -- der
                # Why-this-agent-Inspector liest sie ueber `/runs/.../graph`.
                run_agent_row["metadata"] = {"rationale": rationale_payload}
            await self._repository.create_run_agents([run_agent_row])
            if planner_agent_id:
                progress = min(95, 20 + index * 12)
                await self._repository.update_run_agent(
                    run_id,
                    planner_agent_id,
                    {"status": "running", "progress_pct": progress},
                )
            spawn_payload: dict[str, Any] = {
                "action": "spawn",
                "agent": node.agent_key,
            }
            if rationale_payload:
                spawn_payload["rationale"] = rationale_payload
            await self._message_bus.publish_message(
                run_id,
                message_type="handoff",
                from_agent_id=planner_agent_id,
                to_agent_id=agent_id,
                from_agent=PLANNER_AGENT_KEY,
                to_agent=node.agent_key,
                subject=f"spawn::{node.agent_key}",
                message=f"Planner aktiviert {agent_by_key[node.agent_key].name}.",
                payload=spawn_payload,
            )
            event_payload: dict[str, Any] = {}
            if rationale_payload:
                event_payload["rationale"] = rationale_payload
            await self._message_bus.publish_event(
                run_id,
                agent=node.agent_key,
                phase="starting",
                status="started",
                from_agent=PLANNER_AGENT_KEY,
                to_agent=node.agent_key,
                message=f"Planner spawnt {node.agent_key}.",
                agent_id=agent_id,
                payload=event_payload or None,
            )

        # 4. Planner als abgeschlossen markieren.
        if planner_agent_id:
            await self._repository.update_run_agent(
                run_id,
                planner_agent_id,
                {
                    "status": "completed",
                    "progress_pct": 100,
                    "completed_at": datetime.utcnow().isoformat(),
                },
            )
            await self._message_bus.publish_event(
                run_id,
                agent=PLANNER_AGENT_KEY,
                phase="complete",
                status="completed",
                message="Planner LLM hat alle Agenten aktiviert.",
                agent_id=planner_agent_id,
            )

        # 5. Bus fuer Inter-Agent-Kommunikation aufsetzen.
        agent_bus = AgentBus(self._message_bus, agent_id_by_key)

        # 5a. Learn-from-corrections-Loop: relevante User-Korrekturen einmal
        #     pro Run laden, gruppiert pro Agent. `run_dynamic_agent` zieht
        #     daraus seine Few-Shot-Beispiele.
        from backend.app.services.pkm import recall_corrections as _recall_corrections

        try:
            corrections_by_agent = await _recall_corrections(
                self._repository,
                experiment_type=request.experiment_type,
                limit=6,
            )
        except Exception:  # noqa: BLE001
            corrections_by_agent = {}

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
            "validation": {},
            "agent_bus": agent_bus,
            "run_id": run_id,
            "corrections": corrections_by_agent,
        }
        for level in execution_plan.levels:
            tasks = [self._run_node(run_id, state, node, agent_id_by_key, agent_by_key) for node in level]
            results = await asyncio.gather(*tasks)
            for output_key, output in results:
                state[output_key] = output

        plan_end = datetime.utcnow()
        generation_seconds = max(0.0, (plan_end - plan_start).total_seconds())
        # Heuristik fuer "Wieviel Researcher-Zeit haetten wir manuell gebraucht?"
        # Reine Faustformel: pro Protocol-Step 30 min Recherche/Schreiben,
        # pro Material 5 min Catalog-Lookup, +60 min Doc-Aufbau. Wir setzen das
        # explizit ins metadata, damit das Frontend keinen eigenen Heuristik-
        # Code braucht und der Wert im Plan-PDF stabil ist.
        steps_count = (
            len(state["protocol"].get("steps", [])) if isinstance(state.get("protocol"), dict) else 0
        )
        materials_count = (
            len(state["materials"]) if isinstance(state.get("materials"), list) else 0
        )
        manual_minutes_estimate = steps_count * 30 + materials_count * 5 + 60

        applied_corrections_total = sum(
            len(items) for items in (corrections_by_agent or {}).values()
        )
        meta: dict[str, Any] = {
            "experiment_type": state.get("experiment_type") or "general",
            "generated_by": "dynamic-orchestrator-v2",
            "orchestration_mode": "dynamic_db_registry",
            "tool_calling_enabled": self._settings.agent_tool_calling_enabled,
            "generation_seconds": round(generation_seconds, 2),
            "manual_minutes_estimate": manual_minutes_estimate,
            "applied_corrections_total": applied_corrections_total,
            "applied_corrections_by_agent": {
                k: len(v) for k, v in (corrections_by_agent or {}).items()
            },
        }
        if streaming:
            meta["streaming"] = True

        # Validation kommt jetzt regulaer aus dem DAG (Knoten "validation").
        # Falls der Knoten nicht im Plan war (z.B. weil die Registry den Agent
        # nicht kennt), greift ein Legacy-Fallback auf den Direktaufruf, damit
        # bestehende Setups keinen leeren Validation-Tab kriegen.
        validation = state.get("validation")
        if not isinstance(validation, dict) or not validation:
            validation = await validation_agent(
                state["prompt"],
                state["protocol"] if isinstance(state.get("protocol"), dict) else {},
                state["materials"] if isinstance(state.get("materials"), list) else [],
                self._settings,
                request.use_mock,
            )
            meta["validation_fallback"] = "legacy_direct_call"
        plan = ExperimentPlan(
            title=build_title(state["prompt"]),
            hypothesis=state["prompt"],
            literature_qc=state["literature"],
            protocol=state["protocol"],
            materials=state["materials"],
            budget=state["budget"],
            timeline=state["timeline"],
            validation=validation,
            review_issues=state.get("review_issues", []),
            metadata=meta,
        )
        # WICHTIG: Knowledge-Graph wird NICHT mehr automatisch beschrieben.
        # Der Plan ist ein DRAFT, bis der User explizit "Accept" drückt.
        # Wir merken uns lediglich die ID des potenziellen Experiment-Knotens
        # für die spätere Ingest-Stufe.
        from backend.app.services.pkm import (
            candidate_summary,
            extract_knowledge_candidates,
        )

        candidates = extract_knowledge_candidates(plan)
        plan.knowledge_nodes_extracted = [n.id for n in candidates.nodes]
        if isinstance(plan.metadata, dict):
            plan.metadata["candidate_summary"] = candidate_summary(candidates)
            plan.metadata["graph_status"] = "draft"
        await self._repository.save_plan(plan.model_dump(mode="json"))
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
