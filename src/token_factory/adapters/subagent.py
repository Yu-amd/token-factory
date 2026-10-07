"""A2A sub-agent peer adapters — peer of Agent Gateway, never under vLLM-SR."""

from __future__ import annotations

import time

from token_factory.adapters.types import PeerResult, RequestContext


class MockSubAgentAdapter:
    implementation = "demo_a2a"
    mode = "mock"

    def invoke(self, ctx: RequestContext) -> PeerResult:
        t0 = time.perf_counter()
        task = ctx.agent_task or ctx.prompt or "delegate"
        content = (
            f"[a2a:subagent] completed task '{task[:120]}' "
            f"(parent_request_id={ctx.request_id}). Peer path — not via vLLM-SR."
        )
        return PeerResult(
            ok=True,
            peer="demo-subagent",
            request_type="a2a",
            content=content,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            mock=True,
            extras={"agent_task": task, "trace_id": ctx.request_id},
        )
