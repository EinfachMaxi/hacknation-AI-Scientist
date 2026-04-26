from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.schemas.plan import ReviewIssue
from backend.app.services.agent_registry import AgentDefinition
from backend.app.services.catalog import load_catalog
from backend.app.services.integrations import TavilyClient
from backend.app.services.tool_calling import TavilyToolGateway


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
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI chat/completions failed ({response.status_code}): {response.text[:400]}")
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    import json
    return json.loads(content)


def _build_agent_system_prompt(agent: AgentDefinition) -> str:
    metadata = agent.metadata or {}
    task = metadata.get("task")
    output_schema = metadata.get("output_schema")
    parts = [
        f"You are {agent.name}.",
        f"Role: {agent.role}.",
        f"Personality: {agent.personality or 'Professional and concise'}.",
        f"Core instruction: {agent.prompt_template or agent.role}.",
    ]
    if task:
        parts.append(f"Task details: {task}")
    if output_schema:
        parts.append(f"Output schema hint: {output_schema}")
    return "\n".join(parts)


async def literature_scout(
    prompt: str,
    tavily: TavilyClient,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
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
    tavily_warning: str | None = None
    try:
        results = await tavily.search(prompt)
    except Exception as exc:  # noqa: BLE001
        results = []
        tavily_warning = f"Tavily unavailable: {exc!s}"
    references = [
        {
            "title": item.get("title", "Unknown"),
            "url": item.get("url"),
            "similarity": "similar_work_exists",
        }
        for item in results
    ]
    try:
        summary = await _openai_json(
            settings,
            system_prompt or "You are a literature scout. Return JSON with novelty_signal, summary, references.",
            f"Hypothesis: {prompt}\nTavily references: {references}",
        )
    except Exception as exc:  # noqa: BLE001
        fallback_summary = "Literatur-Agent fiel auf Fallback-Antwort zurueck."
        if tavily_warning:
            fallback_summary = f"{fallback_summary} {tavily_warning}"
        return {
            "novelty_signal": "similar_work_exists",
            "summary": f"{fallback_summary} OpenAI error: {exc!s}",
            "references": references,
        }

    summary_text = summary.get("summary", "Automatische Tavily-Auswertung der Literatur.")
    if tavily_warning:
        summary_text = f"{summary_text} ({tavily_warning})"
    return {
        "novelty_signal": summary.get("novelty_signal", "similar_work_exists"),
        "summary": summary_text,
        "references": summary.get("references", references) or references,
    }


async def protocol_designer(
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
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
    try:
        return await _openai_json(
            settings,
            system_prompt or "You are a protocol designer. Return JSON with keys: steps, total_duration, controls. Max 12 steps.",
            f"Create protocol for hypothesis: {prompt}",
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "steps": [
                {
                    "step_number": 1,
                    "action": "Define experiment setup and controls",
                    "duration": "30 minutes",
                    "details": f"Fallback generated for prompt: {prompt}",
                },
                {
                    "step_number": 2,
                    "action": "Execute core assay protocol",
                    "duration": "90 minutes",
                    "details": "Run the main measurement workflow and log observations.",
                },
            ],
            "total_duration": "1 working day",
            "controls": ["Negative control", "Positive control", "Matrix control"],
            "_warning": f"OpenAI fallback used: {exc!s}",
        }


async def materials_agent(
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
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
    try:
        return await _openai_json(
            settings,
            system_prompt
            or "You are a materials agent. Return JSON with key materials as list. Include item, catalog_number, supplier, quantity, unit_price, currency, total_price, verification, source_url.",
            f"Hypothesis: {prompt}\nProduct catalog candidates: {catalog[:15]}",
        )
    except Exception as exc:  # noqa: BLE001
        fallback_materials = []
        if catalog:
            item = catalog[0]
            fallback_materials.append(
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
            )
        return {"materials": fallback_materials, "_warning": f"OpenAI fallback used: {exc!s}"}


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


def _tool_calling_allowed(agent: AgentDefinition) -> bool:
    caps = set(agent.capabilities)
    allowed_tools = set((agent.metadata or {}).get("allowed_tools", []))
    return bool({"literature", "references", "research"} & caps) or "tavily.search" in allowed_tools


async def run_dynamic_agent(
    agent: AgentDefinition,
    *,
    prompt: str,
    settings: Settings,
    use_mock: bool,
    tavily: TavilyClient,
    state: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]]]:
    system_prompt = _build_agent_system_prompt(agent)
    traces: list[dict[str, Any]] = []

    if agent.key == "literature":
        if settings.agent_tool_calling_enabled and _tool_calling_allowed(agent) and not use_mock:
            metadata = agent.metadata or {}
            max_calls = min(int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)), settings.agent_tool_max_calls)
            max_results = int(metadata.get("max_results", 3))
            allowlist_from_env = tuple(
                token.strip()
                for token in settings.agent_tool_domain_allowlist.split(",")
                if token.strip()
            )
            gateway = TavilyToolGateway(
                tavily,
                domain_allowlist=allowlist_from_env or ("pubmed", "nature"),
                timeout_seconds=settings.agent_tool_timeout_seconds,
                max_retries=settings.agent_tool_max_retries,
            )
            try:
                results, search_trace = await gateway.search(prompt, max_results=max_results)
                traces.append(search_trace.as_dict())
                extracts: list[dict[str, Any]] = []
                if max_calls > 1:
                    urls = [row.get("url", "") for row in results if row.get("url")]
                    extracted, extract_trace = await gateway.extract(urls[:2], call_index=2)
                    extracts = extracted
                    traces.append(extract_trace.as_dict())
                references = [
                    {"title": row.get("title", "Unknown"), "url": row.get("url"), "similarity": "similar_work_exists"}
                    for row in results
                ]
                evidence = {"search_results": results, "extracts": extracts}
                summary = await _openai_json(
                    settings,
                    f"{system_prompt}\nReturn JSON with novelty_signal, summary, references.",
                    f"Hypothesis: {prompt}\nEvidence: {evidence}",
                )
                output = {
                    "novelty_signal": summary.get("novelty_signal", "similar_work_exists"),
                    "summary": summary.get("summary", "Automatische Tavily-Auswertung der Literatur."),
                    "references": summary.get("references", references) or references,
                }
                return output, traces
            except Exception as exc:  # noqa: BLE001
                error_class = gateway.classify_error(exc)
                traces.append(
                    {
                        "tool": "tavily.search",
                        "status": "error",
                        "call_index": 1,
                        "payload": {"query": prompt, "error_class": error_class},
                        "error": str(exc),
                    }
                )
                output = await literature_scout(prompt, tavily, settings, use_mock, system_prompt=system_prompt)
                output["summary"] = f"{output.get('summary', '')} (Tool-calling fallback aktiv: {exc!s})".strip()
                return output, traces
        output = await literature_scout(prompt, tavily, settings, use_mock, system_prompt=system_prompt)
        return output, traces

    if agent.key == "protocol":
        output = await protocol_designer(prompt, settings, use_mock, system_prompt=system_prompt)
        return output, traces

    if agent.key == "materials":
        raw = await materials_agent(prompt, settings, use_mock, system_prompt=system_prompt)
        output = raw["materials"] if isinstance(raw, dict) else raw
        return output, traces

    if agent.key == "budget":
        output = await budget_agent(state["materials"])
        return output, traces

    if agent.key == "timeline":
        output = await timeline_agent(state["protocol"].get("steps", []))
        return output, traces

    if agent.key == "review":
        issues = await review_agent(state["protocol"], state["materials"], state["budget"])
        return [issue.model_dump() for issue in issues], traces

    raise RuntimeError(f"Unbekannter Agent: {agent.key}")


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
