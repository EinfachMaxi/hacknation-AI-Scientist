from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from backend.app.services.integrations import TavilyClient

DEFAULT_ALLOWLIST = (
    "pubmed",
    "nature",
    "science",
    "arxiv",
    "protocols.io",
    "semanticscholar",
    "sigmaaldrich",
    "thermofisher",
    "neb.com",
    "bio-rad",
    "abcam",
    "retractionwatch",
    "bio-protocol",
)


@dataclass
class ToolTrace:
    tool: str
    status: str
    call_index: int
    payload: dict[str, Any]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status,
            "call_index": self.call_index,
            "payload": self.payload,
            "error": self.error,
        }


class TavilyToolGateway:
    def __init__(
        self,
        tavily: TavilyClient,
        *,
        domain_allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST,
        timeout_seconds: int = 20,
        max_retries: int = 1,
    ) -> None:
        self._tavily = tavily
        self._domain_allowlist = domain_allowlist
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    def is_allowed_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        return any(token in host for token in self._domain_allowlist)

    @staticmethod
    def classify_error(error: Exception) -> str:
        text = str(error).lower()
        if "401" in text or "unauthorized" in text:
            return "tool_auth_error"
        if "429" in text or "rate" in text:
            return "tool_rate_limited"
        if "timeout" in text:
            return "tool_timeout"
        if "allowlist" in text:
            return "tool_validation_error"
        return "tool_unknown_error"

    async def _call_with_retry(self, coro_factory: Any) -> Any:
        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(coro_factory(), timeout=self._timeout_seconds)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == attempts:
                    break
                await asyncio.sleep(0.35 * attempt)
        if last_error:
            raise last_error
        raise RuntimeError("Tool-Call failed without captured error")

    async def search(self, query: str, *, max_results: int = 3) -> tuple[list[dict[str, Any]], ToolTrace]:
        results = await self._call_with_retry(lambda: self._tavily.search(query))
        trimmed = results[:max_results]
        trace = ToolTrace(
            tool="tavily.search",
            status="completed",
            call_index=1,
            payload={"query": query, "result_count": len(trimmed), "max_results": max_results},
        )
        return trimmed, trace

    async def extract(self, urls: list[str], *, call_index: int = 2) -> tuple[list[dict[str, Any]], ToolTrace]:
        filtered_urls = [url for url in urls if self.is_allowed_url(url)]
        if not filtered_urls:
            trace = ToolTrace(
                tool="tavily.extract",
                status="skipped",
                call_index=call_index,
                payload={"reason": "no_urls_passed_allowlist", "input_count": len(urls)},
            )
            return [], trace
        results = await self._call_with_retry(lambda: self._tavily.extract(filtered_urls))
        trace = ToolTrace(
            tool="tavily.extract",
            status="completed",
            call_index=call_index,
            payload={"urls": filtered_urls, "result_count": len(results)},
        )
        return results, trace

    async def search_domains(
        self,
        query: str,
        *,
        include_domains: list[str] | None = None,
        max_results: int = 3,
        call_index: int = 1,
    ) -> tuple[list[dict[str, Any]], ToolTrace]:
        results = await self._call_with_retry(
            lambda: self._tavily.search_domains(
                query,
                include_domains=include_domains,
                max_results=max_results,
            )
        )
        trimmed = results[:max_results]
        trace = ToolTrace(
            tool="tavily.search",
            status="completed",
            call_index=call_index,
            payload={
                "query": query,
                "include_domains": include_domains or [],
                "result_count": len(trimmed),
                "max_results": max_results,
            },
        )
        return trimmed, trace

    async def crawl(
        self,
        url: str,
        *,
        instructions: str | None = None,
        max_depth: int = 1,
        max_breadth: int = 10,
        chunks_per_source: int | None = None,
        call_index: int = 1,
    ) -> tuple[list[dict[str, Any]], ToolTrace]:
        if not self.is_allowed_url(url):
            trace = ToolTrace(
                tool="tavily.crawl",
                status="skipped",
                call_index=call_index,
                payload={"reason": "domain_not_in_allowlist", "url": url},
            )
            return [], trace
        results = await self._call_with_retry(
            lambda: self._tavily.crawl(
                url,
                instructions=instructions,
                max_depth=max_depth,
                max_breadth=max_breadth,
                chunks_per_source=chunks_per_source,
            )
        )
        trace = ToolTrace(
            tool="tavily.crawl",
            status="completed",
            call_index=call_index,
            payload={
                "url": url,
                "instructions": instructions,
                "result_count": len(results),
                "max_depth": max_depth,
            },
        )
        return results, trace

    async def map(
        self,
        url: str,
        *,
        instructions: str | None = None,
        max_depth: int = 2,
        max_breadth: int = 50,
        limit: int = 50,
        select_paths: list[str] | None = None,
        call_index: int = 1,
    ) -> tuple[list[str], ToolTrace]:
        if not self.is_allowed_url(url):
            trace = ToolTrace(
                tool="tavily.map",
                status="skipped",
                call_index=call_index,
                payload={"reason": "domain_not_in_allowlist", "url": url},
            )
            return [], trace
        urls = await self._call_with_retry(
            lambda: self._tavily.map(
                url,
                instructions=instructions,
                max_depth=max_depth,
                max_breadth=max_breadth,
                limit=limit,
                select_paths=select_paths,
            )
        )
        trace = ToolTrace(
            tool="tavily.map",
            status="completed",
            call_index=call_index,
            payload={"url": url, "instructions": instructions, "url_count": len(urls)},
        )
        return urls, trace

    async def research(
        self,
        input_text: str,
        *,
        model: str = "mini",
        citation_format: str = "numbered",
        call_index: int = 1,
    ) -> tuple[dict[str, Any], ToolTrace]:
        data = await self._call_with_retry(
            lambda: self._tavily.research(
                input_text,
                model=model,
                citation_format=citation_format,
            )
        )
        trace = ToolTrace(
            tool="tavily.research",
            status="completed",
            call_index=call_index,
            payload={
                "input": input_text[:200],
                "model": model,
                "has_report": bool(data.get("report") or data.get("answer")),
                "source_count": len(data.get("sources") or data.get("citations") or []),
            },
        )
        return data, trace
