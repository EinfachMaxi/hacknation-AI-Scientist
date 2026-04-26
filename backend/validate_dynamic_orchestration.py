from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request


DEFAULT_PROMPTS = [
    "A paper-based CRP biosensor with anti-CRP antibodies can reach <0.5 mg/L detection in whole blood.",
    "Trehalose-based cryopreservation improves post-thaw HeLa viability compared to standard DMSO protocol.",
    "Lactobacillus rhamnosus GG supplementation lowers intestinal permeability in C57BL/6 mice within 4 weeks.",
]


@dataclass
class RunCheckResult:
    run_id: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append((name, ok, detail))


class AsyncJsonClient:
    def __init__(self, base_url: str, timeout_seconds: int = 30):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def get(self, path: str) -> Any:
        return await asyncio.to_thread(self._sync_request, "GET", path, None)

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        return await asyncio.to_thread(self._sync_request, "POST", path, payload)

    def _sync_request(self, method: str, path: str, payload: dict[str, Any] | None) -> Any:
        url = f"{self._base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read().decode("utf-8")
                if status >= 400:
                    raise RuntimeError(f"{method} {url} failed ({status}): {raw[:300]}")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            raise RuntimeError(f"{method} {url} failed ({exc.code}): {detail[:300]}") from exc


async def start_run(client: AsyncJsonClient, prompt: str) -> str:
    payload = await client.post("/runs", {"prompt": prompt, "use_mock": False})
    return str(payload["run_id"])


async def wait_until_terminal(
    client: AsyncJsonClient,
    run_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        run = await client.get(f"/runs/{run_id}")
        status = run.get("status")
        if status in {"completed", "failed"}:
            return run
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"Run {run_id} wurde nicht rechtzeitig abgeschlossen.")
        await asyncio.sleep(poll_interval_seconds)


def _extract_tool_name(message: dict[str, Any]) -> str | None:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    trace = payload.get("tool_trace")
    if not isinstance(trace, dict):
        return None
    tool = trace.get("tool")
    return str(tool) if tool else None


async def validate_single_run(client: AsyncJsonClient, run_id: str, run_status: str) -> RunCheckResult:
    result = RunCheckResult(run_id=run_id)

    events, messages, graph = await asyncio.gather(
        client.get(f"/runs/{run_id}/events"),
        client.get(f"/runs/{run_id}/messages"),
        client.get(f"/runs/{run_id}/graph"),
    )

    result.add("run_not_failed", run_status != "failed", f"status={run_status}")
    result.add("graph_nodes_present", len(graph.get("nodes", [])) > 0, f"nodes={len(graph.get('nodes', []))}")
    result.add("graph_edges_present", len(graph.get("edges", [])) > 0, f"edges={len(graph.get('edges', []))}")
    result.add("events_present", len(events) > 0, f"events={len(events)}")
    result.add("messages_present", len(messages) > 0, f"messages={len(messages)}")

    handoffs = [m for m in messages if m.get("message_type") == "handoff"]
    result.add("handoff_count>=2", len(handoffs) >= 2, f"handoffs={len(handoffs)}")

    # Reconnect-/Idempotenz-Simulation: zweimal ziehen, gleiche Sequenzanzahl, keine Duplikate.
    replay_events = await client.get(f"/runs/{run_id}/events")
    seqs = [int(e.get("sequence", -1)) for e in replay_events]
    no_dups = len(seqs) == len(set(seqs))
    monotonic = seqs == sorted(seqs)
    result.add("reconnect_no_duplicate_events", no_dups, f"sequence_count={len(seqs)} unique={len(set(seqs))}")
    result.add("reconnect_monotonic_sequence", monotonic, "event sequence is sorted ascending")

    node_ids = {str(node.get("id")) for node in graph.get("nodes", [])}
    edge_refs_valid = all(
        str(edge.get("from")) in node_ids and str(edge.get("to")) in node_ids
        for edge in graph.get("edges", [])
    )
    result.add("graph_edges_reference_valid_nodes", edge_refs_valid, "all edges reference existing nodes")

    # Tool-Gating: Wenn allowed_tools gesetzt ist, dann nur diese Tools im Message-Trace.
    allowed_by_node: dict[str, set[str]] = {}
    for node in graph.get("nodes", []):
        tooling = node.get("tooling") or {}
        allowed_tools = tooling.get("allowed_tools") or []
        allowed_by_node[str(node.get("id"))] = {str(t) for t in allowed_tools}

    gating_violations: list[str] = []
    for msg in messages:
        from_agent = str(msg.get("from_agent") or "")
        tool_name = _extract_tool_name(msg)
        if not from_agent or not tool_name:
            continue
        allowed = allowed_by_node.get(from_agent, set())
        if allowed and tool_name not in allowed:
            gating_violations.append(f"{from_agent}:{tool_name}")

    result.add(
        "tool_capability_gating",
        len(gating_violations) == 0,
        "violations=" + (", ".join(gating_violations) if gating_violations else "none"),
    )

    return result


async def run_validation(base_url: str, runs: int, timeout_seconds: int, poll_interval_seconds: float) -> int:
    prompts = [DEFAULT_PROMPTS[i % len(DEFAULT_PROMPTS)] for i in range(runs)]
    print(f"Starte {runs} parallele Runs gegen {base_url} ...")

    client = AsyncJsonClient(base_url=base_url, timeout_seconds=30)
    run_ids = await asyncio.gather(*(start_run(client, p) for p in prompts))
    print("Run IDs:", ", ".join(run_ids))

    terminals = await asyncio.gather(
        *(wait_until_terminal(client, run_id, timeout_seconds, poll_interval_seconds) for run_id in run_ids)
    )

    run_status_by_id = {str(run["run_id"]): str(run.get("status")) for run in terminals}
    checks = await asyncio.gather(
        *(validate_single_run(client, run_id, run_status_by_id.get(run_id, "unknown")) for run_id in run_ids)
    )

    failures = 0
    print("\n=== Phase-5 Validierung ===")
    for check in checks:
        print(f"\nRun {check.run_id}")
        for name, ok, detail in check.checks:
            marker = "PASS" if ok else "FAIL"
            print(f"  [{marker}] {name}: {detail}")
            if not ok:
                failures += 1

    print("\n=== Ergebnis ===")
    if failures == 0:
        print("Alle Checks erfolgreich.")
        return 0
    print(f"{failures} Checks fehlgeschlagen.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-5 Validierung für dynamische Orchestrierung")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend Basis-URL")
    parser.add_argument("--runs", type=int, default=3, help="Anzahl paralleler Runs")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Maximale Wartezeit pro Run")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.5, help="Polling Intervall")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(
        run_validation(
            base_url=args.base_url,
            runs=args.runs,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
