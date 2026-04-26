from __future__ import annotations

import asyncio
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


class AgentBus:
    """Erlaubt Agenten, sich gegenseitig Fragen zu stellen.

    Wenn der Ziel-Agent noch nicht abgeschlossen ist (oder nicht innerhalb des
    Timeouts antwortet), wird die Anfrage als ``failed`` markiert und der fragende
    Agent erhaelt ``None`` zurueck. Der Aufrufer entscheidet dann selbst, wie er
    mit dem fehlenden Input umgeht ("okay egal" und weitermachen).
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent_id_by_key: dict[str, str],
    ) -> None:
        self._mb = message_bus
        self._ids = agent_id_by_key
        self._completed: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def mark_completed(self, agent_key: str, output: Any) -> None:
        self._completed[agent_key] = output

    def is_completed(self, agent_key: str) -> bool:
        return agent_key in self._completed

    async def ask(
        self,
        run_id: str,
        from_key: str,
        to_key: str,
        question: str,
        *,
        timeout_seconds: float = 6.0,
        wait_seconds: float = 0.35,
    ) -> Any | None:
        from_id = self._ids.get(from_key)
        to_id = self._ids.get(to_key)

        await self._mb.publish_message(
            run_id,
            message_type="request",
            from_agent_id=from_id,
            to_agent_id=to_id,
            from_agent=from_key,
            to_agent=to_key,
            subject=f"{from_key}->{to_key}",
            message=question,
            payload={"question": question},
        )
        await self._mb.publish_event(
            run_id,
            agent=from_key,
            phase="progress",
            status="started",
            from_agent=from_key,
            to_agent=to_key,
            message=f"{from_key} asks {to_key}: {question}",
            agent_id=from_id,
        )

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            if self.is_completed(to_key):
                break
            await asyncio.sleep(0.15)
        await asyncio.sleep(wait_seconds)

        if self.is_completed(to_key):
            answer_payload = self._completed.get(to_key)
            answer_text = (
                f"{to_key} replies based on its results."
            )
            await self._mb.publish_message(
                run_id,
                message_type="response",
                from_agent_id=to_id,
                to_agent_id=from_id,
                from_agent=to_key,
                to_agent=from_key,
                subject=f"answer::{from_key}",
                message=answer_text,
                payload={"answer": answer_text},
            )
            await self._mb.publish_event(
                run_id,
                agent=from_key,
                phase="progress",
                status="completed",
                from_agent=from_key,
                to_agent=to_key,
                message=f"{to_key} has replied.",
                agent_id=from_id,
            )
            return answer_payload

        timeout_text = (
            f"{to_key} did not reply in time "
            f"({timeout_seconds:.1f}s) - {from_key} continues without input."
        )
        # Wichtig: Wir markieren den fragenden Agent NICHT als failed.
        # Eine unbeantwortete Anfrage ist kein Fehler des Fragenden, sonst
        # zeigt das UI faelschlicherweise eine rote Card. Schema erlaubt nur
        # 'started' | 'completed' | 'failed' -- wir bleiben deshalb auf
        # phase=progress + status=started, um den Agent weiter als laufend zu
        # signalisieren.
        await self._mb.publish_event(
            run_id,
            agent=from_key,
            phase="progress",
            status="started",
            from_agent=from_key,
            to_agent=to_key,
            message=timeout_text,
            agent_id=from_id,
        )
        await self._mb.publish_message(
            run_id,
            message_type="system",
            from_agent_id=from_id,
            to_agent_id=to_id,
            from_agent=from_key,
            to_agent=to_key,
            subject="timeout",
            message=timeout_text,
            payload={"reason": "timeout", "timeout_seconds": timeout_seconds},
        )
        return None
