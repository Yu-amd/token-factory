"""MCP peer adapters — peer of Agent Gateway, never under vLLM-SR."""

from __future__ import annotations

import time

from token_factory.adapters.types import PeerResult, RequestContext


class MockMCPServerAdapter:
    implementation = "demo_mcp"
    mode = "mock"

    def call_tool(self, ctx: RequestContext) -> PeerResult:
        t0 = time.perf_counter()
        tool = ctx.tool_name or "repo_search"
        content = (
            f"[mcp:{tool}] ok — searched codebase for '{ctx.prompt[:80]}' "
            f"(request_id={ctx.request_id}). Model router not involved."
        )
        return PeerResult(
            ok=True,
            peer="demo-mcp-tools",
            request_type="mcp",
            content=content,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            mock=True,
            extras={"tool_name": tool},
        )
