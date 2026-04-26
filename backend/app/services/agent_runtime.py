from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentResult:
    agent: str
    payload: dict[str, Any]


async def run_with_timeout(coro: Any, timeout_seconds: int) -> AgentResult:
    return await asyncio.wait_for(coro, timeout=timeout_seconds)
