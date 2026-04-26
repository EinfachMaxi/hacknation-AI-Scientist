from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from supabase import Client, create_client

from backend.app.config import Settings


class TavilyClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = "https://api.tavily.com"

    async def search(self, query: str) -> list[dict[str, Any]]:
        if not self._settings.tavily_api_key:
            return []
        payload = {
            "api_key": self._settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 3,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._base_url}/search", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"Tavily /search failed ({response.status_code}): {response.text[:300]}")
            data = response.json()
        return data.get("results", [])

    async def extract(self, urls: list[str]) -> list[dict[str, Any]]:
        if not self._settings.tavily_api_key or not urls:
            return []
        payload = {
            "api_key": self._settings.tavily_api_key,
            "urls": urls,
            "include_images": False,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._base_url}/extract", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"Tavily /extract failed ({response.status_code}): {response.text[:300]}")
            data = response.json()
        results = data.get("results", [])
        return results if isinstance(results, list) else []

    async def search_domains(
        self,
        query: str,
        *,
        include_domains: list[str] | None = None,
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        """Wie `search`, aber mit Domain-Filter (Tavily-seitig)."""
        if not self._settings.tavily_api_key:
            return []
        payload: dict[str, Any] = {
            "api_key": self._settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self._base_url}/search", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Tavily /search failed ({response.status_code}): {response.text[:300]}"
                )
            data = response.json()
        return data.get("results", [])

    async def crawl(
        self,
        url: str,
        *,
        instructions: str | None = None,
        max_depth: int = 1,
        max_breadth: int = 10,
        chunks_per_source: int | None = None,
    ) -> list[dict[str, Any]]:
        """Deep-Crawl einer Site; optional mit NL-`instructions` zur semantischen Fokussierung."""
        if not self._settings.tavily_api_key or not url:
            return []
        payload: dict[str, Any] = {
            "api_key": self._settings.tavily_api_key,
            "url": url,
            "max_depth": max_depth,
            "max_breadth": max_breadth,
        }
        if instructions:
            payload["instructions"] = instructions
            if chunks_per_source is not None:
                payload["chunks_per_source"] = chunks_per_source
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self._base_url}/crawl", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Tavily /crawl failed ({response.status_code}): {response.text[:300]}"
                )
            data = response.json()
        results = data.get("results", [])
        return results if isinstance(results, list) else []

    async def map(
        self,
        url: str,
        *,
        instructions: str | None = None,
        max_depth: int = 2,
        max_breadth: int = 50,
        limit: int = 50,
        select_paths: list[str] | None = None,
    ) -> list[str]:
        """Sitemap-Discovery – liefert nur URLs, keinen Content."""
        if not self._settings.tavily_api_key or not url:
            return []
        payload: dict[str, Any] = {
            "api_key": self._settings.tavily_api_key,
            "url": url,
            "max_depth": max_depth,
            "max_breadth": max_breadth,
            "limit": limit,
        }
        if instructions:
            payload["instructions"] = instructions
        if select_paths:
            payload["select_paths"] = select_paths
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(f"{self._base_url}/map", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Tavily /map failed ({response.status_code}): {response.text[:300]}"
                )
            data = response.json()
        urls = data.get("results") or data.get("urls") or []
        return [str(entry) for entry in urls if entry]

    async def research(
        self,
        input_text: str,
        *,
        model: str = "mini",
        citation_format: str = "numbered",
    ) -> dict[str, Any]:
        """End-to-End Agentic Research: liefert Report + Quellen."""
        if not self._settings.tavily_api_key or not input_text:
            return {}
        payload = {
            "api_key": self._settings.tavily_api_key,
            "input": input_text,
            "model": model,
            "citation_format": citation_format,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{self._base_url}/research", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Tavily /research failed ({response.status_code}): {response.text[:300]}"
                )
            data = response.json()
        return data if isinstance(data, dict) else {}


class SupabaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._plans: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._event_sequence: dict[str, int] = {}
        self._message_sequence: dict[str, int] = {}
        self._knowledge_nodes: dict[str, dict[str, Any]] = {}
        self._knowledge_edges: list[dict[str, Any]] = []
        self._agents: dict[str, dict[str, Any]] = {}
        self._run_agents: dict[str, dict[str, dict[str, Any]]] = {}
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._supabase: Client | None = None
        if settings.supabase_url and settings.supabase_service_key:
            self._supabase = create_client(settings.supabase_url, settings.supabase_service_key)

    def _next_local_sequence(self, run_id: str) -> int:
        seq = self._event_sequence.get(run_id, 0) + 1
        self._event_sequence[run_id] = seq
        return seq

    def _next_sequence_from_supabase(self, run_id: str) -> int:
        if not self._supabase:
            return self._next_local_sequence(run_id)
        result = (
            self._supabase.table("agent_events")
            .select("sequence")
            .eq("run_id", run_id)
            .order("sequence", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        current = rows[0]["sequence"] if rows else 0
        next_sequence = current + 1
        self._event_sequence[run_id] = max(self._event_sequence.get(run_id, 0), next_sequence)
        return next_sequence

    def _next_message_sequence_from_supabase(self, run_id: str) -> int:
        if not self._supabase:
            seq = self._message_sequence.get(run_id, 0) + 1
            self._message_sequence[run_id] = seq
            return seq
        result = (
            self._supabase.table("agent_messages")
            .select("sequence")
            .eq("run_id", run_id)
            .order("sequence", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        current = rows[0]["sequence"] if rows else 0
        next_sequence = current + 1
        self._message_sequence[run_id] = max(self._message_sequence.get(run_id, 0), next_sequence)
        return next_sequence

    async def create_run(self, run: dict[str, Any]) -> None:
        self._runs[run["run_id"]] = run
        if self._supabase:
            self._supabase.table("experiment_runs").insert(run).execute()

    async def update_run(self, run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        row = self._runs.get(run_id)
        if not row:
            return None
        row.update(patch)
        row["updated_at"] = datetime.utcnow().isoformat()
        if self._supabase:
            self._supabase.table("experiment_runs").update(row).eq("run_id", run_id).execute()
        return row

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        if run_id in self._runs:
            return self._runs[run_id]
        if self._supabase:
            result = self._supabase.table("experiment_runs").select("*").eq("run_id", run_id).limit(1).execute()
            data = result.data or []
            return data[0] if data else None
        return None

    async def list_agents(self) -> list[dict[str, Any]]:
        if self._supabase:
            result = (
                self._supabase.table("agents")
                .select("*")
                .eq("is_active", True)
                .order("sort_order", desc=False)
                .execute()
            )
            rows = result.data or []
            for row in rows:
                self._agents[row["key"]] = row
            return rows
        return sorted(self._agents.values(), key=lambda row: int(row.get("sort_order", 100)))

    async def upsert_agents(self, agents: list[dict[str, Any]]) -> None:
        for row in agents:
            self._agents[row["key"]] = row
        if self._supabase and agents:
            self._supabase.table("agents").upsert(agents, on_conflict="key").execute()

    async def create_run_agents(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        run_id = rows[0]["run_id"]
        bucket = self._run_agents.setdefault(run_id, {})
        for row in rows:
            bucket[row["agent_id"]] = row
        if self._supabase:
            self._supabase.table("run_agents").upsert(rows, on_conflict="run_id,agent_id").execute()

    async def list_run_agents(self, run_id: str) -> list[dict[str, Any]]:
        local_rows = list(self._run_agents.get(run_id, {}).values())
        if self._supabase:
            result = self._supabase.table("run_agents").select("*").eq("run_id", run_id).execute()
            rows = result.data or []
            if rows:
                for row in rows:
                    self._run_agents.setdefault(run_id, {})[row["agent_id"]] = row
                local_rows = rows
        return local_rows

    async def update_run_agent(
        self,
        run_id: str,
        agent_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any] | None:
        bucket = self._run_agents.setdefault(run_id, {})
        row = bucket.get(agent_id, {"run_id": run_id, "agent_id": agent_id})
        row.update(patch)
        row["updated_at"] = datetime.utcnow().isoformat()
        bucket[agent_id] = row
        if self._supabase:
            self._supabase.table("run_agents").update(row).eq("run_id", run_id).eq("agent_id", agent_id).execute()
        return row

    async def append_agent_event(self, event: dict[str, Any]) -> dict[str, Any]:
        run_id = event["run_id"]
        attempts = 3 if self._supabase else 1
        last_error: Exception | None = None

        for _ in range(attempts):
            seq = self._next_sequence_from_supabase(run_id) if self._supabase else self._next_local_sequence(run_id)
            row = {**event, "sequence": seq}
            try:
                self._events.setdefault(run_id, []).append(row)
                if self._supabase:
                    self._supabase.table("agent_events").insert(row).execute()
                return row
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self._events.get(run_id):
                    self._events[run_id].pop()
                # Bei race conditions auf UNIQUE(run_id, sequence) noch einmal versuchen.
                if "duplicate key value violates unique constraint" not in str(exc):
                    raise
        if last_error:
            raise last_error
        raise RuntimeError("Konnte Agent-Event nicht persistieren")

    async def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        if run_id in self._events:
            return self._events[run_id]
        if self._supabase:
            result = (
                self._supabase.table("agent_events")
                .select("*")
                .eq("run_id", run_id)
                .order("sequence", desc=False)
                .execute()
            )
            return result.data or []
        return []

    async def append_agent_message(self, message: dict[str, Any]) -> dict[str, Any]:
        run_id = message["run_id"]
        attempts = 3 if self._supabase else 1
        last_error: Exception | None = None
        for _ in range(attempts):
            seq = self._next_message_sequence_from_supabase(run_id)
            row = {**message, "sequence": seq}
            try:
                self._messages.setdefault(run_id, []).append(row)
                if self._supabase:
                    self._supabase.table("agent_messages").insert(row).execute()
                return row
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self._messages.get(run_id):
                    self._messages[run_id].pop()
                if "duplicate key value violates unique constraint" not in str(exc):
                    raise
        if last_error:
            raise last_error
        raise RuntimeError("Konnte Agent-Message nicht persistieren")

    async def list_run_messages(self, run_id: str) -> list[dict[str, Any]]:
        if run_id in self._messages:
            return self._messages[run_id]
        if self._supabase:
            result = (
                self._supabase.table("agent_messages")
                .select("*")
                .eq("run_id", run_id)
                .order("sequence", desc=False)
                .execute()
            )
            return result.data or []
        return []

    async def save_plan(self, plan: dict[str, Any]) -> None:
        self._plans[plan["plan_id"]] = plan
        if self._supabase:
            try:
                self._supabase.table("plans").insert(plan).execute()
            except Exception:
                # Dev-Fallback: In manchen Umgebungen ist die plans-Tabelle noch nicht migriert.
                # Der Run soll dann nicht komplett fehlschlagen, solange der Plan lokal vorliegt.
                return

    async def list_plans(self) -> list[dict[str, Any]]:
        if self._supabase:
            try:
                rows = (
                    self._supabase.table("plans")
                    .select("*")
                    .order("generated_at", desc=True)
                    .limit(200)
                    .execute()
                    .data
                    or []
                )
                for row in rows:
                    self._plans[row["plan_id"]] = row
                if rows:
                    return rows
            except Exception:  # noqa: BLE001
                pass
        rows = list(self._plans.values())
        return sorted(rows, key=lambda item: item["generated_at"], reverse=True)

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        if plan_id in self._plans:
            return self._plans[plan_id]
        if self._supabase:
            try:
                rows = (
                    self._supabase.table("plans")
                    .select("*")
                    .eq("plan_id", plan_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if rows:
                    self._plans[plan_id] = rows[0]
                    return rows[0]
            except Exception:  # noqa: BLE001
                pass
        return None

    async def upsert_knowledge_nodes(self, nodes: list[dict[str, Any]]) -> None:
        now = datetime.utcnow().isoformat()
        for node in nodes:
            node.setdefault("created_at", now)
            self._knowledge_nodes[node["id"]] = node
        if self._supabase and nodes:
            try:
                # Wir entfernen `_embedding`-Helper und alle None-Werte, damit
                # DB-Defaults (z.B. `created_at`) greifen können.
                payload = []
                for node in nodes:
                    row = {
                        k: v
                        for k, v in node.items()
                        if k != "_embedding" and v is not None
                    }
                    payload.append(row)
                self._supabase.table("knowledge_nodes").upsert(
                    payload, on_conflict="id"
                ).execute()
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "upsert_knowledge_nodes failed against Supabase: %s", exc
                )
                raise

    async def add_knowledge_edges(self, edges: list[dict[str, Any]]) -> None:
        self._knowledge_edges.extend(edges)
        if self._supabase and edges:
            try:
                payload = [
                    {k: v for k, v in edge.items() if v is not None}
                    for edge in edges
                ]
                self._supabase.table("knowledge_edges").upsert(
                    payload, on_conflict="source_id,target_id,relationship_type"
                ).execute()
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "add_knowledge_edges failed against Supabase: %s", exc
                )

    async def list_knowledge(
        self, *, status: str | None = "active"
    ) -> dict[str, Any]:
        if self._supabase:
            try:
                node_query = self._supabase.table("knowledge_nodes").select(
                    "id,title,node_type,experiment_type,content,metadata,tags,status,"
                    "source_type,source_ref,confidence,times_applied,created_by,created_at"
                )
                if status and status != "all":
                    node_query = node_query.eq("status", status)
                node_rows = node_query.limit(500).execute().data or []
                edge_rows = (
                    self._supabase.table("knowledge_edges")
                    .select("*")
                    .limit(2000)
                    .execute()
                    .data
                    or []
                )
                return {"nodes": node_rows, "edges": edge_rows}
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "list_knowledge supabase fallback to memory: %s", exc
                )
        nodes = list(self._knowledge_nodes.values())
        if status and status != "all":
            nodes = [n for n in nodes if n.get("status", "active") == status]
        return {"nodes": nodes, "edges": self._knowledge_edges}

    async def list_knowledge_node_ids(
        self, *, node_type: str | None = None, status: str = "active"
    ) -> list[dict[str, Any]]:
        """Schlanke Liste für Dedupe-Lookups: id, title, node_type, embedding."""
        if self._supabase:
            try:
                query = self._supabase.table("knowledge_nodes").select(
                    "id,title,node_type,status,embedding"
                ).eq("status", status)
                if node_type:
                    query = query.eq("node_type", node_type)
                rows = query.limit(1000).execute().data or []
                return rows
            except Exception:  # noqa: BLE001
                pass
        rows = [n for n in self._knowledge_nodes.values() if n.get("status", "active") == status]
        if node_type:
            rows = [n for n in rows if n.get("node_type") == node_type]
        return rows

    async def increment_knowledge_node_usage(self, node_id: str) -> None:
        """Bei Dedupe-Treffer: times_applied hochzählen."""
        existing = self._knowledge_nodes.get(node_id)
        if existing:
            existing["times_applied"] = int(existing.get("times_applied", 1)) + 1
        if self._supabase:
            try:
                row = (
                    self._supabase.table("knowledge_nodes")
                    .select("times_applied")
                    .eq("id", node_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                current = int(row[0].get("times_applied", 1)) if row else 1
                self._supabase.table("knowledge_nodes").update(
                    {"times_applied": current + 1}
                ).eq("id", node_id).execute()
            except Exception:  # noqa: BLE001
                pass

    async def search_knowledge(
        self,
        *,
        query_text: str,
        query_embedding: list[float] | None,
        experiment_type: str | None = None,
        match_count: int = 8,
    ) -> list[dict[str, Any]]:
        """Hybride Suche via RPC `knowledge_search`. Fällt auf Memory zurück."""
        if self._supabase:
            try:
                result = self._supabase.rpc(
                    "knowledge_search",
                    {
                        "query_embedding": query_embedding,
                        "query_text": query_text,
                        "experiment_type_filter": experiment_type,
                        "match_count": match_count,
                    },
                ).execute()
                rows = result.data or []
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "knowledge_search RPC fallback to memory: %s", exc
                )
        # Memory-Fallback: einfache substring-Suche.
        haystack = list(self._knowledge_nodes.values())
        query_lower = (query_text or "").lower()
        scored = []
        for node in haystack:
            if node.get("status") != "active":
                continue
            if experiment_type and node.get("experiment_type") != experiment_type:
                continue
            text = " ".join([
                str(node.get("title") or ""),
                str(node.get("content") or ""),
                " ".join(node.get("tags") or []),
            ]).lower()
            score = 1.0 if query_lower and query_lower in text else 0.0
            if score > 0:
                scored.append({**node, "combined_score": score, "vector_score": 0.0, "trigram_score": score})
        scored.sort(key=lambda r: r.get("combined_score", 0), reverse=True)
        return scored[:match_count]

    async def create_knowledge_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        if self._supabase:
            try:
                inserted = (
                    self._supabase.table("knowledge_proposals")
                    .insert(proposal)
                    .execute()
                    .data
                    or []
                )
                if inserted:
                    return inserted[0]
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "create_knowledge_proposal supabase fallback: %s", exc
                )
        from uuid import uuid4 as _uuid4

        row = {
            **proposal,
            "id": str(_uuid4()),
            "created_at": datetime.utcnow().isoformat(),
            "status": proposal.get("status", "pending"),
        }
        self._knowledge_proposals = getattr(self, "_knowledge_proposals", {})
        self._knowledge_proposals[row["id"]] = row
        return row

    async def get_knowledge_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        if self._supabase:
            try:
                rows = (
                    self._supabase.table("knowledge_proposals")
                    .select("*")
                    .eq("id", proposal_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if rows:
                    return rows[0]
            except Exception:  # noqa: BLE001
                pass
        return getattr(self, "_knowledge_proposals", {}).get(proposal_id)

    async def update_knowledge_proposal_status(
        self, proposal_id: str, status: str
    ) -> dict[str, Any] | None:
        patch = {"status": status, "decided_at": datetime.utcnow().isoformat()}
        if self._supabase:
            try:
                rows = (
                    self._supabase.table("knowledge_proposals")
                    .update(patch)
                    .eq("id", proposal_id)
                    .execute()
                    .data
                    or []
                )
                if rows:
                    return rows[0]
            except Exception:  # noqa: BLE001
                pass
        existing = getattr(self, "_knowledge_proposals", {}).get(proposal_id)
        if existing:
            existing.update(patch)
            return existing
        return None
