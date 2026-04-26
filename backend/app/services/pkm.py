"""PKM-Pipeline: Candidate-Extraction, Dedupe, Retrieval, Proposals.

Diese Schicht sitzt zwischen dem Plan-Output und der Knowledge-Graph-Persistenz.
Wichtigste Designentscheidung: **kein automatischer Insert** – alle Methoden
hier liefern Kandidaten, das eigentliche Persistieren passiert erst nach
expliziter User-Aktion (Accept/Confirm) im Endpoint-Layer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.schemas.plan import (
    ExperimentPlan,
    KnowledgeCandidates,
    KnowledgeChatCitation,
    KnowledgeChatResponse,
    KnowledgeEdge,
    KnowledgeNode,
)

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
EMBEDDING_BATCH = 16

DEDUPE_EMBEDDING_THRESHOLD = 0.85
DEDUPE_TRIGRAM_THRESHOLD = 0.6


# === Candidate-Extraktion =================================================


def _slugify(value: str, *, max_len: int = 60) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    if not cleaned:
        cleaned = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return cleaned[:max_len]


def _hash_id(*parts: str, prefix: str) -> str:
    raw = "::".join(parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def extract_knowledge_candidates(plan: ExperimentPlan) -> KnowledgeCandidates:
    """Erzeuge Kandidaten-Knoten und -Kanten aus einem Plan.

    Liefert IMMER `status='pending'`, `source_type='plan_draft'` und
    `source_ref=plan_id`. Persistierung passiert ausschließlich im
    Accept-Endpoint nach Dedupe.
    """
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []

    plan_id = plan.plan_id
    experiment_type = (
        plan.metadata.get("experiment_type") if isinstance(plan.metadata, dict) else None
    )

    # 1) Experiment-Knoten als Anker
    experiment_id = f"kn-exp-{plan_id}"
    nodes.append(
        KnowledgeNode(
            id=experiment_id,
            title=plan.title,
            node_type="experiment",
            experiment_type=experiment_type,
            content=plan.hypothesis,
            tags=["experiment", "plan_draft"],
            status="pending",
            source_type="plan_draft",
            source_ref=plan_id,
            confidence=0.75,
            created_by="pkm-extractor",
        )
    )

    # 2) Reagenzien (deduplizierbar via supplier+catalog)
    for idx, material in enumerate(plan.materials or []):
        catalog = material.catalog_number or "n_a"
        supplier = material.supplier or "unknown"
        reagent_id = _hash_id(supplier.lower(), catalog.lower(), prefix="kn-reagent")
        nodes.append(
            KnowledgeNode(
                id=reagent_id,
                title=material.item,
                node_type="reagent",
                experiment_type=experiment_type,
                content=f"{supplier} • {catalog} • {material.quantity}",
                metadata={
                    "supplier": supplier,
                    "catalog_number": catalog,
                    "unit_price": material.unit_price,
                    "currency": material.currency,
                    "verification": material.verification,
                },
                tags=["reagent", supplier.lower()],
                status="pending",
                source_type="plan_draft",
                source_ref=plan_id,
                confidence=0.65 if material.verification == "verified" else 0.45,
                created_by="pkm-extractor",
            )
        )
        edges.append(
            KnowledgeEdge(
                source_id=experiment_id,
                target_id=reagent_id,
                relationship_type="uses",
                weight=1.0,
                source_type="plan_draft",
                source_ref=plan_id,
            )
        )

    # 3) Literatur-Referenzen (eine pro Paper, dedupliziert via DOI/Title)
    for ref in (plan.literature_qc.references or []):
        identifier = (ref.doi or ref.url or ref.title or "").strip()
        if not identifier:
            continue
        lit_id = _hash_id(identifier.lower(), prefix="kn-lit")
        body_parts = [ref.authors, ref.journal, str(ref.year) if ref.year else None]
        nodes.append(
            KnowledgeNode(
                id=lit_id,
                title=ref.title,
                node_type="literature",
                experiment_type=experiment_type,
                content=" • ".join(p for p in body_parts if p) or None,
                metadata={
                    "doi": ref.doi,
                    "url": ref.url,
                    "year": ref.year,
                    "similarity": ref.similarity,
                    "key_difference": ref.key_difference,
                },
                tags=["literature"],
                status="pending",
                source_type="plan_draft",
                source_ref=plan_id,
                confidence=0.7,
                created_by="pkm-extractor",
            )
        )
        edges.append(
            KnowledgeEdge(
                source_id=experiment_id,
                target_id=lit_id,
                relationship_type="references",
                weight=0.8,
                source_type="plan_draft",
                source_ref=plan_id,
            )
        )

    # 4) Protokoll-Schritte → "claim"-Knoten nur, wenn `notes`/Critical Note vorhanden
    #    (sonst fluten wir den Graph mit trivialen Schritten).
    for step in (plan.protocol.steps or []):
        if not step.notes:
            continue
        claim_id = _hash_id(plan_id, str(step.step_number), step.action.lower(), prefix="kn-claim")
        nodes.append(
            KnowledgeNode(
                id=claim_id,
                title=f"{step.action} (Schritt {step.step_number})",
                node_type="claim",
                experiment_type=experiment_type,
                content=f"{step.details}\n\nCritical: {step.notes}",
                tags=["claim", "protocol"],
                metadata={"step_number": step.step_number, "duration": step.duration},
                status="pending",
                source_type="plan_draft",
                source_ref=plan_id,
                confidence=0.6,
                created_by="pkm-extractor",
            )
        )
        edges.append(
            KnowledgeEdge(
                source_id=experiment_id,
                target_id=claim_id,
                relationship_type="includes_step",
                weight=0.9,
                source_type="plan_draft",
                source_ref=plan_id,
            )
        )

    return KnowledgeCandidates(nodes=nodes, edges=edges)


def candidate_summary(candidates: KnowledgeCandidates) -> dict[str, int]:
    summary: dict[str, int] = {}
    for node in candidates.nodes:
        summary[node.node_type] = summary.get(node.node_type, 0) + 1
    summary["edges"] = len(candidates.edges)
    summary["total_nodes"] = len(candidates.nodes)
    return summary


# === Embeddings ===========================================================


async def embed_texts(settings: Settings, texts: list[str]) -> list[list[float] | None]:
    """Erzeuge Embeddings via OpenAI. Fehlerhafte Items kommen als None zurück."""
    if not texts:
        return []
    if not settings.openai_api_key:
        logger.warning("embed_texts called without OPENAI_API_KEY; returning None vectors")
        return [None] * len(texts)

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    results: list[list[float] | None] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(texts), EMBEDDING_BATCH):
            batch = texts[i : i + EMBEDDING_BATCH]
            try:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json={"model": EMBEDDING_MODEL, "input": batch},
                )
                if response.status_code >= 400:
                    logger.warning("OpenAI embeddings failed (%s): %s", response.status_code, response.text[:200])
                    results.extend([None] * len(batch))
                    continue
                data = response.json()
                vectors = [item["embedding"] for item in data.get("data", [])]
                if len(vectors) != len(batch):
                    results.extend([None] * len(batch))
                else:
                    results.extend(vectors)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning("embedding transient failure: %s", exc)
                results.extend([None] * len(batch))
    return results


def _node_text_for_embedding(node: KnowledgeNode) -> str:
    parts = [node.title]
    if node.content:
        parts.append(node.content)
    if node.tags:
        parts.append(" ".join(node.tags))
    return "\n".join(parts)[:4000]


async def attach_embeddings(settings: Settings, nodes: list[KnowledgeNode]) -> None:
    if not nodes:
        return
    texts = [_node_text_for_embedding(node) for node in nodes]
    vectors = await embed_texts(settings, texts)
    for node, vector in zip(nodes, vectors, strict=False):
        if vector is not None:
            node.metadata.setdefault("_embedding", vector)


# === Dedupe ===============================================================


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_duplicate(
    candidate: KnowledgeNode,
    existing_nodes: list[dict[str, Any]],
    candidate_embedding: list[float] | None,
) -> dict[str, Any] | None:
    """Finde existierenden Knoten, der ein Duplikat des Kandidaten ist.

    Kaskade: exakter Title+Type → Embedding-Cosine → trigram (Lite via
    set-overlap auf Tokens als günstiger Fallback ohne DB-Roundtrip).
    """
    candidate_title_lower = candidate.title.strip().lower()
    candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate_title_lower))

    for existing in existing_nodes:
        if existing.get("node_type") != candidate.node_type:
            continue
        # 1) Exakter Title-Match
        existing_title_lower = str(existing.get("title", "")).strip().lower()
        if existing_title_lower and existing_title_lower == candidate_title_lower:
            return existing
        # 2) Embedding-Cosine
        if candidate_embedding and existing.get("embedding"):
            try:
                existing_vec = existing["embedding"]
                if isinstance(existing_vec, str):
                    existing_vec = json.loads(existing_vec)
                if isinstance(existing_vec, list):
                    score = _cosine(candidate_embedding, existing_vec)
                    if score >= DEDUPE_EMBEDDING_THRESHOLD:
                        return existing
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        # 3) Token-Overlap (ohne pg_trgm-Roundtrip)
        existing_tokens = set(re.findall(r"[a-z0-9]+", existing_title_lower))
        if candidate_tokens and existing_tokens:
            jaccard = len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)
            if jaccard >= DEDUPE_TRIGRAM_THRESHOLD:
                return existing

    return None


# === Chat / RAG ===========================================================


async def build_chat_answer(
    settings: Settings,
    query: str,
    citations: list[KnowledgeChatCitation],
    contexts: list[dict[str, Any]],
    *,
    use_mock: bool = False,
) -> str:
    """LLM-Antwort mit strikter Citation-Pflicht."""
    if not citations:
        return (
            "Im aktuellen Knowledge Graph gibt es keine ausreichenden Belege, um diese "
            "Frage zu beantworten. Bitte akzeptiere zuerst Drafts oder ergänze Wissen, "
            "bevor du weiter chattest."
        )

    if use_mock or not settings.openai_api_key:
        bullets = "\n".join(
            f"- [{c.node_id}] {c.title}" for c in citations[:4]
        )
        return (
            f"Basierend auf dem Knowledge Graph (Mock-Modus):\n\n{bullets}\n\n"
            f"Relevant für deine Frage „{query}\"."
        )

    context_blob = "\n\n".join(
        f"[{ctx['id']}] {ctx['title']}\n{ctx.get('content') or ''}"
        for ctx in contexts
    )[:8000]

    system = (
        "You are the AI Scientist's Knowledge Graph assistant. Answer in German. "
        "Use ONLY the provided knowledge nodes. Cite each claim with [node_id] in "
        "square brackets. If the context is insufficient, say so explicitly. "
        "Keep answers under 220 words."
    )
    user = f"Frage: {query}\n\nKontext:\n{context_blob}"

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code >= 400:
                logger.warning("chat completion failed: %s", response.text[:200])
                return _fallback_chat_answer(query, citations)
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("chat transient failure: %s", exc)
        return _fallback_chat_answer(query, citations)


def _fallback_chat_answer(query: str, citations: list[KnowledgeChatCitation]) -> str:
    bullets = "\n".join(f"- [{c.node_id}] {c.title}" for c in citations[:4])
    return (
        f"LLM nicht erreichbar. Diese Knoten sind aktuell am relevantesten für „{query}\":\n\n"
        f"{bullets}"
    )


def propose_chat_insight(
    query: str,
    answer: str,
    citations: list[KnowledgeChatCitation],
    experiment_type: str | None,
) -> tuple[KnowledgeNode, list[KnowledgeEdge]]:
    """Erzeuge einen Vorschlag für einen `chat_insight`-Knoten plus Edges zu seinen Citations.

    Edges nutzen `relationship_type='derived_from'` und werden beim Confirm 1:1
    persistiert; sie binden den Insight an die Quellen, die das Modell konsultiert hat.
    """
    title = query.strip().rstrip("?").rstrip(".")
    if len(title) > 90:
        title = title[:87] + "…"
    node = KnowledgeNode(
        id=_hash_id(title.lower(), prefix="kn-insight"),
        title=title,
        node_type="chat_insight",
        experiment_type=experiment_type,
        content=answer,
        tags=["chat_insight", "ai"],
        metadata={
            "query": query,
            "citations": [c.model_dump() for c in citations],
        },
        status="pending",
        source_type="chat_insight",
        confidence=min(0.9, 0.5 + 0.1 * len(citations)),
        created_by="chat-user",
        source_ref=None,
    )
    edges: list[KnowledgeEdge] = []
    seen_targets: set[str] = set()
    for citation in citations:
        target = citation.node_id
        if not target or target == node.id or target in seen_targets:
            continue
        seen_targets.add(target)
        edges.append(
            KnowledgeEdge(
                source_id=node.id,
                target_id=target,
                relationship_type="derived_from",
                weight=float(citation.score or 0.0),
                source_type="chat_insight",
                metadata={"score": citation.score},
            )
        )
    return node, edges
