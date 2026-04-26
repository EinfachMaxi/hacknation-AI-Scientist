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


async def _llm_rescue_json(
    settings: Settings,
    system: str,
    user: str,
    *,
    agent_hint: str = "agent",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Letzter LLM-Versuch wenn der reguläre Agent-Call fehlgeschlagen ist.

    Ruft `_openai_json` mit einem stark vereinfachten System-Prompt erneut
    auf. Gibt `({}, trace)` zurueck wenn auch das scheitert. Alle Rescue-
    Calls werden als `openai.rescue` Trace geloggt, damit man im UI sieht,
    dass wir aus dem regulären Pfad gefallen sind.
    """
    trace: dict[str, Any] = {
        "tool": "openai.rescue",
        "status": "completed",
        "call_index": 1,
        "payload": {"agent": agent_hint},
    }
    try:
        result = await _openai_json(settings, system, user, max_attempts=2)
        if not isinstance(result, dict):
            trace["status"] = "skipped"
            trace["payload"]["reason"] = "non_dict_response"
            return {}, trace
        return result, trace
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_rescue[%s] failed: %s", agent_hint, exc)
        trace["status"] = "error"
        trace["error"] = str(exc)
        return {}, trace


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
        "Return JSON with keys: novelty_signal (EXACTLY one of 'exact_match' | "
        "'similar_work_exists' | 'not_found'), summary (string), references "
        "(list of objects with title, url, similarity)."
    )
    base_sp = system_prompt or "You are a literature scout."
    try:
        summary = await _openai_json(
            settings,
            f"{base_sp}\n{literature_schema}",
            f"Hypothesis: {prompt}\nTavily references: {references}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("literature_scout: primary call failed, trying rescue: %s", exc)
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "Summarise how novel the hypothesis is versus existing work. "
                "Return JSON {novelty_signal,summary,references}."
            ),
            f"Hypothesis: {prompt}\nSearch results: {references}",
            agent_hint="literature",
        )
        if rescued:
            summary = rescued
        else:
            summary = {
                "novelty_signal": "similar_work_exists",
                "summary": (
                    f"Literature agent could not reach OpenAI: {exc!s}."
                    + (f" {tavily_warning}" if tavily_warning else "")
                ),
                "references": references,
            }

    summary_text = summary.get("summary") or (
        f"Literature summary unavailable (no OpenAI response)."
        + (f" {tavily_warning}" if tavily_warning else "")
    )
    if tavily_warning:
        summary_text = f"{summary_text} ({tavily_warning})"
    return {
        "novelty_signal": _coerce_novelty_signal(summary.get("novelty_signal")),
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
    raw: dict[str, Any]
    warning: str | None = None
    try:
        raw = await _openai_json(
            settings,
            f"{base_sp}\n{protocol_schema}",
            f"Create protocol for hypothesis: {prompt}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("protocol_designer: primary call failed, trying rescue LLM call: %s", exc)
        raw, _ = await _llm_rescue_json(
            settings,
            (
                "You are a protocol designer. Produce a JSON object with a "
                "`steps` list of concrete wet-lab actions for the hypothesis. "
                "Each step must have step_number (int), action (imperative), "
                "duration (human-readable), details (one sentence with "
                "reagents / concentrations / temperatures). Also provide "
                "`total_duration` (string) and `controls` (list of strings "
                "specific to this experiment)."
            ),
            f"Hypothesis: {prompt}\nReturn JSON only.",
            agent_hint="protocol",
        )
        warning = f"primary protocol call failed: {exc!s}"

    steps = _normalize_protocol_steps(raw.get("steps"), prompt)
    if not steps:
        logger.warning("protocol_designer: attempting second LLM rescue (no usable steps)")
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "You design wet-lab protocols. Output JSON: "
                "{steps:[{step_number,action,duration,details}], "
                "total_duration, controls:[...]}. Be specific and grounded in "
                "real lab practice; derive everything from the given hypothesis."
            ),
            f"Hypothesis: {prompt}\nReturn JSON only with concrete, non-generic steps.",
            agent_hint="protocol",
        )
        steps = _normalize_protocol_steps(rescued.get("steps"), prompt)
        if rescued:
            raw = rescued
        warning = warning or "primary protocol call returned no usable steps"

    result: dict[str, Any] = {
        "steps": steps,
        "total_duration": str(raw.get("total_duration") or ""),
        "controls": [str(c) for c in (raw.get("controls") or []) if str(c).strip()],
    }
    if warning:
        result["_warning"] = warning
    return result


async def materials_agent(
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Generate a fully hypothesis-specific materials list via the LLM.

    There is no hardcoded catalog anymore — every reagent, consumable and
    piece of instrument time is derived from the user's prompt. Tavily tool
    verification runs separately in `_verify_materials_tools` and
    `_merge_materials_with_supplier_data`.
    """
    materials_schema = (
        "Return JSON with key 'materials' as a list of 5-15 items (reagents, "
        "antibodies/enzymes, consumables, and any instrument/chip/sensor "
        "time needed). Each material MUST include item (string, specific "
        "name with clone/grade/kit name where relevant), catalog_number "
        "(realistic supplier catalog id if known, else an educated guess), "
        "supplier (real vendor name), quantity (string like '50 mL' or '100 "
        "tests'), unit_price (number in EUR), currency ('EUR'), total_price "
        "(number = unit_price * qty), storage (string), verification "
        "('suggested_verify' by default because these are LLM guesses), "
        "source_url (null or a plausible vendor URL).\n"
        "Be specific to the hypothesis: DO NOT emit generic placeholder "
        "reagents. If the hypothesis is about CRISPR, include things like "
        "guide RNA, Cas9 protein, transfection reagent, specific cell line "
        "media. If it's about a biosensor, include the actual substrate, "
        "capture/detection antibodies, redox probe, buffer etc."
    )
    base_sp = system_prompt or (
        "You are a materials agent that designs the full bill-of-materials "
        "for a wet-lab experiment given only the hypothesis."
    )
    warning: str | None = None
    try:
        result = await _openai_json(
            settings,
            f"{base_sp}\n{materials_schema}",
            f"Hypothesis: {prompt}\nReturn JSON only.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("materials_agent: primary call failed, trying rescue: %s", exc)
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "List the materials needed to run this experiment. Output "
                "JSON: {materials:[{item,catalog_number,supplier,quantity,"
                "unit_price,currency,total_price,storage,verification,"
                "source_url}]}. Base every choice on the hypothesis."
            ),
            f"Hypothesis: {prompt}\nReturn JSON only.",
            agent_hint="materials",
        )
        result = rescued
        warning = f"primary materials call failed: {exc!s}"

    items = result.get("materials") if isinstance(result, dict) else None
    if not isinstance(items, list) or not items:
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "You are a lab materials expert. Return JSON "
                "{materials:[...]} listing at least five concrete items "
                "needed to test the hypothesis."
            ),
            f"Hypothesis: {prompt}\nJSON only.",
            agent_hint="materials",
        )
        items = rescued.get("materials") if isinstance(rescued, dict) else []
        warning = warning or "primary materials call returned no items"

    normalised: list[dict[str, Any]] = []
    for entry in items or []:
        if not isinstance(entry, dict):
            continue
        try:
            unit_price = float(entry.get("unit_price") or 0)
        except (TypeError, ValueError):
            unit_price = 0.0
        try:
            total_price = float(entry.get("total_price") or unit_price)
        except (TypeError, ValueError):
            total_price = unit_price
        normalised.append(
            {
                "item": str(entry.get("item") or "").strip() or "Unspecified reagent",
                "catalog_number": str(entry.get("catalog_number") or "n/a"),
                "supplier": str(entry.get("supplier") or "Unknown"),
                "quantity": str(entry.get("quantity") or "1 unit"),
                "unit_price": unit_price,
                "currency": str(entry.get("currency") or "EUR"),
                "total_price": total_price,
                "storage": entry.get("storage"),
                "verification": entry.get("verification") or "suggested_verify",
                "source_url": entry.get("source_url"),
            }
        )

    out: dict[str, Any] = {"materials": normalised}
    if warning:
        out["_warning"] = warning
    return out


async def budget_agent(
    materials: list[dict[str, Any]],
    prompt: str,
    settings: Settings,
    use_mock: bool,
    *,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    total = sum(float(item.get("total_price", 0) or 0) for item in materials)

    if not materials:
        return {
            "total": 0.0,
            "currency": "EUR",
            "breakdown": {"reagents": 0.0, "consumables": 0.0, "equipment_usage": 0.0},
            "notes": "No materials provided — budget cannot be computed.",
            "_warning": "empty materials list",
        }

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
    warning: str | None = None
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
        logger.warning("budget_agent: primary call failed, trying rescue: %s", exc)
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "You split a lab experiment budget into three buckets. "
                "Output JSON {currency, breakdown:{reagents,consumables,"
                "equipment_usage}, notes}. The three breakdown numbers must "
                "sum to the given TOTAL."
            ),
            f"Hypothesis: {prompt}\nTOTAL (EUR): {total:.2f}\nMaterials: {materials}",
            agent_hint="budget",
        )
        result = rescued
        warning = f"primary budget call failed: {exc!s}"

    breakdown = result.get("breakdown") if isinstance(result, dict) else None
    if not isinstance(breakdown, dict):
        rescued, _ = await _llm_rescue_json(
            settings,
            "Output JSON {breakdown:{reagents,consumables,equipment_usage},notes}.",
            f"Materials: {materials}\nTOTAL: {total:.2f}",
            agent_hint="budget",
        )
        if isinstance(rescued, dict) and isinstance(rescued.get("breakdown"), dict):
            breakdown = rescued["breakdown"]
            result = rescued
        else:
            breakdown = {}
        warning = warning or "primary budget call returned no breakdown"

    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    reagents = _num(breakdown.get("reagents"))
    consumables = _num(breakdown.get("consumables"))
    equipment_usage = _num(breakdown.get("equipment_usage"))
    bucket_sum = reagents + consumables + equipment_usage
    if bucket_sum <= 0 and total > 0:
        # LLM did not categorise — put everything under reagents rather
        # than inventing a 70/20/10 split. The notes will flag this.
        reagents = total
        consumables = 0.0
        equipment_usage = 0.0
        bucket_sum = total
        warning = warning or "LLM returned empty budget breakdown — all cost attributed to reagents"
    elif abs(bucket_sum - total) > 0.01 and total > 0:
        scale = total / bucket_sum
        reagents *= scale
        consumables *= scale
        equipment_usage *= scale

    notes = str(
        (result.get("notes") if isinstance(result, dict) else None)
        or "LLM-basierte Kostenaufteilung anhand der konkreten Materialien."
    )

    out: dict[str, Any] = {
        "total": round(total, 2),
        "currency": str(
            (result.get("currency") if isinstance(result, dict) else None) or "EUR"
        ),
        "breakdown": {
            "reagents": round(reagents, 2),
            "consumables": round(consumables, 2),
            "equipment_usage": round(equipment_usage, 2),
        },
        "notes": notes,
    }
    if warning:
        out["_warning"] = warning
    return out


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
    warning: str | None = None
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
        logger.warning("timeline_agent: primary call failed, trying rescue: %s", exc)
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "Group the given protocol steps into 2-4 phases. Output JSON "
                "{phases:[{phase,duration,tasks,dependencies,start_day}], "
                "total_duration}. Durations must match the step durations."
            ),
            f"Hypothesis: {prompt}\nSteps: {steps}\nProtocol total: {protocol_total}",
            agent_hint="timeline",
        )
        result = rescued
        warning = f"primary timeline call failed: {exc!s}"

    raw_phases = result.get("phases") if isinstance(result, dict) else None
    if not isinstance(raw_phases, list) or not raw_phases:
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "Design a wet-lab experiment timeline. Output JSON "
                "{phases:[{phase,duration,tasks,dependencies,start_day}], "
                "total_duration}. Derive all phases from the hypothesis and "
                "the given protocol steps."
            ),
            f"Hypothesis: {prompt}\nSteps: {steps}",
            agent_hint="timeline",
        )
        if isinstance(rescued, dict):
            raw_phases = rescued.get("phases")
            result = rescued
        warning = warning or "primary timeline call returned no phases"

    if not isinstance(raw_phases, list):
        raw_phases = []

    normalised_phases: list[dict[str, Any]] = []
    for idx, phase in enumerate(raw_phases, start=1):
        if not isinstance(phase, dict):
            continue
        name = phase.get("phase") or phase.get("name") or f"Phase {idx}"
        duration = phase.get("duration") or ""
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

    total_duration_raw = (
        (result.get("total_duration") if isinstance(result, dict) else None)
        or protocol_total
        or ""
    )

    out: dict[str, Any] = {
        "phases": normalised_phases,
        "total_duration": str(total_duration_raw) or "to be determined",
    }
    if warning:
        out["_warning"] = warning
    return out


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


_LITERATURE_CAP_TRIGGERS = {"literature", "references", "research"}

_VALID_NOVELTY_SIGNALS = {"exact_match", "similar_work_exists", "not_found"}


def _coerce_novelty_signal(raw: Any) -> str:
    """Map freie LLM-Outputs auf die vom Pydantic-Schema erlaubten Enum-Werte.

    Das Pydantic-Model akzeptiert nur `exact_match | similar_work_exists |
    not_found`. Einige Prompts/Modelle liefern Varianten wie `novel`,
    `moderate`, `contradicted` etc. — hier zentral auf den naechsten
    passenden Literal abbilden.
    """
    token = str(raw or "").strip().lower()
    if token in _VALID_NOVELTY_SIGNALS:
        return token
    if token in {"exact", "duplicate", "identical", "match"}:
        return "exact_match"
    if token in {"none", "no_match", "no", "novel", "new", "unique"}:
        return "not_found"
    if token in {
        "similar",
        "similar_work",
        "related",
        "partial",
        "partial_match",
        "moderate",
        "contradicted",
        "contradicts",
    }:
        return "similar_work_exists"
    return "similar_work_exists"


def _agent_allowed_tools(agent: AgentDefinition) -> set[str]:
    """Liefert die fuer einen Agent freigegebenen Tool-Namen.

    Quelle ist `agent.metadata.allowed_tools`. Agents mit Literatur-Capabilities
    erhalten Backward-Compatibility-Default `tavily.search` + `tavily.extract`.
    """
    metadata = agent.metadata or {}
    raw = metadata.get("allowed_tools") or []
    tools = {str(t).strip() for t in raw if str(t).strip()}
    caps = set(agent.capabilities)
    if caps & _LITERATURE_CAP_TRIGGERS and not tools:
        tools = {"tavily.search", "tavily.extract"}
    return tools


def _tool_calling_allowed(agent: AgentDefinition) -> bool:
    return bool(_agent_allowed_tools(agent))


def _build_tool_gateway(settings: Settings, tavily: TavilyClient) -> TavilyToolGateway:
    allowlist_from_env = tuple(
        token.strip()
        for token in settings.agent_tool_domain_allowlist.split(",")
        if token.strip()
    )
    return TavilyToolGateway(
        tavily,
        domain_allowlist=allowlist_from_env or ("pubmed", "nature"),
        timeout_seconds=settings.agent_tool_timeout_seconds,
        max_retries=settings.agent_tool_max_retries,
    )


def _extract_technique_hints(prompt: str, protocol: dict[str, Any] | None) -> list[str]:
    """Kurze Stichworte (Techniken/Assays) aus Prompt + Protokoll-Schritten."""
    hints: list[str] = []
    if protocol and isinstance(protocol, dict):
        for step in (protocol.get("steps") or [])[:3]:
            if isinstance(step, dict):
                label = _step_label(step, "").strip()
                if label:
                    hints.append(label)
    prompt_snippet = prompt.strip().split(".")[0]
    if prompt_snippet:
        hints.append(prompt_snippet[:120])
    return [h for h in hints if h][:3]


def _truncate(text: str, limit: int = 800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


async def _enrich_protocol_tools(
    prompt: str,
    gateway: TavilyToolGateway,
    agent: AgentDefinition,
    settings: Settings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Holt Referenz-Protokolle von protocols.io / nature-protocols / bio-protocol."""
    metadata = agent.metadata or {}
    allowed = _agent_allowed_tools(agent)
    max_calls = min(
        int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
        settings.agent_tool_max_calls,
    )
    include_domains = metadata.get("include_domains") or [
        "protocols.io",
        "nature.com",
        "bio-protocol.org",
    ]
    traces: list[dict[str, Any]] = []
    grounding: dict[str, Any] = {"reference_protocols": [], "snippets": []}
    if "tavily.search" not in allowed or max_calls < 1:
        return grounding, traces

    query = f"{prompt} experimental protocol step by step"
    try:
        results, trace = await gateway.search_domains(
            query, include_domains=include_domains, max_results=3, call_index=1
        )
        traces.append(trace.as_dict())
    except Exception as exc:  # noqa: BLE001
        traces.append(
            {
                "tool": "tavily.search",
                "status": "error",
                "call_index": 1,
                "payload": {"query": query, "error_class": gateway.classify_error(exc)},
                "error": str(exc),
            }
        )
        return grounding, traces

    grounding["reference_protocols"] = [
        {"title": r.get("title"), "url": r.get("url"), "snippet": _truncate(r.get("content") or "", 400)}
        for r in results
    ]

    if "tavily.extract" in allowed and max_calls >= 2 and results:
        urls = [r.get("url") for r in results if r.get("url")][:2]
        try:
            extracts, trace = await gateway.extract(urls, call_index=2)
            traces.append(trace.as_dict())
            grounding["snippets"] = [
                _truncate(entry.get("raw_content") or entry.get("content") or "", 1200)
                for entry in extracts
            ]
        except Exception as exc:  # noqa: BLE001
            traces.append(
                {
                    "tool": "tavily.extract",
                    "status": "error",
                    "call_index": 2,
                    "payload": {"urls": urls, "error_class": gateway.classify_error(exc)},
                    "error": str(exc),
                }
            )
    return grounding, traces


async def _verify_materials_tools(
    materials: list[dict[str, Any]],
    gateway: TavilyToolGateway,
    agent: AgentDefinition,
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sucht Supplier-URLs fuer unverifizierte Materialien, extrahiert Produktseiten."""
    metadata = agent.metadata or {}
    allowed = _agent_allowed_tools(agent)
    max_calls = min(
        int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
        settings.agent_tool_max_calls,
    )
    traces: list[dict[str, Any]] = []
    if "tavily.search" not in allowed or max_calls < 1 or not materials:
        return materials, traces

    include_domains = metadata.get("include_domains") or [
        "sigmaaldrich.com",
        "thermofisher.com",
        "neb.com",
        "bio-rad.com",
        "abcam.com",
    ]

    unverified = [
        (idx, item)
        for idx, item in enumerate(materials)
        if isinstance(item, dict)
        and item.get("verification") != "verified"
        and (item.get("item") or item.get("catalog_number"))
    ]
    budget = max(1, max_calls)
    patched = [dict(item) if isinstance(item, dict) else item for item in materials]
    call_index = 0
    for idx, item in unverified[:budget]:
        call_index += 1
        needle = item.get("catalog_number") or item.get("item") or ""
        query = f"{item.get('item','')} {needle} {item.get('supplier','')}".strip()
        try:
            results, trace = await gateway.search_domains(
                query,
                include_domains=include_domains,
                max_results=2,
                call_index=call_index,
            )
            traces.append(trace.as_dict())
        except Exception as exc:  # noqa: BLE001
            traces.append(
                {
                    "tool": "tavily.search",
                    "status": "error",
                    "call_index": call_index,
                    "payload": {"query": query, "error_class": gateway.classify_error(exc)},
                    "error": str(exc),
                }
            )
            continue
        if not results:
            continue
        best = results[0]
        url = best.get("url")
        snippet = (best.get("content") or "").strip()
        if url:
            patched[idx]["source_url"] = url
            patched[idx]["verification"] = "verified"
            patched[idx]["verification_snippet"] = _truncate(snippet, 300)
    return patched, traces


async def _enrich_budget_tools(
    materials: list[dict[str, Any]],
    gateway: TavilyToolGateway,
    agent: AgentDefinition,
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """/extract auf source_urls der teuersten Items, um Preise zu validieren."""
    metadata = agent.metadata or {}
    allowed = _agent_allowed_tools(agent)
    max_calls = min(
        int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
        settings.agent_tool_max_calls,
    )
    traces: list[dict[str, Any]] = []
    if "tavily.extract" not in allowed or max_calls < 1 or not materials:
        return [], traces

    ranked = sorted(
        [m for m in materials if isinstance(m, dict) and m.get("source_url")],
        key=lambda m: float(m.get("total_price", 0) or 0),
        reverse=True,
    )[:max_calls]
    if not ranked:
        return [], traces
    urls = [str(m["source_url"]) for m in ranked]
    try:
        extracts, trace = await gateway.extract(urls, call_index=1)
        traces.append(trace.as_dict())
    except Exception as exc:  # noqa: BLE001
        traces.append(
            {
                "tool": "tavily.extract",
                "status": "error",
                "call_index": 1,
                "payload": {"urls": urls, "error_class": gateway.classify_error(exc)},
                "error": str(exc),
            }
        )
        return [], traces
    enriched = []
    for material, entry in zip(ranked, extracts):
        text = entry.get("raw_content") or entry.get("content") or ""
        enriched.append(
            {
                "item": material.get("item"),
                "catalog_number": material.get("catalog_number"),
                "url": material.get("source_url"),
                "stated_price": material.get("unit_price"),
                "page_snippet": _truncate(text, 600),
            }
        )
    return enriched, traces


async def _enrich_timeline_tools(
    prompt: str,
    protocol: dict[str, Any],
    gateway: TavilyToolGateway,
    agent: AgentDefinition,
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Kurze Web-Suche nach typischen Dauern pro Technik."""
    metadata = agent.metadata or {}
    allowed = _agent_allowed_tools(agent)
    max_calls = min(
        int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
        settings.agent_tool_max_calls,
    )
    traces: list[dict[str, Any]] = []
    if "tavily.search" not in allowed or max_calls < 1:
        return [], traces

    hints = _extract_technique_hints(prompt, protocol)[:max_calls]
    if not hints:
        return [], traces
    include_domains = metadata.get("include_domains") or [
        "protocols.io",
        "nature.com",
        "bio-protocol.org",
    ]
    benchmarks: list[dict[str, Any]] = []
    for idx, hint in enumerate(hints, start=1):
        query = f"typical duration wet lab {hint}"
        try:
            results, trace = await gateway.search_domains(
                query, include_domains=include_domains, max_results=2, call_index=idx
            )
            traces.append(trace.as_dict())
        except Exception as exc:  # noqa: BLE001
            traces.append(
                {
                    "tool": "tavily.search",
                    "status": "error",
                    "call_index": idx,
                    "payload": {"query": query, "error_class": gateway.classify_error(exc)},
                    "error": str(exc),
                }
            )
            continue
        for r in results:
            benchmarks.append(
                {
                    "technique": hint,
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": _truncate(r.get("content") or "", 300),
                }
            )
    return benchmarks, traces


async def _review_tools(
    literature: dict[str, Any],
    protocol: dict[str, Any],
    prompt: str,
    gateway: TavilyToolGateway,
    agent: AgentDefinition,
    settings: Settings,
) -> tuple[list[ReviewIssue], list[dict[str, Any]]]:
    """Retraction-Watch-Check + Pitfall-Suche pro zentraler Technik."""
    metadata = agent.metadata or {}
    allowed = _agent_allowed_tools(agent)
    max_calls = min(
        int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
        settings.agent_tool_max_calls,
    )
    issues: list[ReviewIssue] = []
    traces: list[dict[str, Any]] = []
    if "tavily.search" not in allowed or max_calls < 1:
        return issues, traces

    remaining = max_calls
    refs = (
        [r for r in (literature.get("references") or []) if isinstance(r, dict)]
        if isinstance(literature, dict)
        else []
    )

    call_idx = 0
    if refs and remaining > 0:
        titles = " ; ".join((r.get("title") or "") for r in refs[:2]).strip(" ;")
        if titles:
            call_idx += 1
            query = f"retraction notice {titles}"
            try:
                results, trace = await gateway.search_domains(
                    query,
                    include_domains=["retractionwatch.com", "pubpeer.com"],
                    max_results=2,
                    call_index=call_idx,
                )
                traces.append(trace.as_dict())
                if results:
                    issues.append(
                        ReviewIssue(
                            severity="warning",
                            message=(
                                "Referenzen koennten Retraction/PubPeer-Einträge haben: "
                                + "; ".join(r.get("title", "?") for r in results[:2])
                            ),
                            path="literature.references",
                        )
                    )
                remaining -= 1
            except Exception as exc:  # noqa: BLE001
                traces.append(
                    {
                        "tool": "tavily.search",
                        "status": "error",
                        "call_index": call_idx,
                        "payload": {"query": query, "error_class": gateway.classify_error(exc)},
                        "error": str(exc),
                    }
                )

    hints = _extract_technique_hints(prompt, protocol)
    for hint in hints:
        if remaining <= 0:
            break
        call_idx += 1
        query = f"{hint} known pitfalls failure modes troubleshooting"
        try:
            results, trace = await gateway.search_domains(
                query,
                include_domains=["protocols.io", "nature.com", "bio-protocol.org"],
                max_results=2,
                call_index=call_idx,
            )
            traces.append(trace.as_dict())
            if results:
                top = results[0]
                issues.append(
                    ReviewIssue(
                        severity="info",
                        message=(
                            f"Bekannte Pitfalls fuer '{hint}' vorhanden: {top.get('title')}"
                        ),
                        path=f"protocol.techniques::{hint}",
                    )
                )
            remaining -= 1
        except Exception as exc:  # noqa: BLE001
            traces.append(
                {
                    "tool": "tavily.search",
                    "status": "error",
                    "call_index": call_idx,
                    "payload": {"query": query, "error_class": gateway.classify_error(exc)},
                    "error": str(exc),
                }
            )
    return issues, traces


async def _merge_protocol_with_grounding(
    draft: dict[str, Any],
    grounding: dict[str, Any],
    prompt: str,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Nachgelagerter LLM-Call, der die Tavily-Protokoll-Snippets in die Steps einpflegt.

    Ergebnis: Same protocol shape, aber die Schritte werden mit konkreten
    Reagenz-Mengen, Inkubationszeiten und einem `citation_url` pro Step
    angereichert wenn die Grounding-Daten das hergeben.
    """
    references = grounding.get("reference_protocols") or []
    snippets = grounding.get("snippets") or []
    if not references and not snippets:
        return draft, None

    system = (
        "You are a protocol post-processor. Given a DRAFT protocol and REFERENCE "
        "protocols fetched from protocols.io / nature-protocols / bio-protocol, "
        "produce an ENRICHED protocol JSON with the SAME shape as the draft but:\n"
        "- keep step_number order and total step count close to the draft\n"
        "- upgrade each step's `action` and `details` with concrete reagent "
        "concentrations, incubation times and temperatures drawn from the "
        "references when possible (do NOT invent numbers that are not in the "
        "references or common lab practice)\n"
        "- for every step, add a `citation_url` field pointing to the most "
        "relevant reference URL if one supports the step; leave it empty otherwise\n"
        "- refine `controls` to match what the references actually recommend\n"
        "- set `total_duration` to a realistic sum\n\n"
        "Return JSON with keys: steps (list of {step_number, action, duration, "
        "details, citation_url}), total_duration (string), controls (list of strings)."
    )
    user = (
        f"Hypothesis: {prompt}\n\n"
        f"DRAFT protocol: {json.dumps(draft, ensure_ascii=False)[:4000]}\n\n"
        f"REFERENCE protocols (Tavily search): {json.dumps(references, ensure_ascii=False)[:3000]}\n\n"
        f"REFERENCE extracted text (truncated): {json.dumps(snippets, ensure_ascii=False)[:3500]}"
    )
    trace = {
        "tool": "openai.merge",
        "status": "completed",
        "call_index": 1,
        "payload": {"agent": "protocol", "refs": len(references), "snippets": len(snippets)},
    }
    try:
        merged = await _openai_json(settings, system, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("protocol merge: falling back (OpenAI error): %s", exc)
        trace["status"] = "error"
        trace["error"] = str(exc)
        return draft, trace

    steps = _normalize_protocol_steps(merged.get("steps"), prompt)
    if not steps:
        trace["status"] = "skipped"
        trace["payload"]["reason"] = "llm_returned_no_steps"
        return draft, trace

    for step in steps:
        citation = (merged.get("steps") or [{}])
        try:
            src_step = next(
                (s for s in merged.get("steps", []) if int(s.get("step_number", -1)) == int(step.get("step_number", -2))),
                None,
            )
            if src_step and src_step.get("citation_url"):
                step["citation_url"] = str(src_step["citation_url"]).strip()
        except Exception:  # noqa: BLE001
            pass

    controls = merged.get("controls")
    if not isinstance(controls, list) or not controls:
        controls = draft.get("controls") or []

    total = merged.get("total_duration") or draft.get("total_duration") or ""
    return (
        {
            "steps": steps,
            "total_duration": str(total),
            "controls": [str(c) for c in controls],
        },
        trace,
    )


async def _merge_materials_with_supplier_data(
    draft_materials: list[dict[str, Any]],
    prompt: str,
    settings: Settings,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """LLM-Merge: schreibt aus Tavily-Supplier-Snippets (bereits an den Materials
    annotiert als `verification_snippet` + `source_url`) echte catalog_numbers,
    unit_prices und supplier in die materials Liste."""
    relevant = [
        m
        for m in draft_materials
        if isinstance(m, dict) and (m.get("verification_snippet") or m.get("source_url"))
    ]
    if not relevant:
        return draft_materials, None

    system = (
        "You are a lab materials post-processor. Given a DRAFT list of materials "
        "and SUPPLIER SNIPPETS pulled from sigmaaldrich / thermofisher / neb / "
        "bio-rad / abcam / cytiva, return the SAME list but with each matching "
        "item upgraded to reflect the supplier data:\n"
        "- overwrite `catalog_number` if the snippet clearly shows a catalog ID\n"
        "- overwrite `supplier` to match the real vendor from the URL\n"
        "- overwrite `unit_price` ONLY if the snippet explicitly states a price "
        "in EUR or USD (convert USD to EUR using 0.92). Do NOT guess.\n"
        "- recompute `total_price = unit_price * qty` when unit_price changes; "
        "if quantity is non-numeric, leave total_price as stated\n"
        "- keep `verification='verified'` when source_url is set and snippet "
        "confirms the product, else 'suggested_verify'\n"
        "- keep the same item order and number of items.\n\n"
        "Return JSON with key `materials` (list of objects: item, catalog_number, "
        "supplier, quantity, unit_price, currency, total_price, storage, "
        "verification, source_url)."
    )
    user = (
        f"Hypothesis: {prompt}\n\n"
        f"DRAFT materials (each item already carries verification_snippet + "
        f"source_url from a Tavily vendor search): "
        f"{json.dumps(draft_materials, ensure_ascii=False)[:6000]}"
    )
    trace = {
        "tool": "openai.merge",
        "status": "completed",
        "call_index": 1,
        "payload": {"agent": "materials", "items": len(draft_materials)},
    }
    try:
        merged = await _openai_json(settings, system, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("materials merge: falling back (OpenAI error): %s", exc)
        trace["status"] = "error"
        trace["error"] = str(exc)
        return draft_materials, trace

    items = merged.get("materials")
    if not isinstance(items, list) or len(items) != len(draft_materials):
        trace["status"] = "skipped"
        trace["payload"]["reason"] = "length_mismatch"
        return draft_materials, trace

    out: list[dict[str, Any]] = []
    for original, upgraded in zip(draft_materials, items):
        if not isinstance(upgraded, dict):
            out.append(original)
            continue
        merged_item = dict(original)
        for key in (
            "item",
            "catalog_number",
            "supplier",
            "quantity",
            "unit_price",
            "currency",
            "total_price",
            "storage",
            "verification",
            "source_url",
        ):
            if upgraded.get(key) not in (None, "", []):
                merged_item[key] = upgraded[key]
        try:
            merged_item["unit_price"] = float(merged_item.get("unit_price") or 0)
            merged_item["total_price"] = float(merged_item.get("total_price") or 0)
        except (TypeError, ValueError):
            pass
        if merged_item.get("verification") not in {"verified", "suggested_verify"}:
            merged_item["verification"] = original.get("verification", "suggested_verify")
        out.append(merged_item)
    return out, trace


async def _merge_budget_with_prices(
    draft_budget: dict[str, Any],
    materials: list[dict[str, Any]],
    price_context: list[dict[str, Any]],
    prompt: str,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """LLM-Merge: verrechnet verifizierte Preise in total/breakdown/notes."""
    if not price_context:
        return draft_budget, None

    system = (
        "You are a budget post-processor. Given a DRAFT budget, the current "
        "MATERIALS list, and PRICE EVIDENCE extracted from supplier product "
        "pages, return an updated budget that reflects the verified prices.\n"
        "- `breakdown` must be a dict with numeric keys reagents, consumables, "
        "equipment_usage; assign each material to the most sensible bucket.\n"
        "- `total` MUST equal the sum of the breakdown values.\n"
        "- Populate `notes` with a short human-readable list of detected price "
        "discrepancies: e.g. 'Anti-CRP Ab: stated 395 EUR, supplier page shows "
        "425 EUR (abcam.com)'. If all prices check out, set notes to 'All "
        "supplier prices within 10% of the draft.'\n"
        "- Keep currency = 'EUR'. Round numbers to 2 decimals.\n\n"
        "Return JSON: {total, currency, breakdown:{reagents,consumables,"
        "equipment_usage}, notes}."
    )
    user = (
        f"Hypothesis: {prompt}\n\n"
        f"DRAFT budget: {json.dumps(draft_budget, ensure_ascii=False)[:2000]}\n\n"
        f"MATERIALS: {json.dumps(materials, ensure_ascii=False)[:3500]}\n\n"
        f"PRICE EVIDENCE: {json.dumps(price_context, ensure_ascii=False)[:3500]}"
    )
    trace = {
        "tool": "openai.merge",
        "status": "completed",
        "call_index": 1,
        "payload": {"agent": "budget", "evidence": len(price_context)},
    }
    try:
        merged = await _openai_json(settings, system, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("budget merge: falling back (OpenAI error): %s", exc)
        trace["status"] = "error"
        trace["error"] = str(exc)
        return draft_budget, trace

    breakdown = merged.get("breakdown") or {}
    if not isinstance(breakdown, dict):
        trace["status"] = "skipped"
        trace["payload"]["reason"] = "invalid_breakdown"
        return draft_budget, trace

    def _num(value: Any, fallback: float = 0.0) -> float:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return fallback

    reagents = _num(breakdown.get("reagents"), _num(draft_budget.get("breakdown", {}).get("reagents")))
    consumables = _num(breakdown.get("consumables"), _num(draft_budget.get("breakdown", {}).get("consumables")))
    equipment = _num(breakdown.get("equipment_usage"), _num(draft_budget.get("breakdown", {}).get("equipment_usage")))
    total = _num(merged.get("total"), reagents + consumables + equipment)
    if abs(total - (reagents + consumables + equipment)) > 0.05:
        total = round(reagents + consumables + equipment, 2)

    notes = merged.get("notes")
    if not isinstance(notes, str) or not notes.strip():
        notes = draft_budget.get("notes") or ""

    out = dict(draft_budget)
    out.update(
        {
            "total": total,
            "currency": merged.get("currency") or draft_budget.get("currency") or "EUR",
            "breakdown": {
                "reagents": reagents,
                "consumables": consumables,
                "equipment_usage": equipment,
            },
            "notes": notes.strip(),
        }
    )
    return out, trace


async def _merge_timeline_with_benchmarks(
    draft_timeline: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    prompt: str,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """LLM-Merge: passt phase durations anhand von Benchmark-URLs an und fuegt rationale hinzu."""
    if not benchmarks:
        return draft_timeline, None

    system = (
        "You are a timeline post-processor. Given a DRAFT timeline and DURATION "
        "BENCHMARKS fetched via Tavily (published wet-lab timings), return an "
        "updated timeline:\n"
        "- keep the same phase order and count\n"
        "- adjust each phase's `duration` to a realistic value consistent with "
        "the benchmarks (human-readable strings like '2 days', '4 hours')\n"
        "- recompute `start_day` so phases stack correctly (respect dependencies)\n"
        "- add a `rationale` field per phase citing the benchmark URL that "
        "justified the duration (empty if no matching benchmark)\n"
        "- update `total_duration` accordingly\n\n"
        "Return JSON: {phases:[{phase, duration, tasks, dependencies, start_day, "
        "rationale}], total_duration}."
    )
    user = (
        f"Hypothesis: {prompt}\n\n"
        f"DRAFT timeline: {json.dumps(draft_timeline, ensure_ascii=False)[:3000]}\n\n"
        f"DURATION BENCHMARKS: {json.dumps(benchmarks, ensure_ascii=False)[:3500]}"
    )
    trace = {
        "tool": "openai.merge",
        "status": "completed",
        "call_index": 1,
        "payload": {"agent": "timeline", "benchmarks": len(benchmarks)},
    }
    try:
        merged = await _openai_json(settings, system, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("timeline merge: falling back (OpenAI error): %s", exc)
        trace["status"] = "error"
        trace["error"] = str(exc)
        return draft_timeline, trace

    phases_raw = merged.get("phases")
    if not isinstance(phases_raw, list) or not phases_raw:
        trace["status"] = "skipped"
        trace["payload"]["reason"] = "no_phases"
        return draft_timeline, trace

    normalized_phases: list[dict[str, Any]] = []
    draft_phases = draft_timeline.get("phases") if isinstance(draft_timeline, dict) else []
    draft_phases = draft_phases or []
    for idx, phase in enumerate(phases_raw):
        if not isinstance(phase, dict):
            continue
        fallback = draft_phases[idx] if idx < len(draft_phases) and isinstance(draft_phases[idx], dict) else {}
        name = str(phase.get("phase") or fallback.get("phase") or f"Phase {idx + 1}")
        duration = str(phase.get("duration") or fallback.get("duration") or "1 day")
        tasks_raw = phase.get("tasks") or fallback.get("tasks") or []
        tasks = [str(t) for t in tasks_raw if str(t).strip()]
        deps_raw = phase.get("dependencies") or fallback.get("dependencies") or []
        deps = [str(d) for d in deps_raw if str(d).strip()]
        try:
            start_day = int(phase.get("start_day") if phase.get("start_day") is not None else fallback.get("start_day", idx))
        except (TypeError, ValueError):
            start_day = idx
        rationale = str(phase.get("rationale") or "").strip()
        entry = {
            "phase": name,
            "duration": duration,
            "tasks": tasks,
            "dependencies": deps,
            "start_day": start_day,
        }
        if rationale:
            entry["rationale"] = rationale
        normalized_phases.append(entry)

    if not normalized_phases:
        trace["status"] = "skipped"
        trace["payload"]["reason"] = "normalization_empty"
        return draft_timeline, trace

    total = merged.get("total_duration") or draft_timeline.get("total_duration") or ""
    return ({"phases": normalized_phases, "total_duration": str(total)}, trace)


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
    tools_on = (
        settings.agent_tool_calling_enabled
        and _tool_calling_allowed(agent)
        and not use_mock
    )
    gateway = _build_tool_gateway(settings, tavily) if tools_on else None

    if agent.key == "literature":
        if tools_on and gateway is not None:
            metadata = agent.metadata or {}
            max_calls = min(
                int(metadata.get("max_tool_calls", settings.agent_tool_max_calls)),
                settings.agent_tool_max_calls,
            )
            max_results = int(metadata.get("max_results", 3))
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
                    (
                        f"{system_prompt}\nReturn JSON with novelty_signal "
                        "(EXACTLY one of 'exact_match' | 'similar_work_exists' "
                        "| 'not_found'), summary, references."
                    ),
                    f"Hypothesis: {prompt}\nEvidence: {evidence}",
                )
                output = {
                    "novelty_signal": _coerce_novelty_signal(summary.get("novelty_signal")),
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
        grounding: dict[str, Any] = {}
        if tools_on and gateway is not None:
            grounding, protocol_traces = await _enrich_protocol_tools(
                prompt, gateway, agent, settings
            )
            traces.extend(protocol_traces)
        grounded_sp = system_prompt
        if grounding.get("reference_protocols"):
            grounded_sp += (
                "\n\nGrounding: die folgenden veroeffentlichten Protokolle wurden "
                "per Tavily abgerufen. Nutze sie als Vorbild, zitiere die URLs bei "
                "Bedarf und bleibe bei realen Methoden statt zu halluzinieren.\n"
                f"{grounding['reference_protocols']}"
            )
        if grounding.get("snippets"):
            grounded_sp += f"\n\nTextausschnitte (gekuerzt): {grounding['snippets']}"
        output = await protocol_designer(prompt, settings, use_mock, system_prompt=grounded_sp)
        if (
            tools_on
            and isinstance(output, dict)
            and (grounding.get("reference_protocols") or grounding.get("snippets"))
        ):
            output, merge_trace = await _merge_protocol_with_grounding(
                output, grounding, prompt, settings
            )
            if merge_trace is not None:
                traces.append(merge_trace)
        if isinstance(output, dict) and grounding.get("reference_protocols"):
            output["_grounding_sources"] = [
                {"title": r["title"], "url": r["url"]}
                for r in grounding["reference_protocols"]
                if r.get("url")
            ]
        return output, traces

    if agent.key == "materials":
        raw = await materials_agent(prompt, settings, use_mock, system_prompt=system_prompt)
        materials = raw["materials"] if isinstance(raw, dict) else raw
        if tools_on and gateway is not None and isinstance(materials, list):
            materials, mat_traces = await _verify_materials_tools(
                materials, gateway, agent, settings
            )
            traces.extend(mat_traces)
            materials, merge_trace = await _merge_materials_with_supplier_data(
                materials, prompt, settings
            )
            if merge_trace is not None:
                traces.append(merge_trace)
        return materials, traces

    if agent.key == "budget":
        materials = state.get("materials") if isinstance(state.get("materials"), list) else []
        price_context: list[dict[str, Any]] = []
        if tools_on and gateway is not None:
            price_context, budget_traces = await _enrich_budget_tools(
                materials, gateway, agent, settings
            )
            traces.extend(budget_traces)
        grounded_sp = system_prompt
        if price_context:
            grounded_sp += (
                "\n\nVerified supplier pages (via Tavily /extract). Use them as a "
                "reality check for the most expensive items; flag significant "
                "price deviations in the `notes` field.\n"
                f"{price_context}"
            )
        output = await budget_agent(
            materials,
            prompt,
            settings,
            use_mock,
            system_prompt=grounded_sp,
        )
        if tools_on and isinstance(output, dict) and price_context:
            output, merge_trace = await _merge_budget_with_prices(
                output, materials, price_context, prompt, settings
            )
            if merge_trace is not None:
                traces.append(merge_trace)
        if isinstance(output, dict) and price_context:
            output["_price_verification"] = price_context
        return output, traces

    if agent.key == "timeline":
        protocol_state = state["protocol"] if isinstance(state.get("protocol"), dict) else {}
        benchmarks: list[dict[str, Any]] = []
        if tools_on and gateway is not None:
            benchmarks, tl_traces = await _enrich_timeline_tools(
                prompt, protocol_state, gateway, agent, settings
            )
            traces.extend(tl_traces)
        grounded_sp = system_prompt
        if benchmarks:
            grounded_sp += (
                "\n\nDuration benchmarks from the web (via Tavily /search). Use "
                "them to sanity-check phase durations; prefer published timings "
                "over guesses.\n"
                f"{benchmarks}"
            )
        output = await timeline_agent(
            protocol_state,
            prompt,
            settings,
            use_mock,
            system_prompt=grounded_sp,
        )
        if tools_on and isinstance(output, dict) and benchmarks:
            output, merge_trace = await _merge_timeline_with_benchmarks(
                output, benchmarks, prompt, settings
            )
            if merge_trace is not None:
                traces.append(merge_trace)
        if isinstance(output, dict) and benchmarks:
            output["_duration_benchmarks"] = benchmarks
        return output, traces

    if agent.key == "review":
        issues = await review_agent(state["protocol"], state["materials"], state["budget"])
        if tools_on and gateway is not None:
            extra, review_traces = await _review_tools(
                state.get("literature") if isinstance(state.get("literature"), dict) else {},
                state["protocol"] if isinstance(state["protocol"], dict) else {},
                prompt,
                gateway,
                agent,
                settings,
            )
            issues.extend(extra)
            traces.extend(review_traces)
        return [issue.model_dump() for issue in issues], traces

    raise RuntimeError(f"Unbekannter Agent: {agent.key}")


async def validation_agent(
    prompt: str,
    protocol: dict[str, Any],
    materials: list[dict[str, Any]],
    settings: Settings,
    use_mock: bool,
) -> dict[str, Any]:
    validation_schema = (
        "Return JSON with keys: success_criteria (list of 3-5 concrete, "
        "measurable criteria tied to the hypothesis; include numeric "
        "thresholds with units where possible, derived from the actual "
        "materials and steps), controls (list of strings covering negative, "
        "positive and matrix/blank controls appropriate for THIS protocol "
        "and reagents), statistical_plan (one sentence describing replicate "
        "count and the statistical test used for evaluation, tuned to the "
        "detection modality)."
    )
    base_sp = (
        "You are a validation agent that defines hypothesis-specific, "
        "measurable success criteria, required controls and a statistical "
        "analysis plan for wet-lab experiments. Never emit generic "
        "placeholders — every output must be justified by the given "
        "protocol / materials."
    )
    steps = protocol.get("steps", []) if isinstance(protocol, dict) else []
    protocol_controls = (
        protocol.get("controls", []) if isinstance(protocol, dict) else []
    )
    warning: str | None = None
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
        logger.warning("validation_agent: primary call failed, trying rescue: %s", exc)
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "Output JSON {success_criteria:[...], controls:[...], "
                "statistical_plan:'...'} for the experiment. Be specific "
                "to the hypothesis, protocol and materials."
            ),
            f"Hypothesis: {prompt}\nSteps: {steps}\nMaterials: {materials[:10]}",
            agent_hint="validation",
        )
        result = rescued
        warning = f"primary validation call failed: {exc!s}"

    criteria = [
        str(c).strip()
        for c in ((result.get("success_criteria") if isinstance(result, dict) else None) or [])
        if str(c).strip()
    ]
    controls = [
        str(c).strip()
        for c in ((result.get("controls") if isinstance(result, dict) else None) or [])
        if str(c).strip()
    ]
    stat_plan = result.get("statistical_plan") if isinstance(result, dict) else None

    if not criteria or not controls or not stat_plan:
        rescued, _ = await _llm_rescue_json(
            settings,
            (
                "Return JSON {success_criteria, controls, statistical_plan}. "
                "Three concrete success criteria, three concrete controls, "
                "one statistical plan sentence — all specific to the "
                "hypothesis."
            ),
            f"Hypothesis: {prompt}\nProtocol: {steps}\nMaterials: {materials[:10]}",
            agent_hint="validation",
        )
        if isinstance(rescued, dict):
            criteria = criteria or [
                str(c).strip() for c in (rescued.get("success_criteria") or []) if str(c).strip()
            ]
            controls = controls or [
                str(c).strip() for c in (rescued.get("controls") or []) if str(c).strip()
            ]
            stat_plan = stat_plan or rescued.get("statistical_plan")
        warning = warning or "primary validation call returned incomplete payload"

    out = {
        "success_criteria": criteria,
        "controls": controls,
        "statistical_plan": str(stat_plan or "").strip() or "To be defined based on data distribution.",
    }
    if warning:
        out["_warning"] = warning
    return out


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
