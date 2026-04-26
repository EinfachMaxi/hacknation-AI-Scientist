from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.schemas.plan import ReviewIssue
from backend.app.services.catalog import load_catalog
from backend.app.services.integrations import TavilyClient


async def _openai_json(settings: Settings, system: str, user: str) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt. Bitte in backend/.env setzen.")
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    import json
    return json.loads(content)


async def literature_scout(prompt: str, tavily: TavilyClient, settings: Settings, use_mock: bool) -> dict[str, Any]:
    if use_mock:
        return {
            "novelty_signal": "similar_work_exists",
            "summary": "2 thematisch nahe Arbeiten gefunden, aber kein exakter Match.",
            "references": [
                {
                    "title": "Paper-based electrochemical biosensor for CRP detection in whole blood",
                    "authors": "Zhang et al.",
                    "year": 2024,
                    "journal": "Biosensors and Bioelectronics",
                    "doi": "10.1016/j.bios.2024.xxxxx",
                    "similarity": "similar_methodology",
                    "key_difference": "Serum statt Vollblut.",
                }
            ],
        }
    results = await tavily.search(prompt)
    references = [
        {
            "title": item.get("title", "Unknown"),
            "url": item.get("url"),
            "similarity": "similar_work_exists",
        }
        for item in results
    ]
    summary = await _openai_json(
        settings,
        "You are a literature scout. Return JSON with novelty_signal, summary, references.",
        f"Hypothesis: {prompt}\nTavily references: {references}",
    )
    return {
        "novelty_signal": summary.get("novelty_signal", "similar_work_exists"),
        "summary": summary.get("summary", "Automatische Tavily-Auswertung der Literatur."),
        "references": summary.get("references", references) or references,
    }


async def protocol_designer(prompt: str, settings: Settings, use_mock: bool) -> dict[str, Any]:
    if use_mock:
        return {
            "steps": [
                {
                    "step_number": 1,
                    "action": "Prepare CRP standards and controls",
                    "duration": "30 minutes",
                    "details": f"Set up dilution series for hypothesis: {prompt}",
                },
                {
                    "step_number": 2,
                    "action": "Run assay incubation and wash steps",
                    "duration": "90 minutes",
                    "details": "Execute binding, washing, and detection sequence under standard conditions.",
                },
                {
                    "step_number": 3,
                    "action": "Measure signal and document results",
                    "duration": "45 minutes",
                    "details": "Capture readouts and export data for downstream validation.",
                },
            ],
            "total_duration": "1 working day",
            "controls": ["Negative control", "Positive CRP standard", "Matrix control (whole blood)"],
        }
    return await _openai_json(
        settings,
        "You are a protocol designer. Return JSON with keys: steps, total_duration, controls. Max 12 steps.",
        f"Create protocol for hypothesis: {prompt}",
    )


async def materials_agent(prompt: str, settings: Settings, use_mock: bool) -> dict[str, Any]:
    catalog = load_catalog()
    if use_mock and catalog:
        item = catalog[0]
        return {
            "materials": [
                {
                    "item": item["item"],
                    "catalog_number": item["catalog_number"],
                    "supplier": item["supplier"],
                    "quantity": "1 unit",
                    "unit_price": float(item["unit_price"]),
                    "currency": item.get("currency", "EUR"),
                    "total_price": float(item["unit_price"]),
                    "storage": item.get("storage", "-20C"),
                    "verification": "verified",
                    "source_url": item.get("source_url"),
                }
            ]
        }
    return await _openai_json(
        settings,
        "You are a materials agent. Return JSON with key materials as list. Include item, catalog_number, supplier, quantity, unit_price, currency, total_price, verification, source_url.",
        f"Hypothesis: {prompt}\nProduct catalog candidates: {catalog[:15]}",
    )


async def budget_agent(materials: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(float(item["total_price"]) for item in materials)
    return {
        "total": total,
        "currency": "EUR",
        "breakdown": {
            "reagents": round(total * 0.7, 2),
            "consumables": round(total * 0.2, 2),
            "equipment_usage": round(total * 0.1, 2),
        },
        "notes": "Mock-Kalkulation; Preise ohne Versand und VAT.",
    }


async def timeline_agent(protocol_steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "phases": [
            {
                "phase": "Preparation",
                "duration": "1 day",
                "tasks": [protocol_steps[0]["action"]] if protocol_steps else ["Preparation"],
                "dependencies": [],
                "start_day": 1,
            },
            {
                "phase": "Execution",
                "duration": "2 days",
                "tasks": [step["action"] for step in protocol_steps[1:]] or ["Execution"],
                "dependencies": ["Preparation"],
                "start_day": 2,
            },
        ],
        "total_duration": "3 working days",
    }


async def review_agent(
    protocol: dict[str, Any], materials: list[dict[str, Any]], budget: dict[str, Any]
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if not protocol.get("steps"):
        issues.append(ReviewIssue(severity="error", message="Protocol enthält keine Schritte.", path="protocol.steps"))
    if not materials:
        issues.append(ReviewIssue(severity="error", message="Materialliste ist leer.", path="materials"))
    if budget.get("total", 0) <= 0:
        issues.append(ReviewIssue(severity="warning", message="Budget ist 0 oder unbekannt.", path="budget.total"))
    if any(item.get("verification") == "suggested_verify" for item in materials):
        issues.append(
            ReviewIssue(
                severity="warning",
                message="Nicht verifizierte Katalogeinträge vorhanden.",
                path="materials[*].verification",
            )
        )
    return issues


def default_validation() -> dict[str, Any]:
    return {
        "success_criteria": [
            "Detection limit <= 0.5 mg/L",
            "Assay time <= 10 minutes",
            "R2 >= 0.95 vs baseline method",
        ],
        "controls": ["Negative control", "Positive standard", "Matrix control"],
        "statistical_plan": "n=3 technical replicates x 3 biological replicates; ANOVA + Tukey.",
    }


def build_title(prompt: str) -> str:
    snippet = prompt[:50].strip()
    return f"Auto Experiment Plan - {snippet}"


def build_knowledge_nodes(plan_id: str, hypothesis: str, materials: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    experiment_node_id = f"kn-exp-{plan_id}"
    nodes = [
        {
            "id": experiment_node_id,
            "title": f"Experiment {plan_id}",
            "node_type": "experiment",
            "content": hypothesis,
            "confidence_score": 0.7,
            "times_applied": 1,
            "tags": ["experiment", "auto-generated"],
            "created_by": "ai-agent",
            "created_at": datetime.utcnow().isoformat(),
        }
    ]
    edges: list[dict[str, Any]] = []
    def _read(value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    normalized_materials = materials if isinstance(materials, list) else [materials]
    for idx, material in enumerate(normalized_materials):
        item = _read(material, "item") or "unknown_item"
        supplier = _read(material, "supplier") or "unknown_supplier"
        catalog_number = _read(material, "catalog_number") or "n/a"
        reagent_id = f"kn-reagent-{plan_id}-{idx}"
        nodes.append(
            {
                "id": reagent_id,
                "title": item,
                "node_type": "reagent",
                "content": f"{supplier} - {catalog_number}",
                "confidence_score": 0.6,
                "times_applied": 1,
                "tags": ["reagent", "catalog"],
                "created_by": "ai-agent",
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        edges.append(
            {
                "source_id": experiment_node_id,
                "target_id": reagent_id,
                "relationship_type": "uses",
                "weight": 1.0,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
    return nodes, edges
