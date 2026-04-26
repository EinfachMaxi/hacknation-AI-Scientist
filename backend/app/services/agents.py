from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.schemas.plan import ReviewIssue
from backend.app.services.agent_registry import AgentDefinition
from backend.app.services.catalog import load_catalog
from backend.app.services.integrations import TavilyClient
from backend.app.services.tool_calling import TavilyToolGateway

logger = logging.getLogger(__name__)


async def _openai_json(
    settings: Settings,
    system: str,
    user: str,
    *,
    max_attempts: int = 3,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY fehlt. Bitte in backend/.env setzen.")

    # OpenAI requires the literal word "json" to appear somewhere in `messages`
    # whenever `response_format={"type": "json_object"}` is used. Callers pass
    # arbitrary system prompts (e.g. built from the agent registry) that may
    # not mention JSON at all, so we normalise defensively here.
    system_with_json = system
    if "json" not in system.lower() and "json" not in user.lower():
        system_with_json = f"{system}\n\nRespond with a single valid JSON object."

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_with_json},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
            status = response.status_code
            if status == 429 or status >= 500:
                raise RuntimeError(
                    f"OpenAI transient ({status}): {response.text[:200]}"
                )
            if status >= 400:
                raise RuntimeError(
                    f"OpenAI chat/completions failed ({status}): {response.text[:400]}"
                )
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except (httpx.TimeoutException, httpx.TransportError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("OpenAI call transient failure (attempt %s/%s): %s", attempt, max_attempts, exc)
        except RuntimeError as exc:
            last_error = exc
            if "transient" not in str(exc):
                raise
            logger.warning("OpenAI call transient failure (attempt %s/%s): %s", attempt, max_attempts, exc)

        if attempt < max_attempts:
            await asyncio.sleep(0.4 * attempt)

    assert last_error is not None
    raise last_error


def _coerce_duration(raw: Any, default: str = "30 minutes") -> str:
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return f"{int(raw)} minutes"
    text = str(raw).strip()
    return text or default


def _normalize_protocol_steps(raw_steps: Any, prompt: str) -> list[dict[str, Any]]:
    """Coerce LLM output variants into the shape the rest of the pipeline expects.

    Downstream (`timeline_agent`, frontend rendering) assumes each step has
    `step_number`, `action`, `duration`, and `details`. OpenAI frequently emits
    `step`/`description` or similar aliases; we normalise here so a single
    unexpected key does not force us onto the fallback path.
    """
    if not isinstance(raw_steps, list):
        return []
    normalised: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_steps, start=1):
        if not isinstance(entry, dict):
            continue
        step_number = entry.get("step_number") or entry.get("step") or entry.get("number") or idx
        try:
            step_number = int(step_number)
        except (TypeError, ValueError):
            step_number = idx
        action = (
            entry.get("action")
            or entry.get("title")
            or entry.get("name")
            or entry.get("description")
            or entry.get("task")
            or f"Step {idx}"
        )
        details = (
            entry.get("details")
            or entry.get("description")
            or entry.get("notes")
            or entry.get("explanation")
            or ""
        )
        duration = _coerce_duration(entry.get("duration") or entry.get("estimated_duration"))
        if action == details:
            details = ""
        normalised.append(
            {
                "step_number": step_number,
                "action": str(action).strip() or f"Step {idx}",
                "duration": duration,
                "details": str(details).strip(),
            }
        )
    return normalised


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
    literature_schema = (
        "Return JSON with keys: novelty_signal (string: 'novel' | 'similar_work_exists' | 'contradicted'), "
        "summary (string), references (list of objects with title, url, similarity)."
    )
    base_sp = system_prompt or "You are a literature scout."
    try:
        summary = await _openai_json(
            settings,
            f"{base_sp}\n{literature_schema}",
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
    protocol_schema = (
        "Return JSON with keys: steps (list), total_duration (string), controls (list of strings). "
        "Each step MUST include step_number (int), action (short imperative string, e.g. 'Immobilise anti-CRP antibodies'), "
        "duration (human-readable like '30 minutes'), and details (one sentence). "
        "Produce 6 to 12 concrete, hypothesis-specific steps."
    )
    base_sp = system_prompt or "You are a protocol designer."
    try:
        raw = await _openai_json(
            settings,
            f"{base_sp}\n{protocol_schema}",
            f"Create protocol for hypothesis: {prompt}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("protocol_designer: falling back (OpenAI error): %s", exc)
        return _protocol_fallback(prompt, reason=str(exc))

    steps = _normalize_protocol_steps(raw.get("steps"), prompt)
    if not steps:
        logger.warning("protocol_designer: OpenAI returned no usable steps, using fallback")
        return _protocol_fallback(prompt, reason="LLM returned no usable steps")

    controls = raw.get("controls")
    if not isinstance(controls, list) or not controls:
        controls = ["Negative control", "Positive control", "Matrix control"]

    total_duration = raw.get("total_duration") or "1 working day"
    return {
        "steps": steps,
        "total_duration": str(total_duration),
        "controls": [str(c) for c in controls],
    }


def _protocol_fallback(prompt: str, *, reason: str) -> dict[str, Any]:
    """Reasonable protocol skeleton when the LLM is unavailable.

    The old fallback leaked the raw prompt into the UI ("Fallback generated
    for prompt: ..."), which looked broken. We now produce a short but
    coherent protocol the user can still work with, and attach the error as
    an internal `_warning` instead.
    """
    short_prompt = prompt.strip()
    if len(short_prompt) > 120:
        short_prompt = short_prompt[:117].rstrip() + "..."
    return {
        "steps": [
            {
                "step_number": 1,
                "action": "Prepare reagents, controls and calibration standards",
                "duration": "45 minutes",
                "details": "Thaw reagents, prepare buffers and dilution series; document lot numbers.",
            },
            {
                "step_number": 2,
                "action": "Assemble instrument and verify baseline performance",
                "duration": "30 minutes",
                "details": "Calibrate the detector, run a blank, confirm signal-to-noise within spec.",
            },
            {
                "step_number": 3,
                "action": "Run positive, negative and matrix controls",
                "duration": "45 minutes",
                "details": "Validate assay behaviour before applying samples.",
            },
            {
                "step_number": 4,
                "action": "Execute main assay on test samples",
                "duration": "90 minutes",
                "details": f"Perform measurement loop for hypothesis under test ({short_prompt}).",
            },
            {
                "step_number": 5,
                "action": "Record readouts and export raw data",
                "duration": "30 minutes",
                "details": "Capture numeric readouts and metadata; store with run identifier.",
            },
            {
                "step_number": 6,
                "action": "Clean up and archive samples",
                "duration": "30 minutes",
                "details": "Dispose biohazard waste, archive remaining samples at -20 C.",
            },
        ],
        "total_duration": "1 working day",
        "controls": ["Negative control", "Positive standard", "Matrix control"],
        "_warning": f"OpenAI fallback used: {reason}",
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
    materials_schema = (
        "Return JSON with key 'materials' as a list. Each material MUST include "
        "item (string), catalog_number (string), supplier (string), quantity (string), "
        "unit_price (number), currency (string, e.g. 'EUR'), total_price (number), "
        "verification ('verified' | 'suggested_verify'), source_url (string or null)."
    )
    base_sp = system_prompt or "You are a materials agent."
    try:
        return await _openai_json(
            settings,
            f"{base_sp}\n{materials_schema}",
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


async def budget_agent(
    materials: list[dict[str, Any]],
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    total = sum(float(item.get("total_price", 0) or 0) for item in materials)

    if use_mock or not materials:
        return _budget_fallback(total, reason="mock or empty materials")

    budget_schema = (
        "Return JSON with keys: currency (string like 'EUR'), "
        "breakdown (object with numeric fields 'reagents', 'consumables', "
        "'equipment_usage' that together must sum to the provided TOTAL), "
        "notes (1-2 sentences explaining why this split fits the actual "
        "material list; reference dominant cost drivers by name)."
    )
    base_sp = system_prompt or (
        "You are a budget agent that categorises experiment costs. "
        "Analyse each material item (reagents vs plastic/tips/plates vs "
        "instrument/chip/sensor time) and distribute the precomputed total "
        "accordingly."
    )
    try:
        result = await _openai_json(
            settings,
            f"{base_sp}\n{budget_schema}",
            (
                f"Hypothesis: {prompt}\n"
                f"Precomputed TOTAL (EUR, authoritative): {total:.2f}\n"
                f"Materials (item, catalog_number, supplier, quantity, "
                f"unit_price, total_price): {materials}\n"
                "Classify each material into reagents, consumables, or "
                "equipment_usage, sum the totals per bucket and ensure the "
                "three buckets sum EXACTLY to the provided TOTAL."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("budget_agent: falling back (OpenAI error): %s", exc)
        return _budget_fallback(total, reason=str(exc))

    breakdown = result.get("breakdown") or {}
    try:
        reagents = float(breakdown.get("reagents", 0) or 0)
        consumables = float(breakdown.get("consumables", 0) or 0)
        equipment_usage = float(breakdown.get("equipment_usage", 0) or 0)
    except (TypeError, ValueError):
        return _budget_fallback(total, reason="LLM returned non-numeric breakdown")

    bucket_sum = reagents + consumables + equipment_usage
    if bucket_sum <= 0:
        return _budget_fallback(total, reason="LLM returned empty breakdown")
    if abs(bucket_sum - total) > 0.01:
        # Re-scale so the three buckets match our authoritative total.
        scale = total / bucket_sum
        reagents *= scale
        consumables *= scale
        equipment_usage *= scale

    return {
        "total": round(total, 2),
        "currency": str(result.get("currency") or "EUR"),
        "breakdown": {
            "reagents": round(reagents, 2),
            "consumables": round(consumables, 2),
            "equipment_usage": round(equipment_usage, 2),
        },
        "notes": str(
            result.get("notes")
            or "LLM-basierte Kostenaufteilung anhand der konkreten Materialien."
        ),
    }


def _budget_fallback(total: float, *, reason: str) -> dict[str, Any]:
    total_rounded = round(total, 2)
    return {
        "total": total_rounded,
        "currency": "EUR",
        "breakdown": {
            "reagents": round(total * 0.7, 2),
            "consumables": round(total * 0.2, 2),
            "equipment_usage": round(total * 0.1, 2),
        },
        "notes": (
            "Heuristische 70/20/10-Aufteilung (Fallback, ohne Versand/VAT). "
            f"Grund: {reason}"
        ),
    }


def _step_label(step: Any, fallback: str) -> str:
    if not isinstance(step, dict):
        return fallback
    for key in ("action", "title", "name", "description", "task"):
        value = step.get(key)
        if value:
            return str(value)
    return fallback


async def timeline_agent(
    protocol: dict[str, Any],
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    if isinstance(protocol, dict):
        raw_steps = protocol.get("steps") or []
        if isinstance(raw_steps, list):
            steps = [s for s in raw_steps if isinstance(s, dict)]
    protocol_total = (
        protocol.get("total_duration") if isinstance(protocol, dict) else None
    )

    if use_mock or not steps:
        return _timeline_fallback(steps, protocol_total)

    timeline_schema = (
        "Return JSON with keys: phases (list), total_duration (string like "
        "'3 working days'). Each phase MUST include phase (string, e.g. "
        "'Preparation', 'Sample run', 'Analysis'), duration (human-readable "
        "like '1 day' or '4 hours'), tasks (list of short action strings "
        "derived from the provided protocol steps), dependencies (list of "
        "phase names that must finish first), start_day (integer >= 1). "
        "Group the given protocol steps into 2-4 coherent phases; respect "
        "each step's individual duration when estimating phase durations."
    )
    base_sp = system_prompt or (
        "You are a timeline agent that schedules experiment phases based on "
        "concrete protocol steps and their durations."
    )
    try:
        result = await _openai_json(
            settings,
            f"{base_sp}\n{timeline_schema}",
            (
                f"Hypothesis: {prompt}\n"
                f"Protocol total duration (reference): {protocol_total}\n"
                f"Protocol steps (with duration + details): {steps}\n"
                "Assign every step to exactly one phase."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("timeline_agent: falling back (OpenAI error): %s", exc)
        return _timeline_fallback(steps, protocol_total, reason=str(exc))

    raw_phases = result.get("phases")
    if not isinstance(raw_phases, list) or not raw_phases:
        return _timeline_fallback(
            steps, protocol_total, reason="LLM returned no usable phases"
        )

    normalised_phases: list[dict[str, Any]] = []
    for idx, phase in enumerate(raw_phases, start=1):
        if not isinstance(phase, dict):
            continue
        name = phase.get("phase") or phase.get("name") or f"Phase {idx}"
        duration = phase.get("duration") or "1 day"
        raw_tasks = phase.get("tasks") or []
        tasks = [str(t).strip() for t in raw_tasks if str(t).strip()]
        raw_deps = phase.get("dependencies") or []
        dependencies = [str(d).strip() for d in raw_deps if str(d).strip()]
        try:
            start_day = int(phase.get("start_day") or idx)
        except (TypeError, ValueError):
            start_day = idx
        normalised_phases.append(
            {
                "phase": str(name).strip() or f"Phase {idx}",
                "duration": str(duration).strip() or "1 day",
                "tasks": tasks or [f"Phase {idx} tasks"],
                "dependencies": dependencies,
                "start_day": max(1, start_day),
            }
        )

    if not normalised_phases:
        return _timeline_fallback(
            steps, protocol_total, reason="LLM phases could not be normalised"
        )

    total_duration = result.get("total_duration") or protocol_total or "3 working days"
    return {
        "phases": normalised_phases,
        "total_duration": str(total_duration),
    }


def _timeline_fallback(
    steps: list[dict[str, Any]],
    protocol_total: Any,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    prep_task = _step_label(steps[0], "Preparation") if steps else "Preparation"
    execution_tasks = [
        _step_label(step, f"Step {idx + 2}") for idx, step in enumerate(steps[1:])
    ]
    result: dict[str, Any] = {
        "phases": [
            {
                "phase": "Preparation",
                "duration": "1 day",
                "tasks": [prep_task],
                "dependencies": [],
                "start_day": 1,
            },
            {
                "phase": "Execution",
                "duration": "2 days",
                "tasks": execution_tasks or ["Execution"],
                "dependencies": ["Preparation"],
                "start_day": 2,
            },
        ],
        "total_duration": str(protocol_total or "3 working days"),
    }
    if reason:
        result["_warning"] = f"Timeline fallback: {reason}"
    return result


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
        output = await budget_agent(
            state["materials"],
            prompt,
            settings,
            use_mock,
            system_prompt=system_prompt,
        )
        return output, traces

    if agent.key == "timeline":
        output = await timeline_agent(
            state["protocol"] if isinstance(state.get("protocol"), dict) else {},
            prompt,
            settings,
            use_mock,
            system_prompt=system_prompt,
        )
        return output, traces

    if agent.key == "review":
        issues = await review_agent(state["protocol"], state["materials"], state["budget"])
        return [issue.model_dump() for issue in issues], traces

    raise RuntimeError(f"Unbekannter Agent: {agent.key}")


async def validation_agent(
    prompt: str,
    protocol: dict[str, Any],
    materials: list[dict[str, Any]],
    settings: Settings,
    use_mock: bool,
) -> dict[str, Any]:
    if use_mock:
        return _validation_fallback()

    validation_schema = (
        "Return JSON with keys: success_criteria (list of 3-5 concrete, "
        "measurable criteria tied to the hypothesis; include numeric "
        "thresholds with units where possible), controls (list of strings "
        "covering negative, positive and matrix/blank controls appropriate "
        "for the protocol), statistical_plan (one sentence describing "
        "replicate count and the statistical test used for evaluation)."
    )
    base_sp = (
        "You are a validation agent that defines hypothesis-specific, "
        "measurable success criteria, required controls and a statistical "
        "analysis plan for wet-lab experiments."
    )
    steps = protocol.get("steps", []) if isinstance(protocol, dict) else []
    protocol_controls = (
        protocol.get("controls", []) if isinstance(protocol, dict) else []
    )
    try:
        result = await _openai_json(
            settings,
            f"{base_sp}\n{validation_schema}",
            (
                f"Hypothesis: {prompt}\n"
                f"Protocol steps: {steps}\n"
                f"Protocol-level controls already defined: {protocol_controls}\n"
                f"Materials (first 10): {materials[:10]}\n"
                "Derive criteria that directly test the hypothesis."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("validation_agent: falling back (OpenAI error): %s", exc)
        fallback = _validation_fallback()
        fallback["_warning"] = f"OpenAI fallback used: {exc!s}"
        return fallback

    criteria = [str(c).strip() for c in (result.get("success_criteria") or []) if str(c).strip()]
    controls = [str(c).strip() for c in (result.get("controls") or []) if str(c).strip()]
    stat_plan = result.get("statistical_plan")

    if not criteria or not controls or not stat_plan:
        fallback = _validation_fallback()
        fallback["_warning"] = "LLM returned incomplete validation payload"
        return fallback

    return {
        "success_criteria": criteria,
        "controls": controls,
        "statistical_plan": str(stat_plan).strip(),
    }


def _validation_fallback() -> dict[str, Any]:
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
