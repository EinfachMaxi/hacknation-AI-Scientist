from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.config import Settings, get_settings
from backend.app.schemas.plan import (
    AcceptDraftResponse,
    AgentMessage,
    AgentEvent,
    CorrectionRequest,
    ExperimentPlan,
    ExperimentRun,
    ExperimentSummary,
    GeneratePlanRequest,
    KnowledgeCandidates,
    KnowledgeChatCitation,
    KnowledgeChatRequest,
    KnowledgeChatResponse,
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeProposal,
    KnowledgeProposalCreate,
    RunGraphEdge,
    RunGraphMeta,
    RunGraphNode,
    RunGraphNodeRationale,
    RunGraphNodeTooling,
    RunGraphSnapshot,
    StartRunRequest,
    StartRunResponse,
)
from backend.app.services.agent_registry import AgentRegistry
from backend.app.services.integrations import SupabaseRepository, TavilyClient
from backend.app.services.orchestrator import PlanOrchestrator
from backend.app.services import pkm as pkm_service

app = FastAPI(title="Dr. Nexus Backend", version="0.1.0")
settings = get_settings()
repository = SupabaseRepository(settings)
origins = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_orchestrator(settings: Settings = Depends(get_settings)) -> PlanOrchestrator:
    return PlanOrchestrator(settings=settings, repository=repository)


def _api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _safe_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/providers")
async def health_providers() -> dict:
    providers: dict[str, dict[str, str | bool]] = {
        "tavily": {"configured": bool(settings.tavily_api_key), "status": "not_configured"},
        "openai": {"configured": bool(settings.openai_api_key), "status": "not_configured"},
    }

    if settings.tavily_api_key:
        try:
            tavily = TavilyClient(settings)
            await tavily.search("healthcheck")
            providers["tavily"]["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            providers["tavily"]["status"] = "error"
            providers["tavily"]["message"] = str(exc)[:250]

    if settings.openai_api_key:
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://api.openai.com/v1/models", headers=headers)
            if response.status_code < 400:
                providers["openai"]["status"] = "ok"
            else:
                providers["openai"]["status"] = "error"
                providers["openai"]["message"] = response.text[:250]
        except Exception as exc:  # noqa: BLE001
            providers["openai"]["status"] = "error"
            providers["openai"]["message"] = str(exc)[:250]

    return {"providers": providers, "tool_calling_enabled": settings.agent_tool_calling_enabled}


@app.get("/agents")
async def list_agents() -> dict:
    """Liste der aktiven Agenten aus der Registry.

    Wird von der Frontend-`/agents`-Seite genutzt, damit dort die echten
    Backend-Agenten angezeigt werden statt einer statischen Liste.
    """
    registry = AgentRegistry(repository)
    agents = await registry.get_active_agents()
    return {
        "agents": [
            {
                "id": agent.id,
                "key": agent.key,
                "name": agent.name,
                "role": agent.role,
                "personality": agent.personality,
                "capabilities": list(agent.capabilities),
                "is_active": agent.is_active,
                "sort_order": agent.sort_order,
                "metadata": agent.metadata,
            }
            for agent in sorted(agents, key=lambda a: a.sort_order)
        ]
    }


@app.post("/runs", response_model=StartRunResponse)
async def start_run(
    request: StartRunRequest,
    orchestrator: PlanOrchestrator = Depends(get_orchestrator),
) -> StartRunResponse:
    run_id = f"run-{uuid4().hex[:12]}"
    await repository.create_run(
        ExperimentRun(
            run_id=run_id,
            hypothesis=request.prompt,
            experiment_type=request.experiment_type,
            status="running",
        ).model_dump(mode="json")
    )

    async def _execute() -> None:
        payload = GeneratePlanRequest(
            prompt=request.prompt,
            experiment_type=request.experiment_type,
            use_mock=request.use_mock,
        )
        try:
            plan = await orchestrator.build_plan(payload, run_id=run_id, create_run=False)
            await repository.update_run(run_id, {"status": "completed", "plan_id": plan.plan_id})
        except Exception as exc:  # noqa: BLE001
            await repository.update_run(run_id, {"status": "failed", "error_message": str(exc)})

    asyncio.create_task(_execute())
    return StartRunResponse(run_id=run_id, status="running")


@app.get("/runs/{run_id}", response_model=ExperimentRun)
async def get_run(run_id: str) -> ExperimentRun:
    run = await repository.get_run(run_id)
    if not run:
        raise _api_error(404, "run_not_found", "Run not found")
    return ExperimentRun.model_validate(run)


@app.get("/runs/{run_id}/events", response_model=list[AgentEvent])
async def get_run_events(run_id: str) -> list[AgentEvent]:
    run = await repository.get_run(run_id)
    if not run:
        raise _api_error(404, "run_not_found", "Run not found")
    events = await repository.list_run_events(run_id)
    return [AgentEvent.model_validate(event) for event in events]


@app.get("/runs/{run_id}/messages", response_model=list[AgentMessage])
async def get_run_messages(run_id: str) -> list[AgentMessage]:
    run = await repository.get_run(run_id)
    if not run:
        raise _api_error(404, "run_not_found", "Run not found")
    messages = await repository.list_run_messages(run_id)
    return [AgentMessage.model_validate(message) for message in messages]


@app.get("/runs/{run_id}/graph", response_model=RunGraphSnapshot)
async def get_run_graph(run_id: str, app_settings: Settings = Depends(get_settings)) -> RunGraphSnapshot:
    run = await repository.get_run(run_id)
    if not run:
        raise _api_error(404, "run_not_found", "Run not found")

    registry = AgentRegistry(repository)
    agents = await registry.get_active_agents()
    run_agents = await repository.list_run_agents(run_id)
    run_agent_by_id = {str(row.get("agent_id")): row for row in run_agents}

    events = await repository.list_run_events(run_id)
    messages = await repository.list_run_messages(run_id)

    node_by_key: dict[str, RunGraphNode] = {}
    for agent in agents:
        run_agent = run_agent_by_id.get(str(agent.id))
        state = str(run_agent.get("status", "pending")) if run_agent else "pending"
        progress_pct = int(run_agent.get("progress_pct", 0)) if run_agent else 0
        tool_messages = [
            msg
            for msg in messages
            if msg.get("from_agent") == agent.key
            and isinstance(msg.get("payload"), dict)
            and isinstance(msg.get("payload", {}).get("tool_trace"), dict)
        ]
        last_tool_status = None
        if tool_messages:
            trace = tool_messages[-1].get("payload", {}).get("tool_trace", {})
            if isinstance(trace, dict):
                last_tool_status = trace.get("status")
        allowed_tools = []
        metadata = agent.metadata if isinstance(agent.metadata, dict) else {}
        if isinstance(metadata.get("allowed_tools"), list):
            allowed_tools = [str(tool) for tool in metadata["allowed_tools"]]
        rationale_obj: RunGraphNodeRationale | None = None
        run_agent_meta = (
            run_agent.get("metadata")
            if run_agent and isinstance(run_agent.get("metadata"), dict)
            else None
        )
        rationale_payload = (
            run_agent_meta.get("rationale") if isinstance(run_agent_meta, dict) else None
        )
        if isinstance(rationale_payload, dict):
            try:
                rationale_obj = RunGraphNodeRationale.model_validate(rationale_payload)
            except Exception:  # noqa: BLE001
                rationale_obj = None
        node_by_key[agent.key] = RunGraphNode(
            id=agent.key,
            label=agent.name,
            role=agent.role,
            personality=agent.personality,
            state=state,  # type: ignore[arg-type]
            progress_pct=progress_pct,
            tooling=RunGraphNodeTooling(
                allowed_tools=allowed_tools,
                tool_calls_count=len(tool_messages),
                last_tool_status=last_tool_status,
            ),
            rationale=rationale_obj,
        )

    edges_map: dict[tuple[str, str], RunGraphEdge] = {}
    for event in events:
        src = event.get("from_agent")
        dst = event.get("to_agent")
        if not src or not dst:
            continue
        key = (str(src), str(dst))
        last_activity = _safe_dt(event.get("timestamp"))
        edge_state = "active"
        if event.get("phase") == "error" or event.get("status") == "failed":
            edge_state = "failed"
        elif event.get("phase") == "complete" or event.get("status") == "completed":
            edge_state = "completed"
        edges_map[key] = RunGraphEdge(
            from_=key[0],
            to=key[1],
            state=edge_state,  # type: ignore[arg-type]
            last_message_type="event",
            last_activity_at=last_activity,
        )

    for message in messages:
        src = message.get("from_agent")
        dst = message.get("to_agent")
        if not src or not dst:
            continue
        key = (str(src), str(dst))
        created_at = _safe_dt(message.get("created_at"))
        current = edges_map.get(key)
        edge_state = "active"
        if current and current.state == "failed":
            edge_state = "failed"
        elif current and current.state == "completed":
            edge_state = "completed"
        edge = RunGraphEdge(
            from_=key[0],
            to=key[1],
            state=edge_state,  # type: ignore[arg-type]
            last_message_type=str(message.get("message_type")) if message.get("message_type") else None,
            last_activity_at=created_at,
            last_tool_activity_at=current.last_tool_activity_at if current else None,
            last_tool_name=current.last_tool_name if current else None,
            last_tool_error=current.last_tool_error if current else None,
        )
        payload = message.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("tool_trace"), dict):
            trace = payload["tool_trace"]
            edge.last_tool_activity_at = created_at
            edge.last_tool_name = str(trace.get("tool")) if trace.get("tool") else None
            if trace.get("status") and trace.get("status") != "ok":
                edge.last_tool_error = str(trace.get("error") or trace.get("status"))
                edge.state = "failed"
        edges_map[key] = edge

    updated_candidates = [
        _safe_dt(run.get("updated_at")),
        *(_safe_dt(event.get("timestamp")) for event in events),
        *(_safe_dt(message.get("created_at")) for message in messages),
    ]
    updated_at = max((dt for dt in updated_candidates if dt), default=datetime.utcnow())
    return RunGraphSnapshot(
        nodes=list(node_by_key.values()),
        edges=list(edges_map.values()),
        meta=RunGraphMeta(
            run_status=run.get("status", "running"),
            updated_at=updated_at,
            version="v1",
            tool_calling_enabled=app_settings.agent_tool_calling_enabled,
        ),
    )


@app.get("/runs/{run_id}/plan", response_model=ExperimentPlan)
async def get_run_plan(run_id: str) -> ExperimentPlan:
    run = await repository.get_run(run_id)
    if not run:
        raise _api_error(404, "run_not_found", "Run not found")
    if run.get("status") == "failed":
        raise _api_error(409, "run_failed", run.get("error_message") or "Run failed")
    plan_id = run.get("plan_id")
    if not plan_id:
        raise _api_error(404, "plan_not_ready", "Plan not ready")
    row = await repository.get_plan(plan_id)
    if not row:
        raise _api_error(404, "plan_not_found", "Plan not found")
    return ExperimentPlan.model_validate(row)


@app.post("/generate-plan", response_model=ExperimentPlan)
async def generate_plan(
    request: GeneratePlanRequest,
    orchestrator: PlanOrchestrator = Depends(get_orchestrator),
) -> ExperimentPlan:
    return await orchestrator.build_plan(request)


@app.post("/generate-plan/stream")
async def generate_plan_stream(
    request: GeneratePlanRequest,
    orchestrator: PlanOrchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in orchestrator.stream_plan(request):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001
            error_event = {
                "agent": "orchestrator",
                "phase": "error",
                "status": "failed",
                "payload": {"message": str(exc)},
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/plans", response_model=list[ExperimentSummary])
async def list_plans() -> list[ExperimentSummary]:
    rows = await repository.list_plans()
    return [
        ExperimentSummary(
            plan_id=row["plan_id"],
            title=row["title"],
            hypothesis=row["hypothesis"],
            generated_at=row["generated_at"],
        )
        for row in rows
    ]


@app.get("/plans/{plan_id}", response_model=ExperimentPlan)
async def get_plan(plan_id: str) -> ExperimentPlan:
    row = await repository.get_plan(plan_id)
    if not row:
        raise _api_error(404, "plan_not_found", "Plan not found")
    return ExperimentPlan.model_validate(row)


@app.get("/knowledge")
async def list_knowledge(status: str = "active") -> dict:
    return await repository.list_knowledge(status=status)


@app.post("/plans/{plan_id}/corrections")
async def add_correction(plan_id: str, correction: CorrectionRequest) -> dict:
    node_id = f"kn-correction-{plan_id}-{abs(hash(correction.field_path + correction.new_value)) % 100000}"
    node = {
        "id": node_id,
        "title": f"Correction: {correction.field_path}",
        "node_type": "correction",
        "experiment_type": correction.experiment_type,
        "content": f"{correction.old_value} -> {correction.new_value}. Reason: {correction.reason}",
        "metadata": correction.model_dump(),
        "confidence": 0.8,
        "times_applied": 1,
        "status": "active",
        "source_type": "user_correction",
        "source_ref": plan_id,
        "created_by": "scientist-review",
        "tags": ["correction", correction.experiment_type],
    }
    edge = {
        "source_id": f"kn-exp-{plan_id}",
        "target_id": node_id,
        "relationship_type": "corrects",
        "weight": 1.0,
        "source_type": "user_correction",
        "source_ref": plan_id,
    }
    await repository.upsert_knowledge_nodes([node])
    await repository.add_knowledge_edges([edge])
    return {"status": "stored", "node_id": node_id}


# === Knowledge Graph: Accept-Draft, Chat, Proposals ========================


async def _ingest_candidates_with_dedupe(
    plan_id: str,
    candidates: KnowledgeCandidates,
    settings: Settings,
) -> tuple[int, int, int]:
    """Embeddings + Dedupe + Upsert. Liefert (inserted, merged, edges)."""
    # Embeddings für Kandidaten erzeugen
    texts = [pkm_service._node_text_for_embedding(node) for node in candidates.nodes]
    vectors = await pkm_service.embed_texts(settings, texts)

    # Existierende Knoten je Type laden (mit Embedding für Cosine-Vergleich)
    existing_by_type: dict[str, list[dict]] = {}
    for node in candidates.nodes:
        if node.node_type not in existing_by_type:
            existing_by_type[node.node_type] = await repository.list_knowledge_node_ids(
                node_type=node.node_type, status="active"
            )

    inserted = 0
    merged = 0
    nodes_to_upsert: list[dict] = []
    id_remap: dict[str, str] = {}

    for node, vector in zip(candidates.nodes, vectors, strict=False):
        existing = pkm_service.find_duplicate(
            node, existing_by_type.get(node.node_type, []), vector
        )
        if existing:
            await repository.increment_knowledge_node_usage(existing["id"])
            id_remap[node.id] = existing["id"]
            merged += 1
            continue

        row = node.model_dump(mode="json")
        row["status"] = "active"
        row["source_ref"] = plan_id
        row["source_type"] = node.source_type or "plan_draft"
        if vector is not None:
            row["embedding"] = vector
        nodes_to_upsert.append(row)
        inserted += 1

    if nodes_to_upsert:
        await repository.upsert_knowledge_nodes(nodes_to_upsert)

    # Edges remappen falls Source/Target dedupliziert wurden, dann einfügen.
    edge_rows: list[dict] = []
    for edge in candidates.edges:
        source = id_remap.get(edge.source_id, edge.source_id)
        target = id_remap.get(edge.target_id, edge.target_id)
        edge_rows.append(
            {
                "source_id": source,
                "target_id": target,
                "relationship_type": edge.relationship_type,
                "weight": edge.weight,
                "source_type": edge.source_type or "plan_draft",
                "source_ref": plan_id,
            }
        )
    if edge_rows:
        await repository.add_knowledge_edges(edge_rows)

    return inserted, merged, len(edge_rows)


@app.post("/plans/{plan_id}/accept", response_model=AcceptDraftResponse)
async def accept_plan_draft(
    plan_id: str,
    app_settings: Settings = Depends(get_settings),
) -> AcceptDraftResponse:
    """Akzeptiere einen Draft → Wissen-Kandidaten extrahieren, dedupen, upserten."""
    row = await repository.get_plan(plan_id)
    if not row:
        raise _api_error(404, "plan_not_found", "Plan not found")
    plan = ExperimentPlan.model_validate(row)
    candidates = pkm_service.extract_knowledge_candidates(plan)

    inserted, merged, edges_count = await _ingest_candidates_with_dedupe(
        plan_id, candidates, app_settings
    )

    if isinstance(plan.metadata, dict):
        plan.metadata["graph_status"] = "active"
        plan.metadata["accepted_at"] = datetime.utcnow().isoformat()
        await repository.save_plan(plan.model_dump(mode="json"))

    return AcceptDraftResponse(
        plan_id=plan_id,
        inserted_nodes=inserted,
        merged_nodes=merged,
        inserted_edges=edges_count,
        candidate_summary=pkm_service.candidate_summary(candidates),
    )


@app.post("/knowledge/chat", response_model=KnowledgeChatResponse)
async def knowledge_chat(
    request: KnowledgeChatRequest,
    app_settings: Settings = Depends(get_settings),
) -> KnowledgeChatResponse:
    """Graph-grounded Q&A mit Citation-Pflicht."""
    embeddings = await pkm_service.embed_texts(app_settings, [request.query])
    query_embedding = embeddings[0] if embeddings else None

    rows = await repository.search_knowledge(
        query_text=request.query,
        query_embedding=query_embedding,
        experiment_type=request.experiment_type,
        match_count=max(1, min(20, request.top_k)),
    )

    citations = [
        KnowledgeChatCitation(
            node_id=str(row["id"]),
            title=str(row.get("title") or row["id"]),
            node_type=row.get("node_type", "entity"),
            score=float(row.get("combined_score") or row.get("vector_score") or 0.0),
        )
        for row in rows
        if row.get("id")
    ]

    answer = await pkm_service.build_chat_answer(
        app_settings,
        request.query,
        citations,
        contexts=rows,
        use_mock=False,
    )
    # Heuristik: Nur dann einen `chat_insight`-Save-Vorschlag mitsenden,
    # wenn die Frage substantiell genug ist und mindestens 2 Citations
    # hervorgebracht hat. So vermeiden wir Muell-Vorschlaege bei Smalltalk
    # ("Hi", "ok", "Was ist X?") und reduzieren Knoten-Drift im Graph.
    proposed_node = None
    proposed_edges: list = []
    query_text = request.query.strip()
    looks_substantial = len(query_text) >= 25 and len(query_text.split()) >= 4
    if looks_substantial and len(citations) >= 2:
        proposed_node, proposed_edges = pkm_service.propose_chat_insight(
            request.query, answer, citations, request.experiment_type
        )

    return KnowledgeChatResponse(
        answer=answer,
        citations=citations,
        proposed_save=proposed_node,
        proposed_edges=proposed_edges,
    )


@app.post("/knowledge/proposals", response_model=KnowledgeProposal)
async def create_knowledge_proposal(
    proposal: KnowledgeProposalCreate,
) -> KnowledgeProposal:
    row = await repository.create_knowledge_proposal(
        {
            "kind": proposal.kind,
            "source_ref": proposal.source_ref,
            "payload": proposal.payload.model_dump(mode="json"),
            "created_by": proposal.created_by or "chat-user",
            "status": "pending",
        }
    )
    return KnowledgeProposal(
        id=str(row["id"]),
        kind=row["kind"],
        source_ref=row.get("source_ref"),
        payload=KnowledgeCandidates.model_validate(row.get("payload") or {}),
        status=row.get("status", "pending"),
        created_by=row.get("created_by"),
        created_at=_safe_dt(row.get("created_at")),
        decided_at=_safe_dt(row.get("decided_at")),
    )


@app.post("/knowledge/proposals/{proposal_id}/confirm", response_model=AcceptDraftResponse)
async def confirm_knowledge_proposal(
    proposal_id: str,
    app_settings: Settings = Depends(get_settings),
) -> AcceptDraftResponse:
    proposal = await repository.get_knowledge_proposal(proposal_id)
    if not proposal:
        raise _api_error(404, "proposal_not_found", "Proposal not found")
    if proposal.get("status") != "pending":
        raise _api_error(409, "proposal_decided", "Proposal already decided")

    payload = proposal.get("payload") or {}
    candidates = KnowledgeCandidates.model_validate(payload)
    source_ref = proposal.get("source_ref") or proposal_id

    inserted, merged, edges_count = await _ingest_candidates_with_dedupe(
        source_ref, candidates, app_settings
    )
    await repository.update_knowledge_proposal_status(proposal_id, "confirmed")

    return AcceptDraftResponse(
        plan_id=source_ref,
        inserted_nodes=inserted,
        merged_nodes=merged,
        inserted_edges=edges_count,
        candidate_summary=pkm_service.candidate_summary(candidates),
    )


@app.post("/knowledge/proposals/{proposal_id}/reject")
async def reject_knowledge_proposal(proposal_id: str) -> dict:
    proposal = await repository.get_knowledge_proposal(proposal_id)
    if not proposal:
        raise _api_error(404, "proposal_not_found", "Proposal not found")
    if proposal.get("status") != "pending":
        raise _api_error(409, "proposal_decided", "Proposal already decided")
    await repository.update_knowledge_proposal_status(proposal_id, "rejected")
    return {"status": "rejected", "id": proposal_id}
