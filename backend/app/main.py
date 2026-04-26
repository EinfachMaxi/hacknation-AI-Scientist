from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.config import Settings, get_settings
from backend.app.schemas.plan import (
    AgentEvent,
    CorrectionRequest,
    ExperimentPlan,
    ExperimentRun,
    ExperimentSummary,
    GeneratePlanRequest,
    StartRunRequest,
    StartRunResponse,
)
from backend.app.services.integrations import SupabaseRepository
from backend.app.services.orchestrator import PlanOrchestrator

app = FastAPI(title="AI Scientist Backend", version="0.1.0")
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
        raise HTTPException(status_code=404, detail="Run not found")
    return ExperimentRun.model_validate(run)


@app.get("/runs/{run_id}/events", response_model=list[AgentEvent])
async def get_run_events(run_id: str) -> list[AgentEvent]:
    events = await repository.list_run_events(run_id)
    return [AgentEvent.model_validate(event) for event in events]


@app.get("/runs/{run_id}/plan", response_model=ExperimentPlan)
async def get_run_plan(run_id: str) -> ExperimentPlan:
    run = await repository.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    plan_id = run.get("plan_id")
    if not plan_id:
        raise HTTPException(status_code=404, detail="Plan not ready")
    row = await repository.get_plan(plan_id)
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
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
        raise HTTPException(status_code=404, detail="Plan not found")
    return ExperimentPlan.model_validate(row)


@app.get("/knowledge")
async def list_knowledge() -> dict:
    return await repository.list_knowledge()


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
        "confidence_score": 0.8,
        "times_applied": 1,
        "created_by": "scientist-review",
        "tags": ["correction", correction.experiment_type],
    }
    edge = {
        "source_id": f"kn-exp-{plan_id}",
        "target_id": node_id,
        "relationship_type": "corrects",
        "weight": 1.0,
    }
    await repository.upsert_knowledge_nodes([node])
    await repository.add_knowledge_edges([edge])
    return {"status": "stored", "node_id": node_id}
