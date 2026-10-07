"""Adapter protocols — OSS default implementations plug in here."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from token_factory.adapters.types import (
    EndpointHealth,
    GovernanceDecision,
    PeerResult,
    RequestContext,
    RoutingDecision,
)


class GatewayAdapter(Protocol):
    def health(self) -> bool: ...
    def chat_completions(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> dict[str, Any]: ...


class AgentGatewayAdapter(Protocol):
    def authorize(self, ctx: RequestContext) -> GovernanceDecision: ...


class ModelRouterAdapter(Protocol):
    def classify(self, text: str) -> dict[str, Any]: ...
    def to_routing_decision(self, classify_body: dict[str, Any], *, objective: str | None = None) -> RoutingDecision: ...


class ModelEndpointAdapter(Protocol):
    def health(self, *, base_url: str, model: str | None = None) -> EndpointHealth: ...
    def complete(self, *, base_url: str, model: str, prompt: str, **kwargs: Any) -> dict[str, Any]: ...
    def stream(self, *, base_url: str, model: str, prompt: str, **kwargs: Any) -> Iterator[dict[str, Any]]: ...


class MCPServerAdapter(Protocol):
    def call_tool(self, ctx: RequestContext) -> PeerResult: ...


class SubAgentAdapter(Protocol):
    def invoke(self, ctx: RequestContext) -> PeerResult: ...


class TelemetryAdapter(Protocol):
    def emit(self, name: str, labels: dict[str, str], *, value: float = 1.0) -> None: ...
