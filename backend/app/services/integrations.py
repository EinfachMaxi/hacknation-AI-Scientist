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
            response.raise_for_status()
            data = response.json()
        return data.get("results", [])


class SupabaseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._plans: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._event_sequence: dict[str, int] = {}
        self._knowledge_nodes: dict[str, dict[str, Any]] = {}
        self._knowledge_edges: list[dict[str, Any]] = []
        self._supabase: Client | None = None
        if settings.supabase_url and settings.supabase_service_key:
            self._supabase = create_client(settings.supabase_url, settings.supabase_service_key)

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

    async def append_agent_event(self, event: dict[str, Any]) -> dict[str, Any]:
        run_id = event["run_id"]
        seq = self._event_sequence.get(run_id, 0) + 1
        self._event_sequence[run_id] = seq
        row = {**event, "sequence": seq}
        self._events.setdefault(run_id, []).append(row)
        if self._supabase:
            self._supabase.table("agent_events").insert(row).execute()
        return row

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

    async def save_plan(self, plan: dict[str, Any]) -> None:
        self._plans[plan["plan_id"]] = plan
        if self._supabase:
            self._supabase.table("plans").insert(plan).execute()

    async def list_plans(self) -> list[dict[str, Any]]:
        rows = list(self._plans.values())
        return sorted(rows, key=lambda item: item["generated_at"], reverse=True)

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._plans.get(plan_id)

    async def upsert_knowledge_nodes(self, nodes: list[dict[str, Any]]) -> None:
        now = datetime.utcnow().isoformat()
        for node in nodes:
            node.setdefault("created_at", now)
            self._knowledge_nodes[node["id"]] = node

    async def add_knowledge_edges(self, edges: list[dict[str, Any]]) -> None:
        self._knowledge_edges.extend(edges)

    async def list_knowledge(self) -> dict[str, Any]:
        return {
            "nodes": list(self._knowledge_nodes.values()),
            "edges": self._knowledge_edges,
        }
