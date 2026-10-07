"""Resolve adapter implementations + fallback from config."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from token_factory.adapters.agent_gateway import (
    DisabledAgentGatewayAdapter,
    MockAgentGatewayAdapter,
)
from token_factory.adapters.gateway import EnvoyAIGatewayAdapter, MockGatewayAdapter
from token_factory.adapters.mcp import MockMCPServerAdapter
from token_factory.adapters.model_endpoint import OpenAIModelEndpointAdapter
from token_factory.adapters.model_router import MockModelRouterAdapter, VLLMSRModelRouterAdapter
from token_factory.adapters.subagent import MockSubAgentAdapter
from token_factory.adapters.telemetry import PrometheusTelemetryAdapter


@dataclass
class AdapterBundle:
    gateway: Any
    agent_gateway: Any
    model_router: Any
    model_endpoint: Any
    mcp: Any
    subagent: Any
    telemetry: Any
    config: dict[str, Any]


def _pick(section: dict[str, Any] | None, default_impl: str) -> tuple[str, str | None]:
    sec = section or {}
    impl = str(sec.get("implementation") or default_impl)
    fallback = sec.get("fallback")
    return impl, str(fallback) if fallback else None


def resolve_adapters(
    adapters_cfg: dict[str, Any] | None = None,
    *,
    force_mock: bool = False,
) -> AdapterBundle:
    cfg = adapters_cfg or {}
    if force_mock or os.environ.get("TF_ADAPTERS_MOCK", "").lower() in ("1", "true", "yes"):
        return AdapterBundle(
            gateway=MockGatewayAdapter(),
            agent_gateway=MockAgentGatewayAdapter(),
            model_router=MockModelRouterAdapter(),
            model_endpoint=OpenAIModelEndpointAdapter(),
            mcp=MockMCPServerAdapter(),
            subagent=MockSubAgentAdapter(),
            telemetry=PrometheusTelemetryAdapter(),
            config={"forced_mock": True},
        )

    g_impl, g_fb = _pick(cfg.get("gateway"), "envoy_ai_gateway")
    ag_impl, ag_fb = _pick(cfg.get("agent_gateway"), "mock")
    mr_impl, mr_fb = _pick(cfg.get("model_router"), "vllm_semantic_router")

    gateway: Any
    try:
        gateway = EnvoyAIGatewayAdapter() if g_impl == "envoy_ai_gateway" else MockGatewayAdapter()
        if g_impl == "envoy_ai_gateway" and not gateway.health() and g_fb == "mock":
            gateway = MockGatewayAdapter()
    except Exception:
        gateway = MockGatewayAdapter() if g_fb == "mock" else EnvoyAIGatewayAdapter()

    if ag_impl == "disabled":
        agent_gateway: Any = DisabledAgentGatewayAdapter()
    elif ag_impl in ("mock", "demo", "agentgateway"):
        # agentgateway live integration is P1 — Friday uses mock behind same interface
        agent_gateway = MockAgentGatewayAdapter()
    else:
        agent_gateway = MockAgentGatewayAdapter() if ag_fb == "mock" else DisabledAgentGatewayAdapter()

    model_router: Any
    if mr_impl == "vllm_semantic_router":
        try:
            import httpx

            from token_factory.demo.adapters import LiveClassifyAdapter

            probe = LiveClassifyAdapter()
            r = httpx.get(f"{probe.base_url.rstrip('/')}/health", timeout=1.5)
            if r.status_code >= 400:
                raise RuntimeError("sr unhealthy")
            model_router = VLLMSRModelRouterAdapter()
        except Exception:
            model_router = (
                MockModelRouterAdapter() if (mr_fb or "mock") == "mock" else MockModelRouterAdapter()
            )
    else:
        model_router = MockModelRouterAdapter()

    return AdapterBundle(
        gateway=gateway,
        agent_gateway=agent_gateway,
        model_router=model_router,
        model_endpoint=OpenAIModelEndpointAdapter(),
        mcp=MockMCPServerAdapter(),
        subagent=MockSubAgentAdapter(),
        telemetry=PrometheusTelemetryAdapter(),
        config=cfg,
    )
