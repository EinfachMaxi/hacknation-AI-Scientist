from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Reference(BaseModel):
    title: str
    authors: str | None = None
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    similarity: str | None = None
    key_difference: str | None = None
    url: str | None = None


class LiteratureQC(BaseModel):
    novelty_signal: Literal["exact_match", "similar_work_exists", "not_found"]
    references: list[Reference] = Field(default_factory=list)
    summary: str


class ProtocolStep(BaseModel):
    step_number: int
    action: str
    duration: str
    details: str
    notes: str | None = None
    source: str | None = None


class Protocol(BaseModel):
    steps: list[ProtocolStep] = Field(default_factory=list, max_length=15)
    total_duration: str
    controls: list[str] = Field(default_factory=list)


class MaterialItem(BaseModel):
    item: str
    catalog_number: str
    supplier: str
    quantity: str
    unit_price: float
    currency: str = "EUR"
    total_price: float
    storage: str | None = None
    verification: Literal["verified", "suggested_verify"] = "verified"
    source_url: str | None = None


class BudgetBreakdown(BaseModel):
    reagents: float = 0
    consumables: float = 0
    equipment_usage: float = 0


class Budget(BaseModel):
    total: float
    currency: str = "EUR"
    breakdown: BudgetBreakdown
    notes: str | None = None


class TimelinePhase(BaseModel):
    phase: str
    duration: str
    tasks: list[str]
    dependencies: list[str] = Field(default_factory=list)
    start_day: int


class Timeline(BaseModel):
    phases: list[TimelinePhase]
    total_duration: str


class Validation(BaseModel):
    success_criteria: list[str]
    controls: list[str]
    statistical_plan: str


class ReviewIssue(BaseModel):
    severity: Literal["warning", "error"]
    message: str
    path: str


class ExperimentPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    hypothesis: str
    literature_qc: LiteratureQC
    protocol: Protocol
    materials: list[MaterialItem] = Field(default_factory=list, max_length=25)
    budget: Budget
    timeline: Timeline
    validation: Validation
    review_issues: list[ReviewIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    knowledge_nodes_extracted: list[str] = Field(default_factory=list)


class GeneratePlanRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=8_000)
    experiment_type: str | None = None
    use_mock: bool = False


class ExperimentSummary(BaseModel):
    plan_id: str
    title: str
    hypothesis: str
    generated_at: datetime


class CorrectionRequest(BaseModel):
    experiment_type: str
    field_path: str
    old_value: str
    new_value: str
    reason: str


class RunStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    sequence: int
    agent: str
    phase: Literal["starting", "progress", "complete", "error"]
    status: Literal["started", "completed", "failed"]
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    from_agent: str | None = None
    to_agent: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExperimentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    hypothesis: str
    experiment_type: str | None = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    plan_id: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StartRunRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=8_000)
    experiment_type: str | None = None
    use_mock: bool = False


class StartRunResponse(BaseModel):
    run_id: str
    status: Literal["pending", "running"]

