"""Phase 2 request pipeline: Agent Gateway → peer branch (model | mcp | a2a)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from token_factory.adapters.registry import AdapterBundle, resolve_adapters
from token_factory.adapters.types import (
    GovernanceDecision,
    PeerResult,
    RequestContext,
    RoutingDecision,
)


@dataclass
class Phase2Result:
    ctx: RequestContext
    governance: GovernanceDecision
    routing: RoutingDecision | None = None
    peer: PeerResult | None = None
    model_response: dict[str, Any] | None = None
    phase: str = "phase2"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "request": self.ctx.to_dict(),
            "governance": self.governance.to_dict(),
            "routing": self.routing.to_dict() if self.routing else None,
            "peer": self.peer.to_dict() if self.peer else None,
            "model_response": self.model_response,
            "extras": self.extras,
        }


def run_phase2_request(
    ctx: RequestContext,
    *,
    adapters: AdapterBundle | None = None,
    endpoint_url: str | None = None,
    model: str | None = None,
    compute: str | None = None,
    endpoint_id: str | None = None,
    execute_model: bool = False,
) -> Phase2Result:
    """Authorize at Agent Gateway, then branch to model / MCP / A2A peer.

    Model branch may call vLLM-SR for classification. MCP/A2A never touch the router.
    """
    bundle = adapters or resolve_adapters()
    if not ctx.request_id:
        ctx.request_id = str(uuid.uuid4())

    gov = bundle.agent_gateway.authorize(ctx)
    bundle.telemetry.emit_phase2(
        request_type=ctx.request_type,
        governance_allowed=gov.allowed,
        peer=None,
        implementation=gov.implementation,
    )

    if not gov.allowed:
        return Phase2Result(ctx=ctx, governance=gov, extras={"stopped_at": "agent_gateway"})

    if ctx.request_type == "mcp":
        peer = bundle.mcp.call_tool(ctx)
        bundle.telemetry.emit_phase2(
            request_type="mcp",
            governance_allowed=True,
            peer=peer.peer,
            implementation=gov.implementation,
        )
        return Phase2Result(ctx=ctx, governance=gov, peer=peer)

    if ctx.request_type == "a2a":
        peer = bundle.subagent.invoke(ctx)
        bundle.telemetry.emit_phase2(
            request_type="a2a",
            governance_allowed=True,
            peer=peer.peer,
            implementation=gov.implementation,
        )
        return Phase2Result(ctx=ctx, governance=gov, peer=peer)

    # MODEL branch — vLLM-SR only here
    classify_body = bundle.model_router.classify(ctx.prompt or ctx.intent or "")
    routing = bundle.model_router.to_routing_decision(
        classify_body, objective=ctx.objective
    )
    routing.model = model or routing.model
    routing.compute = compute or routing.compute or "MI300X"
    routing.endpoint_id = endpoint_id or routing.endpoint_id

    model_response = None
    if execute_model and endpoint_url and routing.model:
        model_response = bundle.model_endpoint.complete(
            base_url=endpoint_url,
            model=routing.model,
            prompt=ctx.prompt,
            max_tokens=64,
        )

    bundle.telemetry.emit_phase2(
        request_type="model",
        governance_allowed=True,
        peer=routing.endpoint_id or "model",
        implementation=gov.implementation,
    )
    return Phase2Result(
        ctx=ctx,
        governance=gov,
        routing=routing,
        model_response=model_response,
        extras={"classify": classify_body},
    )
