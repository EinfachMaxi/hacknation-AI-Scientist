from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.schemas.plan import AgentEvent
from backend.app.services.integrations import SupabaseRepository


class MessageBus:
    def __init__(self, repository: SupabaseRepository) -> None:
        self._repository = repository

    async def publish_event(
        self,
        run_id: str,
        *,
        agent: str,
        phase: str,
        status: str,
        payload: dict[str, Any] | None = None,
        message: str | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        event = AgentEvent(
            run_id=run_id,
            sequence=0,
            agent=agent,
            phase=phase,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            payload=payload or {},
            message=message,
            from_agent=from_agent,
            to_agent=to_agent,
        )
        row = event.model_dump(mode="json")
        if agent_id:
            row["agent_id"] = agent_id
        return await self._repository.append_agent_event(row)

    async def publish_message(
        self,
        run_id: str,
        *,
        message_type: str,
        payload: dict[str, Any] | None = None,
        from_agent_id: str | None = None,
        to_agent_id: str | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "run_id": run_id,
            "sequence": 0,
            "message_type": message_type,
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "subject": subject,
            "message": message,
            "payload": payload or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        return await self._repository.append_agent_message(row)
